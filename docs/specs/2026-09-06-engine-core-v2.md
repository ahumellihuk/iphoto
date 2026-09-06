# Spec: Engine core, v2 (2026-09-06)

Status: draft for review; supersedes [engine core v1](2026-09-06-engine-core.md) after the red team ([consolidation](../research/redteam/2026-09-06-consolidated.md)). Immutable once approved; corrections go in a dated `UPDATE:` line at the top. Sections unchanged from v1 are kept so this file stands alone.

## Decisions this spec assumes

- Minimum macOS: pending decision D1. The spec is written so that either answer is a small delta: a `SizeInfo` type carries exact sizes on macOS 27 and estimates on 26.
- The direct build ships the same engine with no AppleScript and no capability flags.
- Product name Video Attic. The Swift package is `ArchiveCore`, the harness is `ArchiveHarness` with bundle id `dev.videoattic.harness`, kept outside any App Store Connect record.
- Edited videos are excluded from phase 1 (decision D4, recommended yes).

## Goal

A Swift package that performs the entire loop against the real Photos library from inside App Sandbox, with no UI: scan, group, plan, download and verify onto a drive, catalog, delete behind Apple's dialog, restore. Resumable at every step. Able to adopt the existing archive the Python tool produced, and to keep adopting it while the frozen CLI is still used. Exercised by a headless harness so it can be proven on this Mac before any SwiftUI exists.

## Non-goals

No SwiftUI, no thumbnails browser, no search UI, no rules engine, no cloud destinations, no changes to the Python tool. Archiving rendered edits and adjustment data is a later spec. Thumbnail generation is in scope because it must happen before deletion.

## Package layout

```
engine/
  Package.swift                  swift-tools 6.0, platforms per D1, language mode 5
  Sources/ArchiveCore/
    Support/     EngineError, Signals (closed enums), Hashing, OneShot, Log
    Library/     AssetFacts, AssetRecord, AssetClassifier, PhotoKitLibraryScanner, LocalityProbe, LibraryEnvironment
    Transfer/    Downloader, Verifier
    Archive/     ArchiveLog, ManifestProjection, ArchiveLayout, ManifestV1Adapter, ThumbnailMaker, Sanitize
    Jobs/        JobState, JobStore, ArchiveJob, RestoreJob, BatchPlanner
    Photos/      Deleter, Restorer
    Volumes/     VolumeAccess
    Grouping/    MomentGrouper, PlaceNamer
  Sources/ArchiveHarness/        headless app bundle built by Makefile, launched with open -n -W
  Harness/                       Info.plist, entitlements
  Tests/ArchiveCoreTests/        pure unit tests
  Fixtures/                      one real Python manifest (with an empty checksum, a duplicate uuid, a missing file), a synthetic v2 log
```

PhotoKit is imported only in `Library/PhotoKitLibraryScanner`, `Library/LocalityProbe`, `Library/LibraryEnvironment`, `Transfer/Downloader`, `Photos/`, and `Archive/ThumbnailMaker`. Nothing that is a `PHAsset`, `PHAssetResource`, or `PHFetchResult` crosses a task boundary; tasks receive identifiers or `AssetRecord` values and re-fetch inside.

## Signals: the closed vocabulary the app localizes

The engine never formats messages for people (invariant 6), so it must give the app a finite set of cases. Every `failed`, `skipped`, or refusal carries one of these, never a free string.

```
ExclusionReason   notUserLibrary | noOriginalVideoResource | sizeUnknown | hasAdjustments | highFrameRate | cinematic | hidden | livePhotoComponent
LocalityCause     .local | .cloudOnly | .unknown(timedOut | otherError(code))
FailureReason     network(code) | stalled | byteMismatch | outOfSpace(volume) | writeError(code) | assetVanished | libraryUnavailable | cancelled
RefusalReason     originalStillPresent(identifier) | alreadyRestored(identifier) | archiveHashMismatch | originNotUserLibrary | needsHash | changedSinceArchive | volumeMismatch | notDeletable
DeleteOutcome     confirmed | declined | unconfirmed(awaitingDialog) | partial(confirmed: [id], remaining: [id])
BudgetShortfall   volume(drive | library) needed available ofWhichCache
LibraryEnvironment authorization(authorized | limited | denied | notDetermined), iCloudPhotosLikely: Bool, optimizeStorageLikely: Bool,
                  libraryVolume: URL?, isSystemLibrary: Bool, sharedLibraryDetected: Bool?, videoCount: Int, canaries: [String]
```

A unit test asserts every `JobState` transition into `failed` or `skipped` carries a case.

## Data model

`AssetFacts` is what the scanner reads from one `PHAsset` and its resources, PhotoKit-free so the rules are testable. `AssetRecord` is the engine's value for one archivable video.

| Field | Source | Note |
|---|---|---|
| `photosIdentifier` | `PHAsset.localIdentifier` | volatile; never a catalog key |
| `originalFilename`, `sizeInfo` | the `.video` resource; `dataSize` on 27 | `SizeInfo.exact(bytes)` or `.estimated(bytes)`; estimate = duration × pixels × codec table × 1.25 for budgeting |
| `creationDate`, `modificationDate`, `location` (lat, lon, altitude), `duration`, `pixelWidth`, `pixelHeight`, `isFavorite`, `isHidden`, `hasAdjustments`, `mediaSubtypesRaw` | `PHAsset` | `modificationDate` and `hasAdjustments` are re-read at catalog and at delete |
| `albumTitles` | `PHAssetCollection.fetchAssetCollectionsContaining` | user albums only; cheap now, impossible after delete |
| `sourceTypeRaw` | `PHAsset.sourceType` | anything but exactly the user-library bit is excluded |
| `locality` | `LocalityProbe` | advisory, with `probedAt` |

Classification rules, in order: not user library → `notUserLibrary`; no `.video` resource → `noOriginalVideoResource` (there is no fallback to `.fullSizeVideo`); `hasAdjustments` → `hasAdjustments`; subtype high frame rate → `highFrameRate`; cinematic → `cinematic`; hidden → `hidden`; size unknown on macOS 27 → `sizeUnknown` (on 26 an estimate is used instead). Live Photos are images and never appear in a `.video` fetch; the classifier still tests `livePhotoComponent` so a future change cannot archive a paired video and delete the still. PhotoKit has no public API for titles, captions, or keywords; they are not preserved and the app must say so.

## Archive on the drive

```
<root>/
  archive-log.jsonl               append-only truth, one event per line
  archive-manifest.json           compacted, pretty-printed projection; regenerated at job end and idle
  archive-manifest.prev.json      previous projection
  archive.lock                    pid and heartbeat of the writer
  README.txt                      static: what the folders and files are, both layouts, both manifest families
  thumbnails/<sha256>.jpg
  2025/2025-11-13 London/IMG_7736.MOV
  <legacy Python folders and iphoto_manifest_*.json, never touched>
```

**Log and projection.** The log is the durable truth. Each line is a self-contained event: `entry` (a full entry object), `asset_added`, `deleted`, `restore_intent`, `restored`, `adopted`. Writes are one line plus one `fsync`, serialized through one actor holding `archive.lock` (pid, hostname, heartbeat every 30 s; a stale lock older than 5 minutes may be taken over). A torn last line is dropped on read. The projection is rebuilt from the log at job end and at idle; readers use the log when it is newer than the projection; a projection or log that fails to parse is an error surfaced to the user, never treated as empty. The app container keeps a mirror of the log; `verify --rebuild` reconstructs from the log plus a directory walk.

**File header** (first log line and top of the projection): `format_version`, `min_reader_version`, `archive_id` (UUID minted at creation), `volume_uuid`, `volume_name`, `written_by`. Writers refuse when `format_version` exceeds theirs. Unknown keys round-trip untouched.

**Entry** (keyed by `content_sha256`, 64 lowercase hex, non-optional):

```
content_sha256, size_bytes, relative_path (NFC), status: ok | needs_hash | missing
group_name, media_subtypes, duration_seconds, pixel_width, pixel_height, has_adjustments
creation_date (ISO 8601 with offset), creation_date_offset_source: location | device | python
latitude, longitude, altitude
thumbnail_path?, adjustments_path?, rendered_path?
archived_by, archived_at, archived_at_precision: exact | local_naive, archived_from: userLibrary | unknown, mode: archived | copied
assets: [ { photos_identifier, original_filename, creation_date, is_favorite, is_hidden, album_titles, archived_at, deleted_at? } ]
restores: [ { restored_at, photos_identifier } ]
restore_intent?: { started_at, placeholder_identifier }
adopted_from: [ { file, session_id, uuid } ]
```

Two library assets with identical bytes are one entry with two `assets[]` items; nothing is overwritten.

**Layout.** Folder `<YYYY>/<YYYY-MM-DD> <place>` where the date is the creation instant rendered in the offset chosen by rule: the placemark's time zone when there is a location, else the Mac's zone, recorded as `creation_date_offset_source`; adopted entries keep Python's. Before naming a group, reuse any existing folder in the catalog with the same date whose centroid is within 2 km. Place is sanitized (Python's character set plus control characters, leading and trailing dots and spaces, Windows reserved names), capped at 60 characters, omitted when unknown. Filenames are the original filename; the collision rule is decided before download against the catalog, compared after NFC normalization and case folding: same hash means already archived, different hash appends the first eight hash characters, and a file already present at the target that the catalog does not know is a hard stop (`FailureReason.writeError`), never deleted.

## Adopting the Python archive

`ManifestV1Adapter` reads every `iphoto_manifest_*.json` under the root on every open, adopting new or changed files by `(uuid, session_id)`. Field mapping: `uuid` → `assets[0].photos_identifier` (bare UUID; fetchability compares on the UUID prefix); `original_filename` (may be "unknown"); `moment_name` → `group_name`; `size_bytes` (prefer the file's real size, record mismatch); `checksum` → `content_sha256` when 64 hex, else `status: needs_hash` with a legacy key `legacy:<uuid>:<session_id>` until the verify job hashes the file and merges equal hashes; `archived_path` resolved by its last two components under the root, else Python's own recovery search (same folder, matching size, then hash), else `status: missing`; `date_created` (naive means UTC, as Python wrote it); `archived_at` is naive local time, kept with `archived_at_precision: local_naive`; `session_id` → `adopted_from`. `archived_from: unknown`, `mode: archived`, `archived_by: iphoto-python`. Files are never moved or renamed, and nothing is written inside legacy folders, so the frozen CLI keeps working on the same drive. Entries with `needs_hash`, `missing`, or `archived_from: unknown` cannot be deleted against or restored until verified, and the user is told why.

## Modules

### LibraryEnvironment

Computed before any scan, derivation, delete, or restore: authorization (must be `.authorized`; `.limited` and `.denied` are refusals, in the engine, not the harness), whether the library is the System Library, the library's volume (for budgeting), whether iCloud Photos and Optimize Storage are likely (from probe results), a Shared Library detection attempt (slice 1 investigates what macOS 27 exposes; result may be `nil` for "cannot tell"), total video count, and three canary identifiers recorded at plan time. A job pauses as `libraryUnavailable` when the count moves beyond tolerance or a canary is unfetchable.

### LibraryScanner

One `fetchAssets(with: .video)` sweep with hidden assets included (measure in slice 1 whether third-party clients receive hidden assets), off the main actor, mapped to `AssetFacts` and classified. Resource lookup is an XPC call per asset, so timing is measured, not assumed. Emits `ScanSummary` counts per `ExclusionReason`.

### LocalityProbe

A network-disallowed `requestData`. The first data chunk proves local and cancels the request; error 3164 means cloud-only; a 60 s timeout or any other error is `.unknown` with its cause. Per asset, on demand, never the whole library.

### Downloader and Verifier

Streams `requestData` with network allowed to `<final>.partial` in the final folder, writing with the throwing `write(contentsOf:)` under a lock with a closed flag; a write error cancels the request and records `FailureReason.writeError`. Inline SHA-256 as chunks arrive. Watchdog on a suspending clock: 180 s without progress or data cancels; absolute cap 3600 s; three attempts with 5, 15, 45 s backoff; `beginActivity(.idleSystemSleepDisabled)` for the job's lifetime, and wake or volume change is a resume, not a failure. After the last chunk, `F_FULLFSYNC` (fall back to `fsync` where unsupported), then the verifier re-reads the file with `F_NOCACHE` and compares the read-back hash to the inline hash and the size to `SizeInfo` (exact must match; estimated is replaced by the real size). Only the read-back result counts (invariant 1). On success the file is renamed to its final name; on failure the `.partial` is removed and the attempt counted. Concurrency 2 by default, 1 to 4 configurable. The Downloader never removes a file it did not create in this attempt.

### ThumbnailMaker

Before download, one poster JPEG at 512 px from PhotoKit (`PHImageManager`, SDR), written to `thumbnails/<hash>.jpg` once the hash is known. Never generated from the drive. Failure never fails the archive step.

### MomentGrouper and PlaceNamer

Pure functions. Split by calendar day in the chosen offset, merge adjacent days when the location centroid moves less than 2 km; assets without location group by day alone. `PlaceNamer` uses `MKReverseGeocodingRequest`, one request per group centroid, cached app-level by rounded coordinate across runs, one request per second, 50 per run; over the ceiling groups keep a date-only name until a later run; `MKError.loadingThrottled` backs off.

### JobState and JobStore

Stored per-asset steps: `planned → downloading → verified → cataloged → deleted`, plus `failed(reason, attempts)` and `skipped(reason)`. `deletable` is a runtime predicate (cataloged ∧ fetchable ∧ `canPerform(.delete)` ∧ not `changedSinceArchive` ∧ volume matches), not a state. Derivation on resume is monotonic and gated by the table below; a stored step is never trusted upward.

| Stored | Disk fact | Library fact | Derived |
|---|---|---|---|
| any | final file exists and re-hashes to catalog entry | fetchable | cataloged |
| any | `.partial` exists | fetchable | downloading (partial removed, restart) |
| cataloged | file re-hashes | not fetchable | deleted |
| planned or downloading | no file | not fetchable | failed(assetVanished) |
| any | file missing | fetchable | planned |

Job file `jobs/<jobId>.json` in the container with `schema_version, job_id, archive_id, volume_uuid, created_at, updated_at, concurrency, assets[]`, held under `flock` for the process lifetime, rewritten atomically, and copied beside the log on the drive at each batch end. Space planning is per batch: `BatchPlanner` sizes batches to the smaller of drive headroom and library-volume headroom (counting PhotoKit's cache of every downloaded original, spike finding 4), refuses below the budget with a `BudgetShortfall`, stops cleanly at a 2 GB floor, and reports `estimatedFreeDate` (latest delete plus 30 days) and `bytesPendingPurge` so the app can set expectations about Recently Deleted.

### Deleter

Takes only assets satisfying the `deletable` predicate. Preconditions re-checked at run time: log entry present, archived file re-hashes with `F_NOCACHE`, `modificationDate` and `hasAdjustments` unchanged since catalog, resolved volume UUID equals the entry's, `canPerform(.delete)`. Batch identifiers are written to the job store before submission. One `performChanges` block per batch of at most 50; never a second while one is outstanding. A 120 s watchdog moves the batch to `awaitingDialog`, polled by re-fetch every 10 s for up to an hour, and no further batch starts until it resolves. `deleted` is derived only from re-fetch, never from the callback alone. Outcome is a `DeleteOutcome`. Continuations use a one-shot box on `Mutex`.

### Restorer

Refuses with a `RefusalReason` when any identifier in `assets[]` or `restores[]` is fetchable, when the file's hash no longer matches, when `archived_from` is not the user library, or when a candidate search (original filename, duration within 0.5 s, size, creation date within 1 s) finds a library asset whose original hashes equal. Writes `restore_intent` to the log before `performChanges`; on resume, the placeholder identifier is checked first. Creates the asset from the archive file with `shouldMoveFile` false, explicit `creationDate` in the recorded offset, `location` with altitude, `isFavorite`, `isHidden`, and re-links user albums by title where they still exist. After completion: fetch, compare date within 1 s and location within 10 m, re-download the new asset's original and hash it against the entry; an unverified restore is flagged and blocks further restores of that entry. Records `restored` in the log; the archived file stays.

### VolumeAccess

Security-scoped bookmark resolved with `.withSecurityScope` and `.withoutMounting`; states `available`, `absent` (Cocoa error 4 or unreachable), `stale`, `needsReselect`. Access is started once when a volume becomes available and stopped once when released or at exit; the URL is kept alive for the duration. The entry's volume UUID is compared on every delete.

## Harness

`ArchiveHarness`, bundle `dev.videoattic.harness`, built and signed with the Apple Development identity (ad hoc signing changes the TCC attribution on every rebuild), launched with `open -n -W` behind a running-instance guard. Commands write JSONL to the chosen folder: `scan`, `environment`, `group`, `plan`, `archive --job`, `delete --job --i-understand`, `restore --hash`, `adopt --root`, `verify --root [--rebuild]`, `volume`.

## Error handling

`EngineError` is typed with a `photoKit(domain, code)` case. Nothing is retried silently beyond the download policy. Every failure lands in the job store with its `FailureReason` and attempt count.

## Testing

- Unit: signals coverage of every transition; classifier rules and precedence including subtypes, hidden, adjustments, Live Photo; log parse with a torn last line and an unparsable projection; header version refusal and unknown-key round trip; v1 adapter against the real fixture with empty checksum, duplicate uuid, missing file, naive dates; derivation table on synthetic states including "planned, file absent, asset absent" not deriving `deleted`; sanitation, NFC, case folding, collision; volume state mapping; batch planning arithmetic.
- Integration through the harness on this Mac: the phase 1 exit gate as sharpened in decision D3.
- The Python archive on the Acer drive is the compatibility oracle, read-only.

## App Review dossier (appendix, drafted in phase 1, used in phase 3)

Usage string: "Video Attic needs your whole Photos library to find large videos, copy them to your drive, and remove them only after you confirm in Photos' own dialog." Justification under 5.1.1(iii): the picker cannot enumerate, download originals, or delete. Sandbox and public API statements under 2.4.5 and 2.5.1. Deletion precedent: Gemini 2. Privacy label: location data sent to Apple for place names. Review notes include a demo script on a sample library.

## Slices

1. Package skeleton; `AssetFacts` and `AssetRecord` with the full field set; classifier with all exclusions and precedence tests; `LibraryEnvironment` with `.limited` refusal and the Shared Library detection probe; `PhotoKitLibraryScanner` off main actor; `LocalityProbe` with timeout and early cancel; harness `scan` and `environment`; hidden-asset visibility measured.
2. `ArchiveLog`, `ManifestProjection`, header, `Sanitize`, `ArchiveLayout`, `ManifestV1Adapter` with the real fixture, harness `adopt` and `verify`.
3. `Downloader` (`.partial`, fsync, no-cache read-back), `Verifier`, `ThumbnailMaker` from PhotoKit, `JobState` with the derivation table, `JobStore` with lock and drive copy, `BatchPlanner`, `VolumeAccess`, harness `archive` with resume across kill, sleep, and unplug.
4. `Deleter` with `awaitingDialog`, harness `delete`.
5. `Restorer` with intent, candidate search, albums, harness `restore`.
6. `MomentGrouper`, `PlaceNamer` on MapKit, harness `group`.
7. Exit-gate run per decision D3, results record under `docs/research/`.
