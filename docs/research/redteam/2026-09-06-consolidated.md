# Red team consolidation (2026-09-06)

Five Fable 5.1 reviewers examined the north star, the engine spec (v1), the slice 1 plan, and the spike evidence with different lenses: data safety, platform correctness, archive format and job state, product and App Store review, and plan executability. Their verbatim reports sit beside this file. This record lists every finding once, the disposition, and where the fix lands. The fixes are applied in [engine spec v2](../../specs/2026-09-06-engine-core-v2.md); the slice 1 plan is rewritten after the open decisions below are made.

Disposition key: **accepted** (in spec v2 or the plan), **decision** (needs the human owner), **rejected** (with reason), **deferred** (later slice or spec, tracked).

## Critical and high, all accepted

| # | Finding | Raised by | Fix lands in |
|---|---|---|---|
| 1 | Streaming to the final path and removing whatever is there can overwrite an earlier verified archive on a filename collision; exFAT is case-insensitive and does not normalize Unicode | safety C1, format H6, platform M6 | spec v2: `.partial` files, rename after verification, never delete a pre-existing file, collision check against the manifest with NFC and case folding before download, foreign file at target is a hard stop |
| 2 | Read-back verification is served from the page cache and proves nothing about the drive | safety C2, platform H2 | spec v2: `F_FULLFSYNC` after write, read-back and Deleter precondition hashes opened with `F_NOCACHE` |
| 3 | Archiving only the unedited original and then deleting destroys trims, slo-mo ranges, and cinematic edits | safety C3, format H2, product M4 | spec v2: assets with adjustments, high-frame-rate, or cinematic subtypes are excluded by default with their own reasons until an adjustments spec archives the rendered video and adjustment data alongside |
| 4 | `.fullSizeVideo` fallback archives a rendition and calls it the original | safety C4 | spec v2 and plan: fallback removed; only a `.video` resource counts as an original |
| 5 | "Not fetchable means deleted" marks vanished, never-archived assets as done | safety C5, format C2 | spec v2: monotonic derivation; `deleted` only from a cataloged entry whose file re-hashes; otherwise `failed(assetVanished)`; secondary match key (uuid, filename, creation date, size) |
| 6 | Permission downgrade, Limited Library, or a switched System Library make everything "deleted" and every restore "safe" | safety H2, product M2 | spec v2: `LibraryEnvironment` guard before any derivation or restore: authorized and not limited, video count within tolerance, three canary identifiers; failure pauses the job as `libraryUnavailable` |
| 7 | Single rewritten manifest on a slow, resetting exFAT drive is a single point of catalog loss | safety H3, format C1, product L4 | spec v2: append-only `archive-log.jsonl` is the truth; `archive-manifest.json` is a compacted projection with `.prev` and a container mirror; lock file; unparsable is an error, never "empty" |
| 8 | Restore is not idempotent across a crash between creation and manifest write; manual re-import defeats the guard | safety H1, safety M2 | spec v2: `restore_intent` written before `performChanges`; candidate search by filename, duration, size, date, then hash probe before creating; unverified restore is flagged and blocks further restores |
| 9 | A second delete dialog queued behind an abandoned one leads to "the app deleted my videos and reported an error" | safety H4 | spec v2: one outstanding `performChanges` at a time; `awaitingDialog` polled by re-fetch for up to an hour; batch identifiers recorded before submission |
| 10 | Edits between catalog and delete are not detected | safety H7 | spec v2 and plan: `modificationDate` captured at scan and catalog; Deleter refuses `changedSinceArchive` |
| 11 | Identical bytes in two assets collapse into one entry, losing the second asset's metadata and confusing restore | safety M1, format H1 | spec v2: entries keyed by hash carry an `assets[]` list; Restorer refuses if any identifier in `assets[]` or `restores[]` is fetchable |
| 12 | Adopter treats an empty v1 checksum as a hash; `archived_path` is absolute; duplicate uuids across manifests; adoption must repeat because the frozen CLI keeps writing v1 | safety H6, format H3, H4, H5 | spec v2: `status: needs_hash` with a legacy key until hashed; suffix resolution with the Python fallback search; prefer the entry whose file exists; `(uuid, session_id)` dedupe; re-scan on every open; never write inside legacy folders |
| 13 | Metadata cheap to read now and gone after delete: hidden flag, subtypes, modification date, altitude, album membership | safety H5, format H2, product M5 | spec v2 and plan: captured in `AssetFacts` and `AssetRecord`; Restorer re-hides and re-links albums by title, best effort. PhotoKit has no public title, caption, or keyword API; the spec says so |
| 14 | `FileHandle.write(_:)` raises an uncatchable exception on I/O error and kills the process mid-job | platform H1 | spec v2: throwing `write(contentsOf:)` under a lock with a closed flag; cancel on write error |
| 15 | Continuation double-resume race in the delete and restore watchdogs; will not compile in language mode 6 | platform H3 | spec v2: one-shot continuation box on `Mutex`; identifiers, not `PHAsset`, cross task boundaries |
| 16 | iCloud Shared Library assets look like user-library assets; PhotoKit cannot distinguish them; deleting one affects the whole family | product H1 | decision D2 below; slice 1 adds an exploratory detection probe either way |
| 17 | "Free iCloud space" is not what a delete does; Recently Deleted holds space 30 days and has no API | product H2, platform M8 | spec v2: `estimatedFreeDate` and `bytesPendingPurge` on the job; north star wording is decision D3 |
| 18 | Invariant 6 has no typed vocabulary behind it | product H3 | spec v2: closed enums `ExclusionReason`, `LocalityCause`, `FailureReason`, `RefusalReason`, `BudgetShortfall`, `DeleteOutcome`, plus `LibraryEnvironment` |
| 19 | Minimum macOS 27 excludes most Macs for the launch quarter and every Intel Mac forever | product H4 | decision D1 below |

## Medium and low, accepted

- Locality probe gets a 60 s timeout and cancels on the first chunk, since a chunk with network disallowed proves locality (platform M2).
- `CLGeocoder` is deprecated on 26; use `MKReverseGeocodingRequest` with a persistent app-level cache (platform M3, format M2).
- Scan is not "under one second"; resource lookup is an XPC call per asset. Claim removed; scan runs off the main actor (platform M5).
- Ad hoc signing breaks TCC attribution on every rebuild; always sign with the Apple Development identity (platform M7).
- Security scope is started once per volume session, not per use (platform M9, L1).
- `open -n -W` plus a running-instance guard for the harness (platform L2).
- Thumbnails come from PhotoKit before download, with an SDR policy, never from the drive (safety M5, platform L4).
- Sleep: `beginActivity(.idleSystemSleepDisabled)` during transfers; watchdog on a suspending clock; wake is a resume (safety M3, format M5).
- Volume UUID is a Deleter precondition (safety M4).
- Job store gets a schema, a file lock, and a copy beside the manifest (format M5, safety L2).
- Folder date time zone rule and place-name reuse within 2 km (format M1, M2); filename sanitation, NFC, case-insensitive collision, Windows reserved names (format M3); file header with format and reader versions, archive id, volume identity, unknown fields preserved (format M4).
- Space planning per batch against both volumes, using the library's volume, with `BatchPlan` (product M3).
- Live Photo exclusion stated explicitly; `hasAdjustments`, hidden, and subtype rules get classifier tests (safety M6).
- Harness bundle id moves to `dev.videoattic.harness`; App Review dossier appendix drafted (product M1, L1, L3).
- `ScanSummary` needs `CodingKeyRepresentable`; test filters need `@Suite`; expected-output strings corrected; dead fallbacks removed; extra tests for record equality, rule precedence, error passthrough; date placeholders resolved; never `git add -A` (plan dry run 1 to 13).
- Restore refuses entries whose origin is not the user library (product L2).
- Sharper exit gates for phases 1 to 3 (product M6): adopted into the north star pending D3.

## Rejected

- Replacing read-back verification with something cheaper (platform H2 considered it): read-back with `F_NOCACHE` costs 10 to 20 s per 4 GB, under the download time. Kept.
- Making Recently Deleted visible or purgeable: no API exists. The honest timeline is the only option.

## Deferred, tracked in STATE

- Archiving rendered edits and adjustment data alongside originals (its own spec, after phase 1).
- Cloud identifiers (`cloudIdentifierMappings`) as a stable secondary key (evaluate in slice 2).
- Hidden-asset visibility to third-party clients on macOS 27 (measure in slice 1).
- Cache eviction latency of downloaded originals (measure at the phase 1 exit run).

## Decisions for the owner

**D1. Minimum macOS.** The product reviewer's evidence: macOS 26 reached about half of active Macs after eleven weeks, and macOS 27 drops every Intel Mac. A 27-only launch in Q4 2026 cannot install on roughly half the Macs that find it. The engine cost of a 26 fallback is one slice: `SizeInfo` as exact or estimated (duration times resolution times a codec table), a budget factor of 1.25 on estimates, and the verifier correcting the catalog with the real size. Recommendation: minimum 26, size exact on 27.

**D2. iCloud Shared Library.** PhotoKit cannot tell a Shared Library asset from a personal one. Options: (a) detect participation, warn, and let the user proceed; (b) detect and refuse deletion entirely while a Shared Library is present; (c) ignore. Recommendation: (a) for the App Store build, with the warning stating that family members' videos may be included and that deletion affects everyone. Slice 1 adds the detection probe regardless.

**D3. North star wording.** Two edits to human-owned text: the job sentence should say iCloud space is freed within 30 days, or immediately if the user empties Recently Deleted in Photos; invariant 7 should say that Shared Library participation is detected and gated because PhotoKit cannot tell shared from personal. Also the sharper exit gates: phase 1 fifty cold iCloud videos including five over 2 GB, one forced sleep and one drive unplug mid-run, resume with zero re-downloads of verified files, ten deletes and restores, one full adopted manifest verified, every exclusion reason exercised, zero untyped failures; phase 2 three strangers complete archive and restore on a sample library unaided in under 15 minutes and can say where their videos are and when space returns; phase 3 ten paying customers, under one support ticket per five sales, no review under three stars citing data loss.

**D4. Edited videos excluded by default in phase 1.** Recommendation: yes, with a visible count, until the adjustments spec ships. The alternative silently destroys edits.
