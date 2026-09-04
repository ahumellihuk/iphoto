# What the git history says about osxphotos, AppleScript, and PhotoKit (2026-09-04)

Reconstructed from `backup/pre-public-history` (30 commits, 2026-01-23 to 2026-02-15), the historical `INVESTIGATION.md`, `TODO.md`, and `CLAUDE.md` at commit 7582b4e (all trimmed from the public repo), and the two "working" commits of 2026-02-09.

## Timeline

| Date | Commit | What happened | Evidence recorded |
|---|---|---|---|
| 2026-01-23 | a14ae10 | Initial build on the osxphotos CLI: 4 parallel workers, three strategies per iCloud video (default export, `--use-photokit`, `--use-photokit --download-missing`), stdout parsing because osxphotos exits 0 with missing files | "osxphotos unreliable with iCloud-full scenario (videos not in local cache)". "Manual export from Photos.app also fails when iCloud is full." |
| 2026-01-23 | 1511b8d | Same day: osxphotos replaced by AppleScript `export ... with using originals`, lookup by filename, 3 retries | "Works when iCloud storage is full (proven with 1.6GB video)". "AppleScript API is flaky (retry logic added)". "Testing needed with real 26-video batch." |
| 2026-01-30 | 7582b4e | INVESTIGATION.md: AppleScript is now failing too | One successful local export, then silent failures. iCloud video returns SUCCESS in 13.9 s with no file. `-1712` timeouts. Four hypotheses, none confirmed. PhotoKit named "Option 2 (Recommended)" but never tried. |
| 2026-02-09 | 042c0c1 | "working": the fixes that made AppleScript hold | Activate Photos before each export; responsiveness probe; quit and relaunch Photos on timeout or missing file; poll for the file up to 90 s; 1 h timeout for iCloud videos; delete stale zero-byte files; fuzzy match for `IMG_1234 2.MOV` renames; skip re-export when a same-size staged file exists. AppleScript `delete` fails with `-10000`, replaced by the "Ready to Delete" album via photoscript. |
| 2026-02-09 | 639ffda | Lookup switched from filename to `media item id` | Duplicate filenames were matching the wrong item. |
| 2026-02-13 to 15 | refactors, release | Parallel exporter removed, sequential only. Public history squashed. | |
| 2026-09 (uncommitted) | working tree | osxphotos broke on a newer Photos schema; direct SQLite fallback added | `no such table` from osxphotos on macOS 26/27. |

## What actually fell short, and why

**osxphotos as an exporter.** It was used for one day, through its CLI, with four concurrent workers, while iCloud storage was full. Its own PhotoKit path was tried only as the third fallback with a 5x timeout multiplier and no per-request stall guard. The recorded failure is "videos not in local cache" and "missing" counts in its summary line. Nothing in the history isolates whether the cause was osxphotos, the experimental PhotoKit wrapper, parallel load, or the iCloud-full state. The initial commit itself notes that Photos.app's own manual export failed under the same condition, which points at the environment rather than the library.

**osxphotos as a scanner.** It worked for seven months and then broke on a schema change, which is exactly its documented weakness. The working tree now carries a hand-written SQLite fallback. For a sandboxed product this path is closed anyway: the App Store build cannot read Photos.sqlite at all.

**AppleScript.** It did not work either at first. The Jan 30 investigation shows the same two failure shapes PhotoKit is documented to have: a call that reports success with no file, and a call that never returns. What made it hold was not the API but the scaffolding around it: quit and relaunch Photos, poll for bytes on disk, long timeouts, retries, and byte-size verification before trusting anything. It has remained sequential and dependent on Photos.app being frontmost ever since. Deletion never worked through AppleScript at all.

**PhotoKit.** Never tried directly in this project. The Jan 30 document recommended it, the TODO listed a PyObjC proof of concept as "High Priority (This Week)", and the AppleScript fixes landed first. The only PhotoKit exposure was osxphotos's `--use-photokit` flag, under the worst conditions described above.

## Risks this history raises for the PhotoKit plan

1. **The iCloud-full condition is the real test environment.** Every failure in January happened with iCloud at capacity, and the user runs the tool in that state today. The research found no documentation on whether iCloud-full affects downloads. The spike must run on this Mac, in this state, not on a clean library.
2. **Both APIs lie in the same ways.** "Success with no bytes" and "never calls back" are documented for PhotoKit (forum threads, osxphotos's 300 s timeout) and were observed here for AppleScript. The mitigations that saved AppleScript apply unchanged: bounded waits, byte-size and checksum verification, retry with backoff. They must be in the spike from day one, not added after.
3. **There is no "restart Photos" lever in the sandbox.** Relaunching Photos.app was the single most effective AppleScript fix. PhotoKit downloads run in `cloudphotod`, which a sandboxed app cannot restart. If a download stalls, the only options are wait, retry, or tell the user. The spike must measure how often a stall recovers on retry alone.
4. **Enumeration may miss the videos that matter.** The ladder project found iCloud-only assets absent from PhotoKit fetches under Optimize Storage and fell back to AppleScript. If that reproduces here, the App Store build cannot even list the videos it exists to archive.
5. **Proxies instead of originals.** Mobile projects saw `writeData` return downscaled files. The current tool guards this by comparing size to the SQLite value. PhotoKit below macOS 27 has no public size, so on 26 the guard would be checksum-only against nothing. This Mac is on 27.0, so `dataSize` can be tested immediately.
6. **Moments and place names disappear.** The scanner's moment grouping and smart thresholds come from SQLite tables. PhotoKit on macOS has no moments and no place names. The selection UX must be rebuilt on date and location clustering, and the ML branch's use of osxphotos labels and scores has no PhotoKit equivalent.
7. **Deletion moves from a workaround to a real API, with a known bug.** `deleteAssets` is the fix for the `-10000` album workaround, but iOS 26 has a reported case where the completion never fires. Verify by re-fetching the asset, not by trusting the callback.
8. **Sequential is not a law.** AppleScript forced one export at a time. PhotoKit permits concurrent requests, and osxphotos issue #1504 shows the daemon can be slow under load. Concurrency is a variable to measure, not assume.

## What the history does not support

- It does not show that PhotoKit is unreliable for large iCloud videos. That claim was never tested here.
- It does not show that osxphotos's PhotoKit wrapper failed for API reasons rather than environmental ones.
- It does not show that AppleScript is inherently reliable. It shows that heavy scaffolding made it reliable enough.

## Recommendation for the spike

Run it in two stages so the expensive Swift work is gated by a cheap answer:

1. **One-day Python pre-spike on this Mac.** Use pyobjc and osxphotos's `photokit` module, which already wraps `PHAssetResourceManager` with network access and a timeout, against the same iCloud-only videos the tool archives today. Record per video: enumerable by PhotoKit, `dataSize` reported, bytes downloaded, checksum match against the AppleScript export of the same asset, stall count, retry recovery. Also measure the private `fileSize` key for the macOS 26 fallback question.
2. **Swift spike only if stage 1 passes** on enumeration, byte-exact originals, and stall recovery. Stage 2 adds the sandbox, the entitlement, the delete dialog, security-scoped bookmarks across a drive reconnect, and the re-import round trip.

Go/no-go thresholds to set before starting: at least 95 percent of iCloud-only videos enumerable and byte-exact after retries, and no stall that fails to recover within three attempts.
