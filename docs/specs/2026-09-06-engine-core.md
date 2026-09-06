# Spec: Engine core (2026-09-06)

SUPERSEDED 2026-09-06 by [engine core v2](2026-09-06-engine-core-v2.md) after the red team ([consolidation](../research/redteam/2026-09-06-consolidated.md)). Kept as the dated record of the first design.

Status: superseded. Immutable once approved; corrections go in a dated `UPDATE:` line at the top.

Phase 1 of the [north star](../NORTH-STAR.md). Builds on the [PhotoKit spike](../archive/specs/2026-09-04-photokit-spike.md) and its [results](../research/2026-09-04-photokit-spike-results.md). Every section below is checked against the seven invariants; the invariant numbers are cited where a rule comes from one.

## Decisions this spec assumes

- Minimum macOS 27. Public `PHAssetResource.dataSize` is the size source; no private API anywhere (invariant 4).
- The direct build ships the same engine with no AppleScript and no capability flags. If a need appears later it gets its own spec.
- Product name pending; nothing in the engine carries a product name. The Swift package is `ArchiveCore`, the developer harness is `ArchiveHarness`.

## Goal

A Swift package that performs the entire loop against the real Photos library from inside App Sandbox, with no UI: scan, group, plan, download and verify onto a drive, catalog, delete behind Apple's dialog, restore. Resumable at every step. Able to adopt the existing archive the Python tool produced. Exercised by a headless harness app so it can be proven on this Mac before any SwiftUI exists.

## Non-goals

No SwiftUI, no thumbnails browser, no search UI, no rules engine, no cloud destinations, no changes to the Python tool. Thumbnail generation is in scope because it must happen before deletion; thumbnail display is not.

## Package layout

```
engine/
  Package.swift                  swift-tools 6.x, platforms: [.macOS(.v27)] (language mode 5 until the PhotoKit callbacks are audited)
  Sources/ArchiveCore/
    Library/     LibraryScanner, LocalityProbe, AssetRecord
    Transfer/    Downloader, Verifier, DrivePaths
    Archive/     ArchiveLayout, Manifest (v2), ManifestV1Adapter, ThumbnailMaker
    Jobs/        ArchiveJob, RestoreJob, JobState, JobStore
    Photos/      Deleter, Restorer
    Volumes/     VolumeAccess (bookmarks)
    Grouping/    MomentGrouper, PlaceNamer
    Support/     Hashing, Log, Errors
  Sources/ArchiveHarness/        headless app bundle built like the spike (Makefile, Info.plist, entitlements)
  Tests/ArchiveCoreTests/        pure unit tests: manifest, adapter, job state machine, grouping, layout
  Fixtures/                      one real Python manifest copied from the drive, a synthetic v2 manifest
```

Each module has one purpose, a small public surface, and no knowledge of the others beyond value types. PhotoKit is imported only in `Library/`, `Transfer/Downloader`, `Photos/`, and `Archive/ThumbnailMaker`.

## Data model

`AssetRecord` (value type, Codable) is the engine's view of one video:

| Field | Source | Note |
|---|---|---|
| `photosIdentifier` | `PHAsset.localIdentifier` | volatile, never the catalog key |
| `originalFilename` | original `.video` resource | |
| `sizeBytes` | `dataSize` on the `.video` resource | nil only for assets the engine will not archive |
| `creationDate`, `location`, `duration`, `pixelWidth`, `pixelHeight`, `isFavorite`, `hasAdjustments` | `PHAsset` | |
| `sourceType` | `PHAsset.sourceType` | anything but `.typeUserLibrary` is excluded (invariant 7) |
| `locality` | `LocalityProbe` | `.local`, `.cloudOnly`, `.unknown`; never from a database (invariant 7) |

`ManifestEntry` (v2) is the durable record of one archived video. Key: `contentSHA256` (invariant 3).

```
format_version: 2
content_sha256, size_bytes
relative_path                 path under the archive root, POSIX, UTF-8
original_filename
creation_date (ISO 8601 with offset), latitude, longitude, duration_seconds, pixel_width, pixel_height, is_favorite
photos_identifier_at_archive  informational only
archived_at, archived_by      ISO 8601; "ArchiveCore/<version>" or "iphoto-python/<version>" for adopted entries
thumbnail_path                relative, may be null
restores: [ { restored_at, photos_identifier } ]
```

The manifest is one JSON file, `archive-manifest.json`, at the archive root, pretty-printed, sorted by `creation_date` (invariant 2). It is rewritten atomically (write temp, fsync, rename) after every entry change.

## Archive layout on the drive

```
<root>/
  archive-manifest.json
  thumbnails/<content_sha256>.jpg
  2025/2025-11-13 London/IMG_7736.MOV
  2023/2023-08-29 Moscow/IMG_5447.MOV
  <legacy Python folders, left exactly where they are>
```

Folder is `<YYYY>/<YYYY-MM-DD> <place>` where place comes from `PlaceNamer` and is omitted when unknown. Filenames are the original filename; on collision the content hash's first eight characters are appended before the extension. Nothing in the layout is required to read the archive: a human opening the drive sees dated folders and a JSON file (invariant 2).

## Adopting the existing archive

`ManifestV1Adapter` reads every `iphoto_manifest_*.json` under a root, maps the Python fields (`uuid`, `original_filename`, `moment_name`, `size_bytes`, `checksum`, `archived_path`, `date_created`, `archived_at`, `session_id`) into v2 entries with `archived_by: iphoto-python`, `relative_path` resolved from `archived_path` against the root, and `creation_date` from `date_created`. Files are never moved. Location and duration are absent in v1 and stay null. Verification of adopted entries (re-hash against `checksum`) is a separate, optional, resumable job because the drive is slow. A fixture copied from the real drive drives the unit test.

## Modules

### LibraryScanner

One `PHAsset.fetchAssets(with: .video)` sweep, `includeHiddenAssets` true, mapped to `AssetRecord`. Excludes `sourceType != .typeUserLibrary` before anything else (invariant 7). Emits a `ScanSummary` with counts by exclusion reason so the app can say "12 videos in shared albums were left alone." Under one second for 5,000 assets in the spike.

### LocalityProbe

A network-disallowed `requestData` per asset; error 3164 means cloud-only, success means local, anything else `.unknown`. Runs on demand per asset in the plan, not on the whole library, because probing a local asset reads the whole file.

### Downloader and Verifier

Ported from the spike's `Downloader`: `requestData` streamed to the destination file with network allowed, inline SHA-256 as chunks arrive, a progress-inactivity watchdog of 180 s that cancels, an absolute cap of 3600 s, three attempts with 5, 15, 45 s backoff. Concurrency 2 by default, configurable 1 to 4 (spike finding 9). Destination is the final path on the drive; there is no staging directory. `Verifier` then re-reads the file from the drive and compares the read-back hash to the inline hash and the size to `dataSize`; only the read-back result counts (invariant 1). On mismatch the file is removed and the attempt counted as failed.

### ThumbnailMaker

After verification, one poster JPEG at 512 px on the long edge from the archived file via `AVAssetImageGenerator`, written to `thumbnails/<hash>.jpg`. Failure to make a thumbnail never fails the archive step; the manifest records null.

### MomentGrouper and PlaceNamer

Pure functions. Grouping: split by calendar day in the asset's local time zone, then merge adjacent days when the location centroid moves less than 2 km; assets without location group by day alone. `PlaceNamer` reverse-geocodes one centroid per group through `CLGeocoder`, cached by rounded coordinate in the job store, rate-limited to one request per second with a 50-per-run ceiling; groups over the ceiling keep a date-only name until a later run. PhotoKit has no moments on macOS; this replaces the Python tool's SQLite moments.

### JobState and JobStore

A job is a list of assets and a per-asset step machine:

`planned → probed → downloading → verified → thumbnailed → cataloged → deletable → deleted → done`, plus `failed(reason, attempts)` and `skipped(reason)`.

The store is one JSON file per job in the app container, rewritten atomically after every transition. Resume re-derives every asset's true step from disk and library state, not from the stored step: a file that exists and re-hashes correctly is `verified` whatever the store says; an asset that is no longer fetchable is `deleted` (invariants 1 and 5). Sleep and drive disconnect are ordinary interruptions; the drive absent state pauses the job and surfaces `needsReconnect`.

Space planning before download: required bytes are counted twice, once for the drive and once for the library cache PhotoKit leaves behind (spike finding 4), against `volumeAvailableCapacityForImportantUsage` on both volumes. The job refuses to start below the budget and stops cleanly if either volume drops below a 2 GB floor mid-run.

### Deleter

Takes only assets at `deletable`. Preconditions, re-checked at run time from disk: manifest entry present, archived file re-hashes to `content_sha256`, `canPerform(.delete)` true. One `performChanges` block per batch of at most 50 assets so the user sees one dialog per batch, a 120 s watchdog for the known "completion never fires" case, then re-fetch of every identifier; `deleted` is set only for identifiers that are no longer fetchable (invariant 1). The dialog wording is Apple's.

### Restorer

Input: a manifest entry. Refuses if `photos_identifier_at_archive` is still fetchable, or if any `restores[].photos_identifier` is still fetchable, or if the file's hash no longer matches (invariant 3). Otherwise `PHAssetCreationRequest` with the `.video` resource from the archive file (`shouldMoveFile` false), explicit `creationDate`, `location`, and `isFavorite`. After completion: fetch the new asset, compare date within 1 s and location within 10 m, re-download its original and hash against the entry. Records the restore in the manifest. The archived file stays on the drive.

### VolumeAccess

Security-scoped bookmark with `.withSecurityScope` and `.withoutMounting` (spike finding 14). States: `.available(url)`, `.absent` (Cocoa error 4 or unreachable), `.stale` (re-store the bookmark), `.needsReselect` (resolution error other than absence). The catalog also stores the volume UUID and name so the app can say which drive to plug in. `startAccessingSecurityScopedResource` is balanced with `stop` in a `defer` on every use.

## Harness

`ArchiveHarness` is a headless app bundle, built and signed by Makefile exactly like the spike, launched with `open -W` (permissions attach to the bundle). Commands, each writing JSONL to a chosen folder: `scan`, `group`, `plan`, `archive --job`, `delete --job --i-understand`, `restore --hash`, `adopt --root`, `verify --root`, `volume`. The harness is how the phase 1 exit gate is run and is not product code.

## Error handling

Errors are typed (`EngineError` with a `PhotoKitError(domain, code)` case) and carry the asset's content hash or identifier. Nothing is retried silently beyond the download policy above. Every failure lands in the job store with the attempt count so resume can decide. User-facing text is the app's job (invariant 6); the engine never formats messages for people.

## Testing

- Unit, in `swift test`: manifest v2 round trip; v1 adapter against the real fixture; job step derivation from synthetic disk states; grouper on synthetic assets; layout naming and collision; volume state mapping from error codes.
- Integration, manual through the harness on this Mac: the phase 1 exit gate in STATE. One real user-library asset with two verified copies goes through archive, delete, and restore; the library ends with the same footage; the adopted Python archive verifies for at least one manifest.
- The Python tool's manifests and archive on the Acer drive are the compatibility oracle, read-only.

## Slices

Each slice gets its own plan under `docs/plans/` and flips its COVERAGE rows in the commit that ships it.

1. Package skeleton, `AssetRecord`, `LibraryScanner` with shared-album exclusion, `LocalityProbe`, harness `scan`.
2. `Manifest` v2, `ArchiveLayout`, `ManifestV1Adapter` with fixture, harness `adopt`.
3. `Downloader`, `Verifier`, `ThumbnailMaker`, `JobState`, `JobStore`, `VolumeAccess`, harness `archive` with resume.
4. `Deleter`, harness `delete`.
5. `Restorer`, harness `restore`.
6. `MomentGrouper`, `PlaceNamer`, harness `group`.
7. Exit-gate run on the real library, results record under `docs/research/`.

## Risks

- macOS 27 is in beta on this Mac; API behavior may shift before release. The harness re-runs the spike measurements cheaply.
- `AVAssetImageGenerator` on very large 4K files may be slow on the drive; thumbnails are optional by design.
- `CLGeocoder` quotas are undocumented; the ceiling and cache keep it polite, and a date-only name is always acceptable.
- Direct-to-drive streaming on a slow or flaky drive means a failed download leaves a partial file; the verifier removes it, and the job resumes from the manifest, not from the partial.
