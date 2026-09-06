# Red team: product and App Store review risk (2026-09-06)

Fable 5.1 reviewer report, verbatim.


Ranked by severity. Sources: repo docs listed in the ask plus the checks cited inline.

## High

### H1. iCloud Shared Library is invisible to the engine and breaks invariant 7's promise

Section: spec `LibraryScanner`, `AssetRecord.sourceType`; north star invariant 7.
Scenario: A family on an iCloud Shared Library (iOS 16+, the exact "family shared with my wife" customer in user-voice quote 1). Every Shared Library asset reports `sourceType == .typeUserLibrary`, so the filter passes it. Apple engineering has confirmed there is no PhotoKit API to distinguish personal from shared-library assets ([forum thread 710767](https://developer.apple.com/forums/thread/710767)). The engine will archive and delete a video contributed by the spouse. On delete, the spouse gets a notification, the video goes to Recently Deleted for everyone, and only the contributor can purge or recover it ([Apple support](https://support.apple.com/en-us/118229)). Storage is charged to the organizer, so a participant running the app may free nothing on their own quota. Restore creates a new personal-library asset, not a shared one, so the family loses the video from the shared view.
The invariant text "Only user-library assets are touched" is satisfied by the letter and violated in effect.
Proposed change: Spec: add `AssetRecord.libraryScope: .personal | .sharedLibraryUnknown` derived from `PHPhotoLibrary`-level detection: if the account participates in a Shared Library (detectable only indirectly; test whether `PHAssetCollection` smart-album fetch or `PHAsset` `sourceType` exposes anything on macOS 27 in slice 1), the engine must set a library-wide `SharedLibraryPresent` flag and the app must warn before any delete. North star invariant 7: reword to "Only assets the user alone owns are touched. Shared-album assets are excluded by source type; Shared Library participation is detected and, when present, deletion is gated behind an explicit warning because PhotoKit cannot tell shared from personal." STATE: add a slice-1 probe task and a known risk line.

### H2. "Free iCloud space" is not what a delete does; the engine has no Recently Deleted signal

Section: north star sentence and customer job; spec `Deleter`, `JobState`.
Scenario: User archives 200 GB, deletes, opens iCloud settings, sees the same number. Space returns only after Recently Deleted purges in 30 days ([Apple 104967](https://support.apple.com/en-us/104967)), and there is no API to enumerate, empty, or even count Recently Deleted; since iOS 16 the fetch returns zero assets ([forum 719540](https://developer.apple.com/forums/thread/719540)). The app cannot deep-link to that album either. The market synthesis itself criticises cleaners for exactly this ("delete into Recently Deleted and do not free iCloud space") and the spec then does the same thing.
Proposed change: North star: change the job sentence to "free iCloud space within 30 days, or today if you empty Recently Deleted yourself", and make the honest timeline a stated invariant-6 obligation. Spec: `JobState.done` must carry `deletedAt` and `bytesPendingPurge`, and the job store must expose `estimatedFreeDate = max(deletedAt) + 30 d` so the app can show "iCloud space frees up on 12 October, or now if you empty Recently Deleted in Photos" with step-by-step instructions. Add a manual test that the wording matches the Photos app on macOS 27.

### H3. Invariant 6 has no typed signals behind it for the situations the app must explain

Section: spec `Error handling`, `ScanSummary`, `LocalityProbe`.
Scenario list, each checked against the spec:

| User-facing situation | Typed signal in spec | Gap |
|---|---|---|
| Video skipped: shared album | `ScanSummary` count by reason | Reason enum not defined; needs `ExclusionReason` |
| Video skipped: no size (`dataSize` nil) | `sizeBytes == nil` | No reason; app cannot say "we could not measure this one" |
| Video skipped: `canPerform(.delete)` false | Deleter precondition only | Not in scan; surfaces late, after download |
| Video skipped: has adjustments (archiving the original loses edits) | `hasAdjustments` field | No rule at all; see M4 |
| Video skipped: Live Photo component or paired resource | none | see M5 |
| Locality unknown | `.unknown` | No cause; app cannot distinguish "offline" from "iCloud stalled" |
| Mac disk filling during download (cache) | Budget refuses to start; 2 GB floor stop | No pre-run estimate object; no message that the cache is macOS's and will be evicted later, not by the app |
| Drive too small | same budget | Same |
| Drive absent / stale / needs reselect | `VolumeAccess` states | Adequate |
| Download failed after retries | `failed(reason, attempts)` | `reason` untyped; must at least split network, timeout, mismatch, out of space |
| Delete dialog cancelled by user | none | Job would sit at `deletable`; needs `deleteDeclined` |
| Delete completion never fired, re-fetch says still present | 120 s watchdog | No state name; app cannot say "Photos did not confirm, nothing was lost" |
| Restore refused: original still present or already restored | Restorer refuses | No typed refusal reason |
| Space actually freed vs pending purge | none | H2 |
| Photos permission limited / denied | none | M2 |
| iCloud Photos off / no cloud-only assets | none | M2 |
| Not the System Library | none | M2 |

Proposed change: Spec: add an `Engine/Support/Signals` section defining closed enums `ExclusionReason`, `LocalityCause`, `FailureReason`, `RefusalReason`, `BudgetShortfall(volume, needed, available, ofWhichCache)`, and `DeleteOutcome(.confirmed, .declined, .unconfirmed)`. Every enum case is a row the app localises; the spec says "the engine never formats messages for people", which is right, but it must give a finite vocabulary to format from. Add a unit test that every `failed`/`skipped` transition carries a case, not a string.

### H4. Minimum macOS 27 at launch cuts the reachable market to a small fraction for the launch quarter

Section: STATE decision "Minimum macOS 27"; spec `Package.swift .v27`.
Scenario: macOS 27 ships mid-September 2026 and drops every Intel Mac ([MacRumors roundup](https://www.macrumors.com/roundup/macos-27/)). macOS 26 reached about 40% within weeks and roughly 50% by week 11 ([MacRumors forum tracking](https://forums.macrumors.com/threads/tahoe-adoption-rate.2474641/), [TelemetryDeck](https://telemetrydeck.com/survey/apple/macOS/versions/)), and 86% after ten months. Expect 27 to follow the same curve on a smaller base, so 40-55% of active Macs by month three and 70-80% by month six, minus all Intel Macs permanently. If phase 3 lands in Q4 2026, half the customers who find the App Store page cannot install it, and the Intel family Mac (an iMac in a kitchen is the archetype) never can. Reviews saying "requires the newest macOS" are the first thing a non-technical buyer reads.
The only stated reason is public `dataSize`. The spike showed the size is needed for two things: the space budget and the selection UI ("largest videos first"). Both tolerate an estimate for a fallback.
Proposed change: Decision to reopen in STATE. Spec: platform `.v26`, `sizeBytes` becomes `SizeInfo { exact(bytes) | estimated(bytes, from: duration×dimensions×codec table) }` with a `#available(macOS 27)` branch; the budget uses estimate ×1.25 and the drive-side verifier corrects the catalog with the real size after download. Cost: one size-estimation function, one availability branch, a fixture test; roughly one slice. The spike already recorded that `dataSize` was nil for a subset even on 27, so the estimator is needed anyway. If the team keeps 27, STATE must record the market-share assumption and a date to revisit.

## Medium

### M1. App Review 5.1.1(iii) and the Photos usage string

Section: north star product shape; spec harness and entitlements.
Scenario: Guideline 5.1.1(iii) tells apps to prefer the out-of-process picker over full Photos access ([App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)). The picker cannot enumerate, download originals, or delete, so full read-write access is justified, but nothing in the repo records the justification or the usage string. Reviewers read `NSPhotoLibraryUsageDescription` and the review notes; a vague string on an app that deletes content is the most likely rejection. Deletion itself has precedent (Gemini 2) and always goes through Apple's dialog, which is the strongest argument.
The harness bundle ID under `com.videoattic` is not submitted, so it cannot confuse review; but it should be kept out of the App Store Connect app record entirely (a separate bundle ID with a `dev.` prefix avoids any accidental provisioning-profile overlap).
Proposed change: Spec: add an "App Review dossier" appendix: the usage string draft ("Video Attic needs your whole Photos library to find large videos, copy them to your drive, and remove them only after you confirm in Photos' own dialog"), the 5.1.1(iii) justification paragraph, the review-notes demo script with a sample library, and the guideline 2.4.5 sandbox and 2.5.1 public-API statements. Move the harness to `dev.videoattic.harness`. STATE: add "review dossier drafted" to the phase 3 gate.

### M2. Library configurations the spec never names

Section: spec `LibraryScanner`; north star invariant 4.
Scenario, one line each:
- iCloud Photos off: everything probes local, downloads are copies, the "free iCloud space" story is false; the app should say "this Mac is not using iCloud Photos" and switch to a "free Mac space" framing or refuse.
- Optimize Storage off with Download Originals: same as above for space, but deleting frees iCloud after 30 days; budget double-counting is wrong here (original already local, no second copy).
- Multiple libraries: PhotoKit reaches only the System Photo Library ([RhetTbull/photokit](https://github.com/RhetTbull/photokit)); a user whose big library is not the system one sees the wrong library and no explanation.
- Library on an external drive: the cache double-count lands on that drive, not the boot volume; the budget must check the library's volume, not `/`.
- Limited Library: `PHAuthorizationStatus.limited` exists on macOS via Catalyst and the research notes a 26.4 regression under it; for AppKit it is usually full or denied, but the engine must still type `.limited` and `.denied` and refuse cleanly rather than scanning an empty library and reporting "no videos".
Proposed change: Spec: add `LibraryEnvironment` produced before scan: `authorization`, `iCloudPhotosEnabled` (inferred: any asset probes cloud-only), `optimizeStorageLikely`, `libraryVolumeURL` (from the library's `PHPhotoLibrary` container path or the probe cache location), `isSystemLibrary`. Budget uses `libraryVolumeURL`. The app refuses or reframes per environment. Add each to the phase 1 exit gate as a manual check where this Mac can produce it.

### M3. Cache double-count is a budget rule but not a user promise

Section: spec `JobState` space planning; STATE known risk.
Scenario: A 512 GB MacBook with 60 GB free archiving 200 GB. The job refuses to start, and the user does not know why, since the drive has room. macOS evicts cached originals on its own schedule; the spike could not measure when. The app can only say "your Mac needs about as much free space as the videos you archive in one go, temporarily; macOS clears it later".
Proposed change: Spec: budget is per batch, not per job; the planner splits the job into batches sized to the smaller of drive and library-volume headroom, and reports `BatchPlan { batches, bytesEach, waitForEvictionBetween }`. STATE: add "measure eviction latency of cached originals" to the phase 1 exit run.

### M4. Edited videos and adjustments

Section: spec `AssetRecord.hasAdjustments`; downloader uses the `.video` resource.
Scenario: The original resource is archived, the edit is lost on delete, restore brings back the unedited video. The field exists; no rule uses it.
Proposed change: Spec: assets with `hasAdjustments` are `skipped(.edited)` in phase 1 and listed by the app; a later spec may archive `.fullSizeVideo` alongside.

### M5. Market research items the spec ignores

Section: user voice "explicit feature requests", market synthesis Option 2.
- Live Photos: the `.video` filter excludes them, and a Live Photo's video component is `.pairedVideo`, so no accidental split. Say so in the spec; today it is implicit.
- Albums lost: the archive layout carries no album membership, so a restored video comes back outside its albums. The catalog should record `albumTitles` at archive time and the restorer should re-add to albums that still exist (`PHAssetCollectionChangeRequest`).
- Incremental sync to a drive (the loudest request) is deferred to phase 4 correctly, but the manifest should already carry `archived_by` mode so a phase-4 "copy without delete" entry is distinguishable from an "archived and deleted" one; currently `restores[]` is the only hint.
- Keywords and star ratings (new in 27 Photos) are metadata the family adds; the manifest drops them.
Proposed change: Spec `ManifestEntry`: add `album_titles[]`, `keywords[]`, `mode: archived | copied`. Restorer: re-link albums by title, best effort, typed result.

### M6. Exit gates are not measurable

Section: north star phase table; STATE gate.
- Phase 1 "proven on this Mac's real library end to end": one asset round trip is a demo, not proof. Sharper: 50 cold iCloud-only videos including five over 2 GB, one forced sleep and one drive unplug mid-run, resume with zero re-downloads of verified files, delete and restore of ten, adopted archive verifies one full manifest, all `ExclusionReason` cases exercised at least once, and zero untyped failures in the JSONL.
- Phase 2 "hallway test": three people who have never seen it, each completes archive-and-restore of a fixed sample library without help, under 15 minutes, and can answer "where are my videos now" and "when does iCloud space come back" correctly afterwards.
- Phase 3 "first paying customers": ten paying customers, fewer than one support ticket per five sales, no review under three stars citing data loss.
Proposed change: replace the three gate cells with the above; STATE gate mirrors phase 1.

## Low

### L1. Direct build notarization

Same engine, same entitlements, Developer ID signing with the hardened runtime; PhotoKit and bookmarks work identically. The only difference is that TCC prompts show the app name from the bundle, so both builds must share `NSPhotoLibraryUsageDescription`. No action beyond a Makefile target and a note in the spec.

### L2. Restore of a shared-album item (finding 13)

The Restorer guard checks fetchability and hash but not the entry's origin. Add `archived_from: userLibrary` to the manifest and refuse restore of anything else, including adopted v1 entries whose origin is unknown unless the user confirms.

### L3. Place names and privacy

`CLGeocoder` sends coordinates to Apple. It is Apple's service and needs no usage string, but the privacy nutrition label must declare location data use. Note in the review dossier.

### L4. Manifest sorted by `creation_date`

Rewriting one pretty-printed JSON per entry change on a 5,000-entry archive is a full file rewrite per video; on the slow drive from the STATE risk it will dominate. Consider append-only journal plus periodic compaction, keeping the human-readable file as the compaction output.

Sanity check done: every item above maps to a quoted line in the spec, north star, or STATE, and the four external claims (Shared Library undetectable, Recently Deleted unreadable, macOS 26 adoption curve, macOS 27 timing and Intel drop) were verified with the linked sources.

result: Engine spec review found four launch-blocking gaps (undetectable iCloud Shared Library assets, no Recently Deleted or space-freed signal behind the "free iCloud space" promise, no typed vocabulary for invariant 6, macOS 27 minimum excluding most Macs at launch) plus six decisions and four minor items, each with a concrete spec, north star, or STATE change.

Sources: [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), [macOS 27 roundup](https://www.macrumors.com/roundup/macos-27/), [macOS 27 Intel drop](https://www.macrumors.com/2026/05/26/macos-27-will-mark-the-end-of-an-era/), [Tahoe adoption thread](https://forums.macrumors.com/threads/tahoe-adoption-rate.2474641/), [TelemetryDeck macOS versions](https://telemetrydeck.com/survey/apple/macOS/versions/), [Shared Library not distinguishable via PhotoKit](https://developer.apple.com/forums/thread/710767), [Recently Deleted not fetchable](https://developer.apple.com/forums/thread/719540), [Shared Library deletion behaviour](https://support.apple.com/en-us/118229), [Recently Deleted 30 days](https://support.apple.com/en-us/104967), [PHAuthorizationStatus.limited](https://developer.apple.com/documentation/photos/phauthorizationstatus/limited), [photokit on macOS reaches System Library only](https://github.com/RhetTbull/photokit)