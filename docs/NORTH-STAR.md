# North Star

Binding intent for the product. Changes here are deliberate, rare, and human-owned. Status never lives here; see [STATE.md](STATE.md).

## The sentence

> Your family's iPhone videos, safe on a drive you own, still findable, and back in Photos whenever you want them.

## Customer and job

A non-technical family hitting the iCloud storage-full warning, unwilling to pay for the next tier, who values footage far more than photos by the byte. They hire the app to free iCloud space without losing anything, and keep it because the problem returns every year.

Evidence: [market synthesis](research/2026-09-04-market-synthesis.md), [user voice](research/2026-09-04-user-voice.md).

## Product shape

- A native macOS app in Swift and SwiftUI on PhotoKit, sandboxed, Mac App Store first, a notarized direct build second.
- Photos stays the family's front door. The app is the tiered-storage layer beneath it: move large old videos to an external drive, keep a catalog with thumbnails, bring any video back into Photos in one click.
- One-time purchase in the $29 to $39 range, family tier above it. Any recurring charge must be for a recurring cost the customer can see.
- The Python CLI in `src/iphoto` is the frozen reference implementation and test oracle for the archive format. Maintenance only: bug fixes, no features.

Evidence for the stack: [PhotoKit spike results](research/2026-09-04-photokit-spike-results.md), verdict PASS on both stages.

## Invariants that bind every change

Every spec, plan, and slice is checked against these. A change that would break one is out, or must show an explicit, reviewed fence.

1. **Nothing is deleted before it is verified.** Every archived file is checksum-matched to the original's bytes before the app offers to delete, and the delete itself is Apple's own dialog. No silent destruction, ever. A destructive step verifies its own preconditions from library state at run time, never from an earlier step's exit status.
2. **The archive is readable without the app.** Plain files in dated folders plus a human-readable manifest. If the company dies, the footage does not.
3. **Restore is one click and idempotent.** Restoring puts the video back in Photos with its date and location, never creates duplicates on retry, and refuses when the original is still in the library. The catalog's durable key is the content hash, not a Photos identifier, because restored assets get new identifiers.
4. **Sandboxed and public-API only.** The App Store build uses PhotoKit and security-scoped bookmarks exclusively. Bookmarks resolve without mounting, and "volume absent" is a recoverable state with a reconnect prompt, never a crash or a silent mount. Anything needing a private API lives only in the direct build behind a documented capability flag.
5. **Every long operation is resumable.** Interruptions, drive disconnects, and sleep never lose progress or leave the library ambiguous. Downloads use bounded waits, retry with backoff, and byte verification, because PhotoKit and iCloud can stall silently.
6. **No jargon in the primary flow.** The user sees videos, space, drive, and Photos, never identifiers, checksums, or error codes. Detail lives one click down.
7. **Only user-library assets are touched.** Shared-album assets (PhotoKit source type cloud-shared) are excluded from selection, deletion, and restore. Locality is decided by a PhotoKit probe, never by a database flag.

## Out of scope for the north star

A standalone media browser competing with Photos. Silent background deletion. Cloud destinations as the primary archive. AppleScript as a product foundation.

## Phases

Phase detail belongs in dated specs under [specs/](specs/); this list is the order and the exit gate of each phase, nothing more.

| Phase | Name | Exit gate |
|---|---|---|
| 0 | Research and spike | Done 2026-09-06. Niche chosen, stack proven, invariants written. |
| 1 | Engine | A Swift package that scans, probes, downloads, verifies, archives, deletes, and restores through PhotoKit, with a developer CLI, resumable sessions, and the ability to adopt the existing Python-made archive. Proven on this Mac's real library end to end. |
| 2 | App | SwiftUI app for a non-technical user: onboarding and permissions, drive choice, find-and-review flow grouped by date and place, archive with progress, catalog with thumbnails and search, one-click restore. Passes a hallway test with someone who has never seen it. |
| 3 | Launch | Mac App Store submission accepted, pricing live, direct notarized build, support and refund path, marketing page. First paying customers. |
| 4 | Growth | Chosen by evidence from phase 3, from: rules and suggestions, optimized-library backup on the same engine, on-device media analysis, second copies. Each is its own spec. |

## Failure families

Tag related backlog and shipped items in STATE with `family:` and `root:` so a root that keeps producing symptoms is visible. Minted at the second occurrence; none yet.
