# Research: competitors and adjacent products (2026-09-04)

Agent-gathered. Prices USD. "Unknown" = not confirmed by a fetched source. Reddit was unreachable, so Reddit mention counts are missing throughout.

## 1. Photos offload and export apps (Mac)

| Product | Price / model | Distribution | Downloads iCloud-only originals | Deletes from Photos | Catalog / restore | Signals | Weaknesses |
|---|---|---|---|---|---|---|---|
| PowerPhotos (Fat Cat) | $39.95 one-time | Direct only | Yes, via Photos automation | Yes, via library-to-library moves and dedupe | Archive library on external, merge back later; no plain-file catalog | Macworld Editors' Choice | Can't sync a subset with iCloud; archive is a Photos library, not files ([site](https://www.fatcatsoftware.com/powerphotos/), [Macworld](https://www.macworld.com/article/2773700/powerphotos-3-review.html)) |
| PhotoSweeper | $14.99 one-time | MAS | No, local originals only | Moves to a trash album for manual delete | None | "Not enough ratings" | Crashes, low trust in dedupe decisions ([MAS](https://apps.apple.com/us/app/photosweeper/id463362050?mt=12)) |
| Mylio Photos+ | $9.99-25/mo, $119-240/yr | MAS + direct | Imports from Photos one-way; unclear | No | Full DAM with external "Vaults"; no restore-to-Photos | 3.5 stars, 50 ratings (GB) | Heavy, unstable iPad app, price increases ([support](https://support.mylio.com/how-much-does-mylio-photos-cost), [baty.net](https://baty.net/posts/2025/08/the-mylio-conundrum/)) |
| Photos Takeout | $8.99/mo or $49.99 lifetime | MAS | Yes | No, export only | None | Insufficient ratings; 9to5Mac coverage | "takes forever", "all or nothing" ([MAS](https://apps.apple.com/us/app/photos-takeout-for-icloud-mac/id1500714691?mt=12)) |
| Photo Exporter (Avid Trader) | $4.99 | MAS | Yes | No | None | Insufficient | "Does not work" on Sonoma, no support ([MAS](https://apps.apple.com/us/app/photo-exporter/id1495415955?mt=12)) |
| Photos Export Pro | $2.99 | MAS | Yes | No | None | Insufficient | Live Photo stills only ([MAS](https://apps.apple.com/us/app/photos-export-pro/id1484356283?mt=12)) |
| Photo Export - Local Backup | $3.99, MIT on GitHub | MAS | Unknown | No | Rebuilds its own state from a folder | 74 GitHub stars, active | Backup not offload ([MAS](https://apps.apple.com/us/app/photo-export-local-backup/id6761410742?mt=12), [GitHub](https://github.com/valtteriluomapareto/photo-export)) |
| Happy Photo Exporter | Free | MAS, Mac + iOS | Unspecified | Yes, delete after export with verification | Re-import rebuilds Live Photos and edits | 3.9 stars, 8 ratings | "38 processed with 26 errors", no albums preserved ([MAS](https://apps.apple.com/us/app/happy-photo-exporter/id6470921349)) |
| Photos Backup Anywhere | $9.99 | MAS | Yes | No | Restores into Photos; whole-library backup | Insufficient | Not selective |
| Parachute Backup | $14.99 | MAS | Unknown | No | "Drag files back in Finder" | Insufficient | Backup only |
| PhotoSort | $4.99 | MAS | n/a | No | None | Insufficient | Finds large files, tells you to export manually |
| SwipePhotos | $34.99/yr | MAS | n/a | Swipe to delete | None | Unknown | Deletion tool |
| Metapho | $19.99/yr or $59.99-99.99 one-time | MAS, universal | Browses iCloud library | Replaces originals | None | 4.6 stars, 2,100+ ratings | Metadata editor, not an archiver ([MAS](https://apps.apple.com/us/app/metapho/id914457352)) |
| Hedge OffShoot | $169-249 | Direct | No Photos integration | No | Verified card offload | Pro video market | Not a Photos tool ([hedge.co](https://hedge.co/products/offshoot)) |
| icloudpd | Free CLI, MIT | GitHub | Yes, via iCloud web API | Yes, "move" mode deletes from iCloud | None | 12.2k stars | Needs web access on and ADP off, 2FA re-auth, "seeks maintainers" ([GitHub](https://github.com/icloud-photos-downloader/icloud_photos_downloader)) |
| osxphotos | Free CLI, MIT | GitHub | Yes, via AppleScript or experimental PhotoKit | No | `osxphotos import` is the only scripted restore path | 3.8k stars | CLI only ([GitHub](https://github.com/RhetTbull/osxphotos)) |

## 2. Cleanup suites with a Photos component

Cross-cutting: none has a catalog, archive, or restore layer. Every one either deletes into Recently Deleted or never touches Photos. None advertises downloading iCloud-only originals before deletion.

- CleanMyMac (MacPaw): $39.99-65.99/yr or $89.99 one-time. Photo Junk removes caches and local copies of iCloud photos; "does not delete actual photos". Cloud Cleanup does not cover iCloud Photos ([MacPaw KB](https://macpaw.com/support/cleanmymac-x/knowledgebase/photo-junk), [MAS](https://apps.apple.com/us/app/cleanmymac/id1339170533?mt=12)).
- DaisyDisk: $9.99. FAQ states Apple provides no API to scan iCloud, so Photos is one opaque blob ([FAQ](https://daisydiskapp.com/support/faq/)).
- Tidy Up: $34.99. Duplicate finder that can move items elsewhere, file-level, no restore ([MAS](https://apps.apple.com/us/app/tidy-up/id1395962105?mt=12)).
- Gemini 2: $19.99-26/yr or $44.95 lifetime. Deletes from Photos library, establishing MAS precedent ([MAS](https://apps.apple.com/us/app/gemini-2-the-duplicate-finder/id1090488118?mt=12)).
- Duplicate Photos Fixer Pro, Photos Duplicate Cleaner, Remo: $0-20, duplicates only.
- iOS cleaners (CleanMy Phone 4.6/23K, Slidebox 4.8/16K, Smart Cleaner 4.4/10K, Cleanup 4.7/710K, Swipewipe 4.7/47-84K): $4-12 per week is the norm; reviewers call the pricing predatory and note they "do not clear iCloud storage" ([Tumbleson](https://connortumbleson.com/2025/01/13/predatory-ios-cleanup-applications/), [Macgasm](https://news.macgasm.net/reviews/cleanup-app-phone-cleaner-review/)).

## 3. Cloud alternatives and migration tooling

| Product | Price | Pulls iCloud-only originals | Deletes from Photos | Restore to Photos | Signals |
|---|---|---|---|---|---|
| Google Photos / One | 100GB $1.99, 2TB $9.99/mo | iOS app must re-download optimized items | No | No | Dominant ([Internxt](https://blog.internxt.com/google-one-pricing/)) |
| Amazon Photos | Prime; only 5GB video | Via iOS app | No | No | Useless for video ([Amazon](https://www.amazon.com/gp/help/customer/display.html?nodeId=G6PT8TMLM9NVZCSL)) |
| Ente | 50GB $2.49 to 2TB $19.99/mo | iOS app imports from iCloud; slow, must stay foregrounded | No | No | 28.6k stars ([GitHub](https://github.com/ente-io/ente)) |
| Immich | Free, self-hosted | Via iOS app or CLI with Download Originals on | No | No | 113.4k stars; 6-8GB RAM, breaking releases ([GitHub](https://github.com/immich-app/immich)) |
| Synology Photos | NAS hardware | Optimized items may be skipped | No | No | Location data dropped on mobile backup ([Apple dev forum](https://developer.apple.com/forums/thread/819034)) |
| PhotoPrism | Free to EUR 6/mo | Folder import only | No | No | 40.1k stars |
| Apple "Transfer a copy" to Google Photos | Free | Yes, 3-7 days | No | No | Drops Live Photos, some metadata; disabled under ADP ([Apple](https://support.apple.com/en-us/118257)) |

## 4. Backup tools targeting the Photos library

Every backup tool depends on "Download Originals to this Mac". None fetches optimized-away originals and none offers selective offload.

- Carbon Copy Cloner 7: $49.99. Can materialize cloud-only iCloud Drive files, but coverage of optimized Photos originals is undocumented ([TidBITS](https://tidbits.com/2023/10/06/carbon-copy-cloner-backs-up-cloud-only-content/)).
- Backblaze: $9/mo. Own blog tells users to select Download Originals ([Backblaze](https://www.backblaze.com/blog/back-photos-library/)); users resort to a second macOS account plus an external drive ([Six Colors](https://sixcolors.com/post/2025/08/work-around-icloud-photos-optimized-limitations/)).
- Time Machine: Apple itself says with Optimize Mac Storage "Time Machine may not have a backup of your originals" ([Apple](https://support.apple.com/en-kg/guide/photos/pht6d60348f/3.0/mac)).
- Arq 7: $59.99; "does not apply to the Photos Library" ([b3n.org](https://b3n.org/macos-backup-strategy/)).
- ChronoSync: $49.99; package-aware sync of local files only.

## 5. Gap analysis

| Job to be done | Who does it well today |
|---|---|
| Find the large old videos eating iCloud | PhotoSort (barely), CleanMy Phone (on device only), nobody on Mac with iCloud awareness |
| Download the iCloud-only original reliably | Photos Takeout (slowly), PowerPhotos (via Photos), icloudpd (web API, fragile auth), osxphotos (CLI) |
| Verified copy to an external drive | Hedge OffShoot (no Photos), CCC (whole library), nobody per-asset |
| Delete from Photos after verification | Happy Photo Exporter (free, error-prone), Gemini 2 (duplicates only), icloudpd move mode (no restore) |
| Browsable catalog of what left | Mylio (heavy DAM), nobody lightweight |
| One-click restore into Photos | osxphotos import (CLI), Happy Photo Exporter (partial), Photos Backup Anywhere (whole library) |
| All of the above in one non-technical flow | Nobody |

## 6. Assessment

- No shipping Mac product combines iCloud-original download, verified copy, delete, catalog, and restore. The closest, Happy Photo Exporter, is free with eight ratings and error reports.
- Exporters cluster at $3-50 one-time. The one subscription exporter, Photos Takeout at $8.99/mo, draws "gets stuck" complaints.
- Subscription fatigue is the loudest complaint across every iOS entry; one-time pricing draws explicit praise.
- "Doesn't actually free iCloud space" is a recurring reviewer note for cleaners.
- Small MAS apps in this space break on each macOS release (Sonoma, Sequoia complaints), which is a trust opening for a maintained product.
- Recurring user pain to design against: iCloud-only originals invisible, Live Photo pairing, album structure lost, distrust of deletion.
