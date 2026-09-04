# Spec: PhotoKit spike (2026-09-04)

Status: approved for stage A on 2026-09-04. Immutable; corrections go in a dated `UPDATE:` header at the top.

## Why

The commercial product is a sandboxed native macOS app built on PhotoKit (see [north star draft](../research/2026-09-04-market-synthesis.md) and the [history review](../research/2026-09-04-history-lessons.md)). PhotoKit was never tried in this project; AppleScript was made to work by scaffolding. Before any product planning, this spike measures whether PhotoKit, from inside App Sandbox, on this Mac in its real state, can enumerate, size, download byte-exact, delete, and re-import large iCloud-only videos. It is a go/no-go gate.

## Non-goals

No UI. No catalog. No shipping code. No changes to the Python tool beyond a small sample-selection script. Nothing here is reused verbatim in the product, though the engine shape is expected to carry over.

## Environment

- This Mac: macOS 27.0 beta, Xcode 27.0 beta, Swift 6.4, Apple Development signing identity present.
- Photos library: iCloud Photos on, Optimize Mac Storage on, iCloud storage at capacity. This is the condition every January failure occurred in and the condition the product's customers are in.
- Archive drive: `/Volumes/AcerFA200/Photos-archive`, with about 740 already archived videos and manifests carrying SHA-256 checksums.
- The spike must not run while `iphoto archive` is running. The harness checks for a live `iphoto` process and refuses to start.

## Layout

```
spike/
  select_sample.py          Python: picks the sample from the SQLite scanner, writes sample.json
  ground_truth.py           Python: AppleScript-exports the paired subset, records SHA-256 into sample.json
  PhotoKitSpike/            Swift: sandboxed app bundle with a headless CLI entry
    Sources/...
    Info.plist
    PhotoKitSpike.entitlements
    Makefile                build, sign, run
  results/                  JSONL per run (gitignored), summaries copied to docs/research
```

## Sample

Selected by `select_sample.py` using the existing `_scan_videos_sqlite` in the scanner, which reports size, locality, and UUID from the database. Written to `spike/sample.json`.

| Band | Count | Criterion |
|---|---|---|
| Small iCloud-only | 10 | not local, size under 200 MB |
| Medium iCloud-only | 10 | not local, 200 MB to 1 GB |
| Large iCloud-only | 10 | not local, over 1 GB, must include the largest video in the library |
| Local control | 5 | locally available, any size |

Within each band selection is random with a fixed seed so runs are repeatable. Expected download volume 20 to 30 GB. The harness checks free space on the scratch volume before starting and requires 1.5x the sample's total size.

Ten of the iCloud-only videos, spread across bands, form the **paired subset**. `ground_truth.py` exports each through today's AppleScript path into a scratch folder and records the SHA-256 and byte size. These are the only byte-exactness references; database size is the reference for all others.

## Stage A: read-only measurements

Runs as the sandboxed bundle, with the Photos library entitlement, the usage string, and a user-selected scratch folder obtained through an open panel and persisted as a security-scoped bookmark. Nothing in stage A modifies the library.

Per video, in order:

1. **Enumeration.** `PHAsset.fetchAssets(withLocalIdentifiers:)` for the UUID and, separately, membership in a `fetchAssets(with: .video)` sweep. Record found or missing for both. This is the ladder risk and is measured under sandbox, which no prior project has done.
2. **Resources.** `PHAssetResource.assetResources(for:)`. Record the resource types present and the `originalFilename`.
3. **Size.** `dataSize` on the `.video` resource (public on macOS 27) and `value(forKey: "fileSize")` (private, for the macOS 26 fallback question only, never for the product). Record both against the database size.
4. **Locality.** `writeData` with `isNetworkAccessAllowed = false`. Expected: local control succeeds, iCloud-only fails with `PHPhotosError` code 3164. Record the actual outcome against the database locality flag.
5. **Download.** `writeData` with `isNetworkAccessAllowed = true` and a `progressHandler`. Stall detection: no progress callback for 180 s cancels the request. Absolute cap 3600 s. Up to three attempts with backoff of 5, 15, 45 s. Record per attempt: outcome, error domain and code, bytes written, wall time, progress samples, stall count. After success: SHA-256 and byte size against the reference.
6. **Cache side effect.** Immediately after a successful download, repeat step 4. If it now succeeds, the original was cached in the library. Record it. The Python side additionally re-reads `ZLOCALAVAILABILITY` for the sample after the run.

Run variants, each a separate run with its own JSONL:

- A1: Photos.app running, concurrency 1, full sample.
- A2: Photos.app quit, concurrency 1, the ten paired videos.
- A3: concurrency 2 then 4, the medium band, Photos.app running.

## Stage B: destructive measurements

Runs only after stage A passes and only with a separate explicit go from the user for each run. Operates only on videos whose archive copy is checksum-verified against a manifest.

1. **Delete.** `PHAssetChangeRequest.deleteAssets` for two videos in one change block. Record the dialog text, whether the completion fires, elapsed time, and the result of re-fetching the identifiers afterwards. Verification is by re-fetch, never by the callback alone.
2. **Re-import.** `PHAssetCreationRequest` from one archived file with explicit `creationDate` and `location`. Record the new identifier, and re-read date and location from the created asset. Then delete the re-imported asset the same way as above, again by explicit go.
3. **Bookmark survival.** With the archive drive selected through the open panel and bookmarked: eject, reconnect, resolve the bookmark, and attempt a write. Record `isStale` and the outcome.

## Thresholds, fixed before running

| Measure | Pass |
|---|---|
| Enumeration under sandbox | at least 95 percent of iCloud-only videos found by both fetches |
| Size available before download | `dataSize` present and equal to database size for at least 95 percent |
| Locality detection | at least 95 percent agreement with the database flag |
| Byte-exact download | at least 95 percent of iCloud-only videos match the reference within three attempts |
| Stall recovery | no video that stalls fails to recover within three attempts |
| Paired hashes | all ten paired videos hash-identical to the AppleScript export |
| Throughput | median bytes per second within 0.5x of AppleScript on the paired subset; soft signal, not a gate |
| Delete | completion fires or re-fetch confirms removal, for both videos |
| Re-import | date within one second and location within 10 m of the values set |
| Bookmark | resolves and writes after reconnect, or fails with a documented error the product can recover from with a re-select prompt |

A failed gate does not end the product plan. It changes it: enumeration or download failure means the App Store build cannot be PhotoKit-only and the direct build with an AppleScript fallback becomes the first release; a size failure means the macOS 26 fallback is estimate-based.

## Output

- `spike/results/<run-id>.jsonl`, one line per video per attempt, schema in `Sources/Record.swift`.
- `docs/research/<date>-photokit-spike-results.md`: summary table per threshold with pass or fail, the failure taxonomy by error code, throughput, and the raw notable events. Written by hand from the JSONL.

## Risks

- macOS 27 beta may itself be the source of failures. Any failure is checked against the Apple Developer Forums for a known 27 regression before being counted.
- The Photos permission prompt attaches to the spike bundle. Revoking and re-granting is done in System Settings, Privacy and Security, Photos.
- A stalled `cloudphotod` cannot be restarted from the sandbox. If a stall persists across three attempts and a later manual retry succeeds, that is recorded as a recoverable-by-time failure, distinct from a hard failure.
- Downloads consume internal disk twice if the library caches the original. Stage A measures this; the harness refuses to start below the space threshold.
