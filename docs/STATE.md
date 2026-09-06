# State

The only home for current status. Rewritten continuously by the execution channel; points at specs, never restates them. Vision and invariants: [NORTH-STAR.md](NORTH-STAR.md). Coverage ledger: [COVERAGE.md](COVERAGE.md).

## Now

- Phase 1, Engine, slice 1 against [spec v2](specs/2026-09-06-engine-core-v2.md): package skeleton, size estimation, full asset record, classifier with all exclusions, library environment with Shared Library probe, scanner, locality probe with timeout, harness `scan` and `environment`. Plan: [plans/2026-09-06-engine-slice-1.md](plans/2026-09-06-engine-slice-1.md) (rewritten after the [red team](research/redteam/2026-09-06-consolidated.md)).

## Next (ordered)

1. Execute slice 1.
2. Engine slice 2: archive log, projection, layout, v1 adapter with a real fixture, harness adopt and verify.
3. Engine slice 3: downloader, verifier, thumbnails, job store, batch planner, volume access, harness archive with resume.
4. Engine slice 4: deleter. 5. Slice 5: restorer. 6. Slice 6: grouping on MapKit. 7. Slice 7: exit gate run.
8. Python CLI maintenance: fix `is_local` (task chip open), then freeze.
9. Phase 2 spec.

## Gate

- Phase 1 exit: the numeric gate in the north star phase table (fifty cold videos, sleep and unplug, zero re-downloads, ten deletes and restores, one adopted manifest verified, every exclusion reason exercised, zero untyped failures).

## Decisions pending

- Final price point within $29 to $39 and the family tier.

## Decisions made

- 2026-09-06 D1 Minimum macOS 26 with estimated sizes; exact sizes on 27. Reverses the earlier 27 decision after the red team.
- 2026-09-06 D2 iCloud Shared Library: detect where possible, warn before any delete, treat "cannot tell" as warn.
- 2026-09-06 D3 North star job sentence carries the 30-day Recently Deleted timeline; invariant 7 gains Shared Library gating and edit preservation; exit gates are numeric.
- 2026-09-06 D4 Edited videos excluded from phase 1 archiving with a visible count.
- 2026-09-06 Engine spec v2 approved.
- 2026-09-06 Product name: Video Attic ([naming study](research/2026-09-06-naming.md)). Follow-ups: formal class 9 and 42 search, videoattic.app domain, early US application.
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
