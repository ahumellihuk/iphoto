# Red team: archive format and job state machine (2026-09-06)

Fable 5.1 reviewer report, verbatim.

# Durable data design review: engine core spec and slice 1 plan

Sources: `docs/NORTH-STAR.md` (inv. 2, 3, 5), `docs/specs/2026-09-06-engine-core.md`, `docs/plans/2026-09-06-engine-slice-1.md`, `src/iphoto/{manifest,models,cli,exporter,mover,scanner}.py`. `/Volumes/AcerFA200/Photos-archive` was not mounted; v1 values are taken from `build_manifest_entry`.

## Critical

### C1. Single rewritten manifest is a single point of catalog loss on a drive known to hang mid-write
Spec: Data model ("one JSON file... rewritten atomically after every entry change"); Risks.
Scenario: 3,000 entries at ~600 bytes is a ~2 MB rewrite plus fsync per archived video. The Acer drive degraded to 0.3 to 0.7 MB/s and reset its USB bridge under sustained writes (memory note, 2026-09-04). A reset between "temp written" and "rename" leaves `archive-manifest.json.tmp` plus either the old file or, on exFAT through FSKit where replace-rename atomicity is not guaranteed, nothing. The Python reference (`load_manifest`) treats an unparsable manifest as empty; if v2 does the same, the engine sees no catalog, `Deleter` has no entries (safe), but every human-readable record for files already on the drive is gone and `Restorer` cannot run. Invariant 2 is broken by the app's own write pattern.
Change: make the durable truth an append-only `archive-log.jsonl` (one entry per line, one `fsync` of a few hundred bytes per event, never rewritten; a torn last line is dropped on read), and make `archive-manifest.json` a compacted, pretty-printed projection regenerated at job end and at idle, never on the hot path. Keep the previous generation as `archive-manifest.prev.json`. Reader rule: log wins over manifest; a manifest that fails to parse is an error surfaced to the user, never "empty". Add `rebuild` (harness `verify --rebuild`) that reconstructs entries from log plus directory walk. Test: truncate the log mid-line and the manifest mid-file; loading must yield all complete entries and refuse silently-empty.

### C2. "Not fetchable means deleted" is stated without the precondition "and cataloged"
Spec: JobState and JobStore ("an asset that is no longer fetchable is `deleted`").
Scenario: an asset at `planned` or `downloading` disappears from the fetch: the user deleted it in Photos, iCloud merged a duplicate, or the local identifier changed after a library re-sync (identifiers are volatile per invariant 3). Resume marks it `deleted`, the job reports success, and no bytes were ever written. Also the inverse: after a confirmed delete, Photos keeps the asset in Recently Deleted for 30 days; the spec never says whether "fetchable" includes it.
Change: derived rule `deleted = cataloged(hash) ∧ archived file re-hashes ∧ asset not fetchable`. Not fetchable and not cataloged is `failed(assetVanished)` and is reported. Define fetchable as `PHAsset.fetchAssets(withLocalIdentifiers:)` non-empty, with a note that trashed assets are excluded and that this is intended. Carry a secondary match key in the job (`uuid`, `originalFilename`, `creationDate`, `sizeBytes`) so a changed identifier is re-linked rather than declared gone. Unit test: synthetic state "planned, file absent, asset absent" must not derive `deleted`.

## High

### H1. Hash-keyed entries collapse two library assets with identical bytes into one, losing the second one's metadata and confusing restore
Spec: Data model (key `content_sha256`), Restorer.
Scenario: Photos holds A and B with identical originals (AirDrop re-import, a prior restore of A while A was still present, which the spike itself produced twice). Archive A: entry E with `photos_identifier_at_archive = A`. Later B is planned; resume finds the file, re-hashes, and B goes `verified → cataloged` by overwriting E (or by the collision rule, which appends the same eight hash characters and so still resolves to the same path). B's creation date, location, favorite and filename, which can differ from A's, are gone once B is deleted. Restore checks only E's single identifier; if A was deleted but B is still in the library, restore succeeds and creates a duplicate, breaking invariant 3.
Change: keep the file keyed by hash, but make `assets` a list inside the entry: `[{ photos_identifier, original_filename, creation_date, latitude, longitude, is_favorite, archived_at, deleted_at }]`, appended, never overwritten. Restorer refuses if any identifier in `assets[]` or `restores[]` is fetchable, and restores the metadata of the asset the user picked (default: the first). `restores[]` growth is bounded by user actions and is not a concern; add `deleted_at` per cycle so the history is readable. Test: archive A, archive B (same bytes, different date), delete both, restore: two assets with distinct dates.

### H2. Edits, slo-mo ranges and album membership are not captured and are unrecoverable after deletion
Plan: Task 2 `AssetRecord`; Spec: Data model, Restorer.
Scenario: a trimmed or colour-adjusted video (`hasAdjustments == true`) is archived as the `.video` original only. After deletion the trim is gone forever; restore returns the untrimmed original with no warning. Slo-mo playback range is an adjustment too. Album membership (`PHAssetCollection.fetchAssetCollectionsContaining`) is cheap to read now and impossible later. `isHidden`, `mediaSubtypes` (slo-mo, time-lapse, cinematic), CLLocation altitude, and `modificationDate` are likewise cheap now, gone later.
Change: `AssetRecord` gains `mediaSubtypesRaw`, `isHidden`, `modificationDate`, `altitude`, `albumIdentifiers: [String]` and `albumTitles: [String]`. The archive step writes the `.adjustmentData` resource (small) to `adjustments/<hash>.plist` when `hasAdjustments`, and optionally the rendered `.fullSizeVideo` as a second file recorded under `rendered_path`; the manifest records `has_adjustments` and `rendered_path`. Restorer re-adds to albums whose identifiers still resolve and re-hides hidden assets. Anything not implemented in slice 1 is listed in the spec under "lost on delete" so the app can warn. PhotoKit has no public title, caption or keyword access; say so explicitly so nobody assumes they are preserved. Consider `cloudIdentifierMappings(forLocalIdentifiers:)` as a stable secondary key for H1 and C2.

### H3. Adapter maps `archived_at` and `checksum` without accounting for their v1 shape
Spec: Adopting the existing archive.
Field-by-field (v1 from `build_manifest_entry`):
- `uuid`: bare Photos UUID. PhotoKit's `localIdentifier` is `UUID/L0/001`; store as `photos_identifier_at_archive` but every fetchability comparison must be on the UUID prefix (`AssetRecord.uuid` already exists; use it uniformly).
- `original_filename` → `original_filename`. May be `"unknown"` (scanner fallback).
- `moment_name` → new field `group_name` (see M2); it is also the on-disk folder after `sanitize_folder_name`.
- `size_bytes` → `size_bytes`, from the Photos database, may be 0; prefer the file's stat size and record a mismatch.
- `checksum` → `content_sha256`. Can be `""` (`checksum or ""` in `_append_archive_manifest_entries`). An empty key cannot go into a hash-keyed catalog. Adapter must hash the file (slow, resumable, part of the optional verify job) and until then the entry has `content_sha256: null` and `status: "needs_hash"`; Restorer and Deleter refuse such entries.
- `archived_path` → `relative_path`: see H4.
- `date_created` → `creation_date`. Written by `.isoformat()` of a tz-aware datetime (scanner forces UTC when naive) so it carries an offset; accept a naive string and treat it as UTC, since that is what Python did.
- `archived_at` → `archived_at`: `datetime.now().isoformat()` is naive local time with no offset. Parse as local time of the adopting Mac and record `archived_at_precision: "local_naive"`; do not fabricate a Z.
- `session_id` → `adopted_from: { file, session_id, uuid }`. `archived_by: "iphoto-python"` with no version, because v1 recorded none.
Test: fixture must include an entry with empty checksum and a naive `archived_at`.

### H4. `archived_path` resolution and duplicate UUIDs across manifests are unspecified
Spec: Adopting the existing archive.
Scenario: `archived_path` is `/Volumes/AcerFA200/Photos-archive/Barking Park • May 31, 2026/IMG_7736.MOV`. After a double-mount the volume is `AcerFA200 1`; on another Mac the root is elsewhere. Naive `relativeTo(root)` fails. Separately, `append_manifest_entries` de-duplicates by UUID only within one session file; `retry_failed` and a fresh session after a failed delete write the same UUID into a second file, possibly with a different `moment_name` folder.
Change: resolve by suffix: take the last two components (Python's layout is exactly `<root>/<folder>/<file>`) and confirm existence under the root; if absent, fall back to Python's own recovery (`_find_valid_archived_file`): any file in that folder with matching size, then hash. For duplicate UUIDs, prefer the entry whose file exists; if several exist, prefer the latest `archived_at` and keep the others in `adopted_from[]`. Entries with no file anywhere become `status: "missing"` entries (never dropped, so the human record survives) and are excluded from restore.

### H5. Adoption must be repeatable because the frozen CLI keeps writing v1 files
Spec: Adopting the existing archive; North star (CLI still used).
Scenario: the user adopts, then runs `iphoto archive` again; a new `iphoto_manifest_<id>.json` appears and its entries are not in v2. If adoption is eager and one-shot, the catalog silently diverges. If the engine ever renamed or moved a legacy file, `_find_valid_archived_file` and `iphoto verify` would report it missing.
Change: eager adoption into the v2 log, plus a `v1_sources: [{file, size, mtime, entry_count}]` ledger. On every root open, re-scan `iphoto_manifest_*.json`, adopt only new or changed files, dedupe by `(uuid, session_id)`. Rule: the engine never writes, renames, or moves anything inside a legacy folder or any `iphoto_manifest_*.json`. Test: adopt, append a synthetic v1 file, re-open, expect one new entry and no duplicates.

### H6. Partial downloads are indistinguishable from finished files, and the collision rule can preserve them
Spec: Downloader and Verifier ("no staging directory"), Archive layout (collision rule), JobState.
Scenario: the app dies mid-download; `2025/2025-11-13 London/IMG_7736.MOV` is a 40% file. On resume, the collision rule sees an existing file and writes `IMG_7736-3fa9c2b1.MOV` next to it; the partial stays, a human sees a broken video (invariant 2), and "a file that exists and re-hashes correctly is verified" must now re-hash every candidate on a slow drive to know which is which.
Change: download to `<final>.partial` in the final folder (not a staging directory, still compatible with the spec's intent), rename on read-back success; on resume delete any `*.partial` older than the job. Collision is declared only when the existing file's hash (from the manifest, not a re-read) differs from the incoming hash; same hash means already archived. Resume re-hashes only assets whose stored step is `downloading` or `verified` and not yet `cataloged`; cataloged entries are trusted until `Deleter` re-hashes them anyway (invariant 1).

## Medium

### M1. Folder date has no defined time zone, and the spec's grouper assumes one PhotoKit does not provide
Spec: Archive layout, MomentGrouper ("calendar day in the asset's local time zone"), Data model (`creation_date` with offset).
Scenario: `PHAsset.creationDate` is an instant; PhotoKit exposes no capture offset. A 23:30 London video rendered in UTC lands in the next day's folder; the same video adopted from Python (osxphotos supplied the library's offset) lands in the right one. Two folders for one evening.
Change: rule, in order: offset from the reverse-geocoded placemark's `timeZone` when location exists; else the Mac's current zone; record the chosen offset in `creation_date` and add `creation_date_offset_source: "location" | "device" | "python"`. Adopted entries keep Python's offset. Test both branches.

### M2. Place name drift creates sibling folders for the same day, and legacy folders confuse the listing
Spec: Archive layout, PlaceNamer.
Scenario: run 1 names `2025-11-13 London`; run 2's geocoder answers "Westminster" and creates `2025-11-13 Westminster`; run 3 is over the 50-request ceiling and creates `2025-11-13`. The root also holds `Barking Park • May 31, 2026/` beside `2025/`, `thumbnails/`, two manifest naming schemes, and (per C1) a log.
Change: before naming a group, reuse any existing folder in the manifest whose date prefix matches and whose centroid is within 2 km; store `group_name` per entry so the reuse is deterministic. Write a static `README.txt` at the root describing both layouts and both manifest families. Keep the geocode cache app-level, not per job (spec puts it in the job store, where it dies with the job).

### M3. Filename sanitation, normalization, length and case rules are absent
Spec: Archive layout.
Scenario: exFAT is case-insensitive, stores UTF-16 with a 255-unit component limit, and macOS does not normalize Unicode on it. `IMG_1.MOV` and `img_1.mov` collide silently; a manifest `relative_path` in NFD fails to match a directory listing in NFC; a CLGeocoder name with `/` or `:` ("St. John's / Barking") breaks the path; a Windows reader chokes on `?`, `"`, trailing dots, `CON`.
Change: sanitize with Python's set plus control characters, leading/trailing dots and spaces, and Windows reserved names; cap place at 60 characters; store `relative_path` in NFC and compare case-insensitively after NFC; collision detection is case-insensitive. Unit tests for each.

### M4. Versioning, unknown fields and multiple roots are unspecified
Spec: Data model.
Scenario: `format_version: 2` appears inside the entry block; file-level version is implied. A future app writes a v3 field; the user opens the drive with an older app, which decodes with `Codable`, drops the unknown key, and rewrites: the field is gone. Two drives each have a manifest with no identity, so the app cannot say which drive holds a video, and a cloned drive cannot be told from its source.
Change: file header `{ format_version, min_reader_version, archive_id (UUID at creation), volume_uuid, volume_name, written_at, written_by, entries: [...] }`. Writers refuse to write when `format_version` exceeds theirs; decode entries as ordered JSON objects and round-trip unknown keys (test: inject a foreign key, rewrite, expect it preserved). The app-side catalog is a union keyed by `(archive_id, content_sha256)`; Deleter and Restorer preconditions are scoped to the archive whose volume is mounted.

### M5. Job store schema, location, locking and sleep behaviour are hand-waved
Spec: JobState and JobStore.
Enumerated steps: `planned, probed, downloading, verified, thumbnailed, cataloged, deletable, deleted, done, failed, skipped`. Problems: `probed` has no disk fact and re-probing a local asset reads the whole file, so the probe result must be stored with a timestamp and treated as advisory; `deletable` is not a state but a runtime predicate (cataloged ∧ fetchable ∧ `canPerform(.delete)`), which the Deleter section already says, so remove it from the stored machine; `done` adds nothing over `deleted`; `thumbnailed` failure must carry attempts or it loops. No schema, filename, or concurrency rule is given, and the harness bundle has its own container, so harness jobs are invisible to the app. Sleep: a wall-clock 180 s watchdog fires spuriously after wake; USB re-enumerates so every in-flight download is stale.
Change: job file `jobs/<jobId>.json` with `{ schema_version, job_id, archive_id, volume_uuid, created_at, updated_at, concurrency, assets: [{ uuid, photos_identifier, expected_sha256?, step, attempts, last_error, probed_at, locality }] }`; exclusive `flock` on the file for the process lifetime and refusal when another holder exists; `ProcessInfo.beginActivity(.idleSystemSleepDisabled)` during transfers; watchdog on `SuspendingClock`; on wake or volume state change cancel in-flight requests and re-derive. Add the derivation table (step, disk fact, library fact, action) to the spec; it is currently one sentence.

## Low

### L1. Manifest sort key and human readability
Sorting by `creation_date` on every rewrite is fine for a projection; irrelevant once C1 lands. Add `relative_path` first in each entry so a human scanning the file sees the file name before the hash.

### L2. `sizeBytes` non-optional in `AssetRecord`
Plan Task 2 makes `sizeBytes: Int` while the spec allows nil; the classifier excludes nil-size assets, which is consistent, but the exclusion reason must reach the manifest-free scan summary so the app can say why small imports were skipped. Already `sizeUnknown`; keep.

### L3. Adopted `moment_name` is the only place-like data the old archive has
Do not drop it; `group_name` (M2) preserves it and lets the app show "Barking Park" for adopted entries without a geocoder.

## Proposed entry shape (v2, one JSONL line, projected into the manifest)

```
{ "content_sha256", "size_bytes", "relative_path" (NFC), "rendered_path"?, "thumbnail_path"?,
  "adjustments_path"?, "has_adjustments", "media_subtypes", "duration_seconds",
  "pixel_width", "pixel_height", "group_name", "archived_by", "archived_at",
  "archived_at_precision", "creation_date", "creation_date_offset_source",
  "latitude", "longitude", "altitude", "status": "ok|needs_hash|missing",
  "assets": [ { "photos_identifier", "cloud_identifier"?, "original_filename",
                "creation_date", "is_favorite", "is_hidden", "album_titles",
                "archived_at", "deleted_at"? } ],
  "restores": [ { "restored_at", "photos_identifier" } ],
  "adopted_from": [ { "file", "session_id", "uuid" } ] }
```

Sanity check performed: re-read the ask against the six review areas; every area has at least one finding with a concrete scenario and a schema, rule, or test. No files were written.

result: Reviewed the engine's manifest v2, layout, v1 adapter, job state machine and slice 1 AssetRecord; 2 critical (single rewritten manifest on a flaky exFAT drive, "unfetchable means deleted" without a cataloged precondition), 6 high (hash-key collapse of duplicate assets, edits and albums lost on delete, v1 field shape mismatches, archived_path resolution, repeatable adoption, partial-file handling), 5 medium, 3 low, each with a proposed schema, rule or test.