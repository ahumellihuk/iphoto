# State

The only home for current status. Rewritten continuously by the execution channel; points at specs, never restates them. Vision and invariants: [NORTH-STAR.md](NORTH-STAR.md). Coverage ledger: [COVERAGE.md](COVERAGE.md).

## Now

- Phase 1, Engine. Red team complete: five reports and a [consolidation](research/redteam/2026-09-06-consolidated.md). [Engine spec v2](specs/2026-09-06-engine-core-v2.md) drafted with the accepted fixes, awaiting review together with decisions D1 to D4. The slice 1 plan is rewritten once D1 and D4 are decided.

## Next (ordered)

1. Decide D1 (minimum macOS), D2 (Shared Library gating), D3 (north star wording and exit gates), D4 (edited videos excluded in phase 1).
2. Rewrite [plans/2026-09-06-engine-slice-1.md](plans/2026-09-06-engine-slice-1.md) against spec v2 and the dry-run defects; execute slice 1.
3. Engine slice 2: archive log, projection, layout, v1 adapter with a real fixture, harness adopt and verify.
4. Engine slice 3: downloader, verifier, thumbnails, job store, batch planner, volume access, harness archive with resume.
5. Engine slice 4: deleter. 6. Slice 5: restorer. 7. Slice 6: grouping on MapKit. 8. Slice 7: exit gate run.
9. Python CLI maintenance: fix `is_local` (task chip open), then freeze.
10. Phase 2 spec.

## Gate

- Phase 1 exit: engine proven end to end on this Mac's real library, including one archive-delete-restore round trip on a real user-library asset with two verified copies, as in the spike.

## Decisions pending

- D1 Minimum macOS 27 (decided 2026-09-06) reopened by the red team: 27 excludes every Intel Mac and about half of active Macs in the launch quarter; a 26 fallback costs one slice. Recommendation: 26.
- D2 iCloud Shared Library: PhotoKit cannot tell shared from personal. Recommendation: detect participation and warn before deletion.
- D3 North star wording: honest 30-day Recently Deleted timeline; invariant 7 gating; sharper exit gates. Text in the consolidation.
- D4 Edited videos excluded from phase 1 archiving. Recommendation: yes.
- Final price point within $29 to $39 and the family tier.

## Decisions made

- 2026-09-06 Product name: Video Attic ([naming study](research/2026-09-06-naming.md)). Follow-ups: formal class 9 and 42 search, videoattic.app domain, early US application.
- 2026-09-06 Engine spec approved.
- 2026-09-06 Minimum macOS 27 (public `dataSize`, no private API).
- 2026-09-06 Direct build ships the same PhotoKit engine, no AppleScript, no capability flags.

## Known risks carried forward

- Deferred from the red team: rendered edits and adjustment data alongside originals (own spec); cloud identifiers as a secondary key (evaluate in slice 2); hidden-asset visibility on macOS 27 (measure in slice 1); cache eviction latency (measure at exit gate).

- Cold downloads above 1.7 GB, sleep behavior, and macOS 26 were not measured in the spike.
- PhotoKit caches every downloaded original in the library; disk budgeting must count it twice.
- The Acer external drive hangs the USB bus under sustained writes; do not use it for engine tests until replaced.

## Pointers

- Research records: [research/](research/)
- Live specs: [specs/](specs/). Shipped specs: [archive/specs/](archive/specs/)
- Spike harness: `spike/` (results gitignored in `spike/scratch/results/`)
- Reference implementation: `src/iphoto` (frozen)
