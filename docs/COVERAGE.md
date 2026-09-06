# Coverage

Every system and surface, its status, its owner, and the invariant that guards it. A row flips in the same commit that ships its slice. Status values: `spike-proven`, `not started`, `in progress`, `shipped`, `frozen`.

## Engine (phase 1)

| System | Status | Owner | Guarding invariant | Pointer |
|---|---|---|---|---|
| Library scan via PhotoKit sweep | spike-proven | engine | 7 | [spike results](research/2026-09-04-photokit-spike-results.md) A1 |
| Locality probe (network-disallowed request) | spike-proven | engine | 7 | spike results, findings 3 and 8 |
| Shared-album exclusion | spike-proven (as a finding) | engine | 7 | spike results, finding 12 |
| Size before download | spike-proven on macOS 27; estimate on 26 per D1 | engine | 6 | spike results, finding 2; [spec v2](specs/2026-09-06-engine-core-v2.md) |
| Download, streamed, stall-cancelled, retried | spike-proven | engine | 5 | spike results A1 to A3 |
| Byte verification (SHA-256) | spike-proven | engine | 1 | spike results |
| Archive format and manifest | not started (Python format is the oracle) | engine | 2 | `src/iphoto/manifest.py` |
| Resumable session | not started (Python semantics are the reference) | engine | 5 | `src/iphoto/models.py` |
| Delete behind Apple's dialog, re-fetch confirmed | spike-proven | engine | 1 | spike results, finding 10 |
| Restore with date and location, hash-keyed | spike-proven | engine | 3 | spike results, finding 11 |
| Volume bookmarks without mounting | spike-proven | engine | 4 | spike results, finding 14 |
| Adopt existing Python-made archive | not started | engine | 2 | manifests on the Acer drive |
| Developer CLI for the engine | not started | engine | 4 | |

## App (phase 2)

| Surface | Status | Owner | Guarding invariant |
|---|---|---|---|
| Onboarding and permissions | not started | app | 4, 6 |
| Drive choice and reconnect prompt | not started | app | 4 |
| Find and review, grouped by date and place | not started | app | 6, 7 |
| Archive run with progress and pause | not started | app | 5, 6 |
| Catalog with thumbnails and search | not started | app | 2, 6 |
| One-click restore | not started | app | 3, 6 |

## Launch (phase 3)

| Surface | Status | Owner | Guarding invariant |
|---|---|---|---|
| App Store packaging and review notes | not started | launch | 4 |
| Direct notarized build | not started | launch | 4 |
| Pricing and purchase | not started | launch | north star, product shape |
| Support and refund path | not started | launch | |

## Reference and tooling

| System | Status | Owner | Note |
|---|---|---|---|
| Python CLI `src/iphoto` | frozen, maintenance only | reference | `is_local` fix pending (task chip) |
| PhotoKit spike harness `spike/` | shipped, kept for re-measurement | engine | not product code |
