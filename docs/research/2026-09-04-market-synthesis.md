# Market synthesis and niche options (2026-09-04)

Synthesis of the five research records in this folder: competitors, Apple platform, demand and pricing, user voice, PhotoKit feasibility. Estimates are marked [est.].

## What the evidence says

**The pain is real, recurring, and emotional.** 60% of surveyed consumers ran out of cloud space in the past six months and 45% already own an external drive (Western Digital, n=6,118). Two-thirds of US Apple customers pay for iCloud storage, making it Apple's most popular service (CIRP). In every forum thread, videos are named as the culprit, and the dominant emotion is fear of loss: "Please don't tell me this can't be done", "Once lost, no amount of money can recover it". Users already use the word "archive" for what they want.

**Apple's answer is buy more or delete.** iCloud+ steps from 200 GB at $2.99 to 2 TB at $9.99 to 6 TB at $29.99, monthly only. Apple's own support articles prescribe deletion or upgrading. macOS 26 and 27 add nothing that offloads individual assets, and iOS 27 makes shared album content count against the owner's storage, which increases pressure. No Sherlock signal found.

**The specific job is unoccupied.** No shipping Mac product combines iCloud-original download, verified copy to a drive, deletion from Photos, a browsable catalog, and one-click restore. Exporters exist ($3-50 one-time) but are export-only and break on macOS releases. Cleaners delete into Recently Deleted and do not free iCloud space. Backup tools all require "Download Originals to this Mac", which is impossible for the people whose Mac is smaller than their library. The closest product, Happy Photo Exporter, is free, has eight ratings, and reports errors on exactly the delete-after-export flow.

**Pricing is settled by the market.** Consumer storage utilities cluster at $10-45 one-time; subscription fatigue is the loudest complaint across every iOS cleaner. A $39 app plus an $85 2 TB drive pays back in about six months against the 2 TB to 6 TB jump. Realistic indie ceiling for a focused utility is $3-8k/month [est.], calibrated against Lunar ($7k/mo, $23 lifetime) and Xnapper ($3-6k/mo, $29).

**The platform is viable but has sharp edges.** PhotoKit from a sandboxed app can stream iCloud originals with `PHAssetResourceManager.writeData` and can delete behind Apple's own dialog, with Gemini 2 as App Store precedent. Documented risks: iCloud downloads that stall and never call back (mitigated by a 300 s timeout and retry, as osxphotos does); one Swift project found iCloud-only assets invisible to PhotoKit under Optimize Storage and fell back to AppleScript; two mobile projects saw the resource API silently return downscaled proxies; original file size is public only on macOS 27; moments and place names do not exist in PhotoKit on macOS; security-scoped bookmarks to external drives have broken in macOS 14.7.5 and 26.3 and need a re-select fallback.

## Niche options

**Option 1: Selective video archive for iCloud families.** Move the large, old videos out of Photos onto a drive the family owns, keep a catalog with thumbnails, restore in one click. Narrowest, exactly the unoccupied square in the gap table, and the "pays for itself" story is strongest. Retention comes from the catalog and the recurring nature of the problem.

**Option 2: Backup for optimized libraries.** Incremental, verified copy of the whole Photos library to an external drive even when the Mac is smaller than the library. This is the single most-requested feature in the forum threads and every backup tool fails at it. It is a copy tool, so it does not free iCloud space, retention is weaker, and it competes with Photos Backup Anywhere, Parachute, and the open-source photo-export at $4-15.

**Option 3: iCloud downsizer.** Whole-library migration off iCloud to local storage with deletion, the "start over" job. One-time need, hard to retain, competes with icloudpd and Apple's own transfer tool.

## Recommendation

Option 1 as the product, with Option 2 as the natural second release because it reuses the same download-verify-catalog engine and answers the loudest forum request. Option 3 is a mode of Option 1, not a product.

Two consequences for the north star:
- The PhotoKit spike is a go/no-go gate, not a formality. It must reproduce the invisible-asset and proxy failures on a real Optimize Storage library before any UI work.
- Minimum macOS may need to be 27 for public file-size access, or 26 with a size estimate from duration and dimensions. The "both distributions" decision earns its keep here: a direct-download build can carry the AppleScript fallback that the App Store build cannot.

## Open questions the research could not settle

- Reddit volume and sentiment (crawler blocked); needs a manual pass of r/iCloud, r/ApplePhotos, r/DataHoarder, r/Parenting.
- Whether `fileSize` is populated for iCloud-only originals below macOS 27.
- Whether iCloud-only assets are reliably enumerable by PhotoKit on a Mac with Optimize Storage on.
- Mac ownership among iPhone-owning families (35% assumed, unsourced).
