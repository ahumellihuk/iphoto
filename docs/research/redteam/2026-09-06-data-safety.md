# Red team: data safety (2026-09-06)

Fable 5.1 reviewer report, verbatim.

# Hostile review: engine core spec and slice 1

Scope: `docs/specs/2026-09-06-engine-core.md` (spec), `docs/plans/2026-09-06-engine-slice-1.md` (plan), the spike code the spec ports, and the Python tool the adapter must read. Severity: Critical = footage loss or silent corruption; High = ambiguous state needing manual recovery; Medium = recoverable with a clear error; Low.

## Critical

### C1. Final-path streaming plus `removeItem` on the destination overwrites an earlier verified archive
Spec: "Downloader and Verifier" ("Destination is the final path on the drive; there is no staging directory"), "Archive layout" (collision suffix from the content hash), spike `Downloader.download` (`try? FileManager.default.removeItem(at: dest)`).
Scenario: Session 1 archives `IMG_0001.MOV` from phone A to `2025/2025-11-13 London/IMG_0001.MOV`, verifies, deletes from Photos. Weeks later phone B's `IMG_0001.MOV`, same day, same place, is planned. The collision rule needs the content hash, but the hash does not exist until the download finishes, and the download writes to the final path. The port of the spike deletes the existing file and streams over it. Phone A's only copy is gone; Photos no longer has it. If instead the engine keeps the file and the verifier sees a mismatch, the spec says "the file is removed", which deletes it too.
exFAT makes this worse: it is case-insensitive, so `IMG_0001.mov` and `IMG_0001.MOV` are the same file to the drive and different strings to the engine; NFC/NFD Unicode variants of a filename behave the same way.
Mitigation: download to `<final>.part-<jobid>` and rename only after verification; the Downloader must never remove a path it did not create in this attempt; the collision check runs against the manifest (case-folded, NFC-normalized) and the filesystem before download, and any pre-existing file at the target is a hard stop, never a delete. Verifier removes only `.part` files. Test: pre-place a foreign file at the target path, run archive, assert the foreign file's hash is unchanged.

### C2. Read-back verification can be served from the page cache and proves nothing about the drive
Spec: "Verifier then re-reads the file from the drive... only the read-back result counts."
Scenario: 700 MB file streamed to an exFAT USB SSD through an RTL9210 bridge (the drive in memory that hung the Python runs with USB resets). Read-back immediately after the write hits the unified buffer cache; the hash matches; the entry is cataloged; the Deleter precondition re-hash in the same session also hits cache; the user clicks Delete. The bridge had dropped writes during a reset. The bytes on media are wrong; nothing checked them.
Mitigation: after close, `fcntl(F_FULLFSYNC)` on the file; open the read-back with `F_NOCACHE` (or `F_RDADVISE`/`preadv` with cache bypass); additionally require that the Deleter's precondition hash be computed with `F_NOCACHE`. Stronger: the delete step is allowed only for entries cataloged in a previous mount session of the volume (record the volume mount time or a mount counter in the job store). Test: simulate with a file whose on-disk bytes are patched via a second file descriptor after the cached read.

### C3. Archive captures the unedited `.video` resource and deletes the user's edit
Spec: data model (`hasAdjustments` recorded, never used), Downloader (`.video` resource), Restorer (adds only `.video`).
Scenario: A parent trimmed a 12-minute recital to the 2 minutes that matter and applied a slow-motion range or a filter. `hasAdjustments == true`. The engine archives the 12-minute original, verifies it, and the Deleter removes the asset. The trim, the slo-mo range selection (stored as adjustment data for high-frame-rate captures), and any Cinematic-mode focus edits are destroyed. Restore produces the untrimmed original; the user thinks the app corrupted their video. This is silent loss of work, which the family experiences as loss of the video.
Mitigation: slice 1 should carry `mediaSubtypes` and `modificationDate` in `AssetFacts`; the classifier excludes `hasAdjustments == true`, `.videoHighFrameRate`, and `.videoCinematic` with their own reasons until a later spec archives `.fullSizeVideo` plus `.adjustmentData` alongside the original and restores all three. Test: classifier test for each subtype and for `hasAdjustments`.

### C4. `.fullSizeVideo` fallback archives a rendition and calls it the original
Plan Task 4, `originalVideoResource(for:)`: `resources.first { .video } ?? resources.first { .fullSizeVideo }`.
Scenario: An asset whose `.video` resource is not listed (seen in the wild for some iCloud states and for edited videos whose original was never re-fetched) gets its rendered edit archived under `original_filename`, hashed, verified against itself, and the asset deleted. The camera original is gone; the archive holds a re-encoded file.
Mitigation: the fallback becomes an exclusion (`noOriginalVideoResource`), not a substitute. The plan's `hasOriginalVideoResource` should be true only when a `.video` resource exists.

### C5. "Not fetchable means deleted" without requiring a verified archive first
Spec: "JobState and JobStore" ("an asset that is no longer fetchable is `deleted`").
Scenario: A job of 60 assets is planned. Before the download of asset 41 starts, the user's spouse deletes it on their iPhone; iCloud sync removes it here. Kill -9 or a normal restart follows. Resume re-derives step from library state: asset 41 is not fetchable, so it becomes `deleted`, then `done`. The job summary says 60 archived. There is no file and no manifest entry. The family believes it is on the drive.
Mitigation: step derivation is monotonic and gated: `deleted` may be derived only from `deletable` or `deleted` with a manifest entry whose file re-hashes; any other unfetchable asset becomes `skipped(vanishedBeforeArchive)` and is reported separately. Test: synthetic disk-state test with an unfetchable asset at `planned`.

## High

### H1. Restore is not idempotent across a crash between creation and manifest write
Spec: "Restorer" ("After completion... Records the restore in the manifest").
Scenario: `performChanges` completes, the new asset exists, the app dies before the manifest rewrite (or the drive is unplugged so the manifest on the drive cannot be written at all). Next attempt: `photos_identifier_at_archive` is not fetchable, `restores[]` is empty, hash matches, so it creates a second copy. Two copies of a 4 GB video in a library that is already over its iCloud quota.
Mitigation: write a `restore_intent {started_at, placeholder_identifier}` into the manifest (and a mirror in the app container) before `performChanges`; on resume, fetch the placeholder identifier first, and also search by `originalFilename + duration ±0.5 s + pixel size + creationDate ±1 s` before creating. If the post-creation verification fails, delete the created asset in the same job or mark the entry `restoreUnverified` and refuse further restores until a human decides.

### H2. Permission downgrade or library switch makes every asset "deleted" and every restore "safe"
Spec: JobStore derivation; Restorer refusal rule.
Scenario: The user grants Limited Library access (or the System Photo Library is switched, or access is revoked and the harness runs with an empty fetch). Every identifier returns nil. Resume marks all `deletable` assets `deleted` and the Restorer's "still fetchable" guard passes for everything, so a restore creates duplicates of assets that are still present in the real library.
Mitigation: before any derivation or restore, prove the library is the same and fully readable: `PHPhotoLibrary.authorizationStatus(for: .readWrite) == .authorized` (never `.limited`), the total video count within a tolerance of the last scan, and a canary fetch of three known-present identifiers recorded at plan time. Failure is `libraryUnavailable`, which pauses the job like `needsReconnect`.

### H3. The manifest is a single file on a slow removable exFAT volume rewritten thousands of times
Spec: "Data model" (one pretty-printed JSON file, rewritten atomically after every entry change).
Scenario: 4,000 entries, two concurrent downloads finishing, rename on exFAT during a USB reset. exFAT has no journal and no directory fsync; the temp file and the target can both be truncated. `load` fails; every entry is now "not in manifest", the Deleter refuses (good), the Restorer cannot find anything (bad), adopted Python entries are gone from the v2 view. Concurrent writes from two processes (app plus harness) interleave read-modify-write and drop entries.
Mitigation: serialize manifest writes through one actor; keep `archive-manifest.json.bak` rotated before each write and a mirror of the manifest in the app container; on load, try main, bak, mirror, and reconcile by re-hashing the files on disk; a lock file at the archive root with the process id and a heartbeat. Test: corrupt the main file and assert full recovery from bak.

### H4. Delete watchdog and batching create a dialog the engine has already given up on
Spec: "Deleter" (50 per block, 120 s watchdog, then re-fetch).
Scenario: Batch 1's dialog appears, the user walks away, the watchdog fires at 120 s, the re-fetch finds everything present, the batch is `failed`, and the loop starts batch 2's `performChanges`, which queues behind the modal. The user returns, clicks Delete on dialog 1, then Delete on dialog 2. The job store says batch 1 failed; the library says both gone. A retry offers batch 1 again for "deletion" and finds nothing; a support ticket says "the app deleted my videos and reported an error".
Mitigation: never start a second `performChanges` while one is outstanding; after the watchdog, the state is `awaitingDialog`, polled by re-fetch every 10 s for up to an hour; no further batch until resolved. Record the batch's identifiers before submission so a later resume can attribute the disappearance.

### H5. Restore fabricates or loses metadata Photos held
Spec: "Restorer" (date, location, favorite only).
Scenario: The video had a title, a caption, keywords, was in three albums, a Memory, was hidden, and its creation date had a stored timezone. Restore brings back a file with the UTC instant, the Mac's current timezone, no title, unhidden. A hidden video from a family member is now visible in the shared library view. Spike measured 0.000 s delta on the instant, which is not what a user sees.
Mitigation: capture `isHidden`, title (via `PHAssetResource`-less route is not available; use `PHAsset` properties that are public), album memberships (`PHAssetCollection.fetchAssetCollectionsContaining`), and the embedded QuickTime creation date with offset at catalog time; restore `isHidden` and album membership; store the offset and verify the displayed local time, not just the instant. At minimum the classifier excludes hidden assets by default with a visible count.

### H6. Adopter treats an empty v1 checksum as a content hash
Spec: "Adopting the existing archive" (maps `checksum` to `content_sha256`). Evidence: `cli.py` writes `checksum or ""`; the Python `verify` skips hashing when the checksum is empty and counts the entry as verified, so nobody has ever noticed these entries.
Scenario: An entry with `checksum: ""` is adopted; `content_sha256` is `""`. It collides with every other empty-checksum entry under the content-hash key; the Restorer's hash check compares the file's hash to `""` and refuses forever; the optional verify job says "verified" if it mirrors the Python logic. Separately, the same uuid appears in two session manifests (archive succeeded, manual album delete never happened, user re-selected it) with different `moment_name` folders; the adapter keeps one and silently drops the other, or keeps both under one key.
Mitigation: `content_sha256` is non-optional and must be 64 hex characters; entries without it become `unverifiedAdopted` with a separate key (`legacy:<uuid>:<session_id>`) and cannot be restored or used as a delete precondition until the verify job hashes the file and, if two entries hash equal, merges them. Missing files are reported as `missingOnDrive`, never dropped. `archived_path` is absolute in v1 (`/Volumes/<name>/...`); resolve by longest suffix match under the root, since the volume can mount as `/Volumes/<name> 1`. Fixture test must include an empty checksum, a duplicate uuid, and a missing file.

### H7. Edits between plan and delete are not detected
Spec: "Deleter" preconditions (manifest entry, file hash, `canPerform(.delete)`).
Scenario: The archive of a long job took two evenings. On the second evening the user trims a video that was cataloged on the first. The Deleter's preconditions all pass (the archived file still hashes; the original resource is unchanged), the asset is deleted, the trim is lost.
Mitigation: record `modificationDate` and `hasAdjustments` at `cataloged`; the Deleter refuses any asset whose `modificationDate` moved or whose `hasAdjustments` flipped, with reason `changedSinceArchive`. Slice 1 must add `modificationDate` to `AssetFacts` now so the field exists in every record.

## Medium

### M1. Identical bytes in two assets collapse into one manifest key
Spec: "Data model" (key `contentSHA256`).
Scenario: The same video was AirDropped twice or saved from WhatsApp twice; two assets, one hash. The second catalog overwrites the first entry's `photos_identifier_at_archive`; both are deleted; restore returns one. No bytes are lost, but the count the user sees is wrong and the second identifier vanishes from the record. Mitigation: `photos_identifiers_at_archive` is a list; catalog appends; the Deleter and Restorer reason per identifier.

### M2. Manual re-import defeats the Restorer's duplicate guard
Spec: "Restorer" (checks only identifiers). Scenario: The user drags the file from the drive into Photos, then later clicks Restore. Duplicate. Mitigation: the candidate search in H1, plus a hash probe of any candidate before creation.

### M3. Sleep and App Nap during long runs
Spec: Downloader watchdog. Scenario: The Mac sleeps at 40 minutes; every in-flight `requestData` stalls; on wake the watchdog fires, three attempts burn 65 s of backoff each, the job marks assets failed. Not loss, but a family that leaves it overnight finds a wall of failures. Mitigation: `ProcessInfo.beginActivity([.userInitiated, .idleSystemSleepDisabled])` for the job's lifetime; treat wake as a resume, not a failure.

### M4. Volume identity is not part of the delete precondition
Spec: "VolumeAccess" (stores UUID and name). Scenario: Two drives with the same name; the bookmark resolves to the wrong one after a reformat; the archive root exists (a copy), the manifest is stale. Deleter preconditions re-hash files that exist on the copy, but the copy may be an older snapshot missing the newest entries, and the job store still points at paths. Mitigation: the Deleter checks the resolved volume UUID against the manifest's recorded UUID; mismatch is a hard stop.

### M5. Space floor and thumbnail generation on the drive
Spec: 2 GB floor; ThumbnailMaker reads the archived file via `AVAssetImageGenerator`. Scenario: Reading a 5 GB 4K file over a flaky bridge to make a thumbnail triggers the same USB resets that hung the Python runs, in the window between verify and delete. Mitigation: generate the thumbnail from the PhotoKit asset (`PHImageManager`) before download, not from the drive; verify job separately.

### M6. Live Photo and burst edge cases are not stated
Spec: "LibraryScanner". `fetchAssets(with: .video)` excludes Live Photos (they are images with a paired video resource), which is correct, but the spec does not say so, and a future "include Live Photo videos" change would archive a `.pairedVideo` resource and then delete the still. Write the exclusion down and add a classifier test for `mediaSubtypes.contains(.photoLive)`.

## Low

### L1. Harness `requestAuthorization` treats `.limited` as failure, but only in the harness
Plan Task 6. The engine should refuse `.limited` itself (see H2), not rely on the harness's `guard`.

### L2. Job store lost with the container
Spec: JobStore in the app container. Reinstall wipes it; derivation from disk and manifest covers archive state, but the plan's exclusion counts and canary identifiers are gone. Keep a copy of each job file beside the manifest on the drive.

### L3. `AssetRecord.uuid` parsing
Plan Task 2. Splitting on `/` and falling back to the bare string means a malformed identifier becomes a "uuid" that `fetchAsset` will happily try twice. Validate the UUID shape and fail loudly.

## Ordered fixes for slice 1

1. Add `mediaSubtypes`, `modificationDate`, `isHidden` to `AssetFacts` and `AssetRecord`; exclude `hasAdjustments`, high-frame-rate, cinematic, and hidden by default with reasons (C3, H5, H7).
2. Remove the `.fullSizeVideo` fallback; treat it as `noOriginalVideoResource` (C4).
3. Reject `.limited` authorization inside the engine (H2, L1).
4. Amend the spec before slice 3: `.part` files plus rename, `F_FULLFSYNC` and `F_NOCACHE` verification, monotonic step derivation, manifest mirror and lock (C1, C2, C5, H3), restore intent record (H1).

result: Hostile review of the engine-core spec found 5 critical paths to footage loss (final-path overwrite on filename collision, cache-served verification, edits destroyed by archiving only the unedited original, `.fullSizeVideo` fallback, "unfetchable means deleted" without a verified archive), 7 high ambiguity risks, and 6 medium/low, each with a concrete mitigation; the report is above in this message.