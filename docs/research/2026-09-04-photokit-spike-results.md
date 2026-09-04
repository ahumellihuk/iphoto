# PhotoKit spike results, stage A (2026-09-04)

Spec: [2026-09-04-photokit-spike.md](../specs/2026-09-04-photokit-spike.md). Raw data: `spike/scratch/results/A1-2026-09-04T122929Z.jsonl` and `A1size-*.jsonl` (gitignored, on this Mac).

## Environment as run

macOS 27.0 (beta), sandboxed bundle signed with the Photos library, user-selected file, and app-scope bookmark entitlements. Photos.app running. iCloud Photos on, Optimize Mac Storage on, iCloud storage at capacity. Sample of 31 videos, 15.1 GB: 10 small, 10 medium, 6 large iCloud-only (the library had only six iCloud-only videos over 1 GB left after today's archive run), 5 "local" controls. Ten paired videos had been AppleScript-exported minutes earlier for reference hashes, which cached their originals in the library, so their downloads exercised the cache path, not iCloud.

## A1 scoring against the thresholds

| Measure | Result | Gate |
|---|---|---|
| Enumeration under sandbox, iCloud-only | 26 of 26 found by direct fetch and by sweep | PASS |
| Byte-exact download, iCloud-only | 26 of 26 size-exact within three attempts; 25 on the first attempt | PASS |
| Paired hashes identical to AppleScript export | 10 of 10 | PASS |
| Stall recovery | 0 stalls; one transient network error (3169) recovered on attempt 2 after 5 s | PASS |
| Public size before download, iCloud-only | 16 of 26 | FAIL against 95 percent, see finding 2 |
| Locality agrees with database flag | 8 of 31 | not meaningful, see finding 3 |
| Throughput, cold iCloud downloads | median about 42 MB/s versus 50 to 59 MB/s for AppleScript on the paired set, about 0.75x | PASS (soft) |
| Cache side effect | 31 of 31 originals present in the library after download | measured, see finding 4 |

The two hard gates that matter for the product direction, enumeration and byte-exact download, passed cleanly. The ladder project's "iCloud-only assets invisible to PhotoKit" failure did not reproduce under sandbox on this library.

## Findings

1. **Downloads are reliable and byte-exact.** Every iCloud-only video downloaded with sizes equal to the database original size, and every paired one hashed identically to the AppleScript export. No proxy substitution was observed. The one failure was a `PHPhotosErrorDomain 3169` network error on a 779 MB file, recovered by the first retry. No download stalled; the 180 s inactivity watchdog never fired.

2. **Public `dataSize` is nil for non-camera videos.** The ten assets without a size are all `.mp4` files, 720p, imported from apps or transfers (WhatsApp-style names, a `Flow_VID_` file), and each exposes only the original video resource. Every camera `.MOV` reports an exact size, including all six large ones. The private `fileSize` key returns 0 for the same ten, so it is no better. Caching the original does not change this. Consequence for the product: size is known for the videos that matter for archiving, and unknown mostly for small app imports, which need a duration-and-resolution estimate or are simply below any threshold. On macOS 26, where `dataSize` does not exist, the private key gave the same answers as the public one here, but it remains unusable for App Store review.

3. **The Python scanner's locality flag is wrong, not PhotoKit.** All five "local" controls failed the network-disallowed probe with error 3164 and then downloaded at network speeds. The scanner computes `is_local` as the maximum availability over all internal resources, so a local thumbnail marks an asset local. PhotoKit's probe is the reliable signal and the product should use it. A separate task has been flagged to fix the Python tool, where the wrong flag shortens iCloud timeouts.

4. **Downloading through PhotoKit caches the original in the library.** After every download the network-disallowed probe succeeded, and this held for 31 of 31. The product must budget internal disk for the library cache as well as its own staging copy, and cannot control when macOS evicts the cached original. This also explains why the AppleScript paired exports made their assets local.

5. **Direct fetch by identifier works with the `UUID/L0/001` form.** The bare UUID does not resolve. The sweep of all videos took under a second for 5,343 assets.

6. **Permission attribution.** Launched from a shell, macOS auto-denied Photos access without a prompt. Launched through LaunchServices it prompted and granted. The product will always launch normally, but any CLI or test harness must use `open`.

## What A1 does not show

- Behavior with Photos.app quit (A2) and under concurrency (A3): not yet run.
- Cold-download behavior on more than six files over 1 GB, since the library ran out of them today.
- Whether the cached originals get evicted, and how quickly.
- Anything about deletion, re-import, or bookmark survival (stage B).

## Next

A2 and A3 need a fresh sample because everything in A1 is now cached. Sample selection runs from a terminal with Full Disk Access, excluding the A1 set, and the harness `--only-cloud` flag skips any video whose original the probe finds local, so a stale database flag cannot contaminate the download measurements again.
