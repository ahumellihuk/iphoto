# State

The only home for current status. Rewritten continuously by the execution channel; points at specs, never restates them. Vision and invariants: [NORTH-STAR.md](NORTH-STAR.md). Coverage ledger: [COVERAGE.md](COVERAGE.md).

## Now

- Phase 1, Engine, slice 1: package skeleton, PhotoKit scanner with shared-album exclusion, locality probe, harness `scan`. Plan: [plans/2026-09-06-engine-slice-1.md](plans/2026-09-06-engine-slice-1.md). Spec approved 2026-09-06: [specs/2026-09-06-engine-core.md](specs/2026-09-06-engine-core.md).

## Next (ordered)

1. Engine slice: library scan and locality probe, excluding shared-album assets.
2. Engine slice: download, verify, archive write, manifest, resumable session.
3. Engine slice: delete behind Apple's dialog with re-fetch confirmation.
4. Engine slice: restore with date and location, hash-keyed, duplicate-refusing.
5. Engine slice: adopt the existing archive on the Acer drive (about 740 videos, 570 GB, ten manifests).
6. Python CLI maintenance: fix `is_local` (task chip open), then freeze.
7. Phase 2 spec: app information architecture and the find-and-review flow.

## Gate

- Phase 1 exit: engine proven end to end on this Mac's real library, including one archive-delete-restore round trip on a real user-library asset with two verified copies, as in the spike.

## Decisions pending

- Final price point within $29 to $39 and the family tier.

## Decisions made

- 2026-09-06 Product name: Video Attic ([naming study](research/2026-09-06-naming.md)). Follow-ups: formal class 9 and 42 search, videoattic.app domain, early US application.
- 2026-09-06 Engine spec approved.
- 2026-09-06 Minimum macOS 27 (public `dataSize`, no private API).
- 2026-09-06 Direct build ships the same PhotoKit engine, no AppleScript, no capability flags.

## Known risks carried forward

- Cold downloads above 1.7 GB, sleep behavior, and macOS 26 were not measured in the spike.
- PhotoKit caches every downloaded original in the library; disk budgeting must count it twice.
- The Acer external drive hangs the USB bus under sustained writes; do not use it for engine tests until replaced.

## Pointers

- Research records: [research/](research/)
- Live specs: [specs/](specs/). Shipped specs: [archive/specs/](archive/specs/)
- Spike harness: `spike/` (results gitignored in `spike/scratch/results/`)
- Reference implementation: `src/iphoto` (frozen)
