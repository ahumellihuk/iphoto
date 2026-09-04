# PhotoKit spike results, stage A (2026-09-04)

**Stage A verdict: PASS.** Enumeration, byte-exact download, stall recovery, and throughput all cleared their gates across A1, A2, and A3. The size gate failed only for non-camera `.mp4` imports. Stage B (delete, re-import, bookmark survival) has not run.

Spec: [2026-09-04-photokit-spike.md](../specs/2026-09-04-photokit-spike.md). Raw data: `spike/scratch/results/A1-*.jsonl`, `A1size-*.jsonl`, `A2-*.jsonl`, `A3c2-*.jsonl`, `A3c4-*.jsonl` (gitignored, on this Mac).

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

## A2: Photos.app quit

Fresh sample (seed 7, A1 set excluded): 15 small, 5 medium, 5 "local" controls, run with `--only-cloud` so the probe decides what is a cold download. Photos.app was quit before the run and stayed quit (`photos_running=false` recorded).

| Measure | Result |
|---|---|
| Cold downloads attempted | 11 (5 medium, 1 small, 5 controls that were iCloud-only despite the database flag) |
| Byte-exact on first attempt | 11 of 11 |
| Stalls, errors | none |
| Throughput, medium band | 45 to 54 MB/s, median 46 |
| Skipped because the probe found the original local | 14 of 15 small videos |

Findings:

7. **Photos.app does not need to be running.** Downloads went through the system daemons at the same speed as A1 or slightly faster. This removes AppleScript's most awkward runtime dependency.
8. **Optimize Mac Storage keeps small originals local.** Fourteen of fifteen small iCloud videos were already local under the database's "not local" flag. The database flag is wrong in both directions; only the PhotoKit probe is trustworthy.

## A3: concurrency 2 and 4

Five medium videos each, Photos.app running.

| Concurrency | Files | Total | Wall time | Aggregate | Per-stream |
|---|---|---|---|---|---|
| 1 (A2 medium, reference) | 5 | 3.6 GB | about 76 s | about 47 MB/s | 45 to 54 MB/s |
| 2 | 5 | 3.0 GB | 57.7 s | about 53 MB/s | 25 to 43 MB/s |
| 4 | 5 | 2.7 GB | 44.7 s | about 61 MB/s | 14 to 26 MB/s |

All 10 byte-exact on the first attempt, no stalls, no errors.

Finding 9. **Concurrency helps only modestly.** Aggregate throughput rises from about 47 to about 61 MB/s between one and four streams, while per-stream speed falls proportionally, which points at a shared network ceiling near 60 MB/s on this connection. Two concurrent downloads is the sensible product default; four adds little and multiplies partial files on failure.

## What stage A does not show

- Cold-download behavior on more than six files over 1 GB, since the library ran out of them today. The largest cold file measured was 1.7 GB.
- Whether the cached originals get evicted, and how quickly.
- Anything about deletion, re-import, or bookmark survival (stage B).
- Behavior across sleep, or on macOS 26.

## Stage A summary for the north star

PhotoKit from inside App Sandbox can be the product's only download engine on macOS 27. It enumerated every iCloud-only video, downloaded every one byte-exact, matched AppleScript hashes on all paired files, recovered its only transient error on the first retry, and did so with Photos.app closed and at about 0.75 to 1.0x AppleScript's speed. The costs are known: sizes are unavailable for non-camera imports, downloads cache the original in the library, and the product must carry its own locality probe because no flag exists. Stage B remains the gate for deletion and restore.
