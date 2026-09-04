# Research: Apple platform, pricing, and policy (2026-09-04)

Agent-gathered, URLs inline. Unconfirmed items listed at the end.

## 1. iCloud+ pricing and the services narrative

Current tiers (Apple's official page, updated 2026-07-17) — [support.apple.com/en-us/108047](https://support.apple.com/en-us/108047)

| Tier | US | UK | Eurozone |
|---|---|---|---|
| 50 GB | $0.99 | £0.99 | €0.99 |
| 200 GB | $2.99 | £2.99 | €2.99 |
| 2 TB | $9.99 | £8.99 | €9.99 |
| 6 TB | $29.99 | £26.99 | €29.99 |
| 12 TB | $59.99 | £54.99 | €59.99 |

Monthly billing only; no annual discount ([bestcloudstorageguide](https://bestcloudstorageguide.com/blog/icloud-plus-pricing-guide-2026)).

Recent price changes:
- July 2026: increases of 11-55% in Nigeria, Türkiye, Vietnam, Japan, Egypt, New Zealand, Philippines, Indonesia; currency-driven. US and unlisted countries unchanged ([MacRumors, 2026-07-17](https://www.macrumors.com/2026/07/17/apple-icloud-plus-price-increase/)).
- May 2025: Brazil, Chile, Peru raised ([MacRumors, 2025-05-26](https://www.macrumors.com/2025/05/26/apple-raises-icloud-prices-in-three-countries/)).
- UK: 50 GB £0.79 to £0.99, 200 GB £2.49 to £2.99, 2 TB £6.99 to £8.99 ([PhoneArena](https://www.phonearena.com/news/Apple-raises-iCloud-prices-in-the-UK-and-other-countries_id148499), [TechRadar](https://www.techradar.com/phones/iphone/thats-just-greediness-apple-fans-left-furious-over-icloud-price-increases)). Date unconfirmed (believed late 2023). Euro pricing unchanged ([GSMArena](https://m.gsmarena.com/newscomm-58989p2.php)).

Implication: the 200 GB to 2 TB jump ($2.99 to $9.99, $84/yr delta) is the pain point. A household with 300-500 GB of video pays $120/yr for 2 TB when a one-time drive plus the app could hold them at 200 GB.

Subscribers and services:
- Q3 FY2026 (2026-07-30): revenue $109.4B (+16%), Services $30.7B record (+12%), cloud services all-time high ([MacRumors](https://www.macrumors.com/2026/07/30/apple-3q-2026-earnings/), [Yahoo Finance](https://finance.yahoo.com/markets/stocks/articles/apple-q3-2026-earnings-beat-211056445.html), [CNBC](https://www.cnbc.com/2026/07/30/apple-earnings-live-updates.html)).
- 1.5 billion paid subscriptions incl. third-party ([PYMNTS](https://www.pymnts.com/apple/2026/apples-record-results-fail-to-ease-growth-concerns/)).
- Apple does not disclose iCloud+ subscriber counts. CIRP (Aug 2024): nearly two-thirds of US Apple customers pay for iCloud storage, its most popular service ([MacRumors](https://www.macrumors.com/2024/08/21/icloud-storage-most-popular-apple-service/)). Third-party claims of ~450M paid are unverified ([countly.net](https://countly.net/how-many-icloud-users-are-there-in-2026-global-by-country-8ea9), [quantumrun](https://www.quantumrun.com/consulting/apple-statistics/)).

## 2. What Apple offers for "storage full" and Sherlock risk

Existing (unchanged in 26/27):
- Optimize Mac Storage / Optimize iPhone Storage: solves device space, not iCloud space ([Apple Support](https://support.apple.com/guide/photos/optimize-storage-in-photos-on-mac-phta9b4673b4/mac)).
- "Recommended for You" in iCloud settings (iOS 17+): deletion only, no archive/restore ([Apple Support 108922](https://support.apple.com/en-us/108922)).
- Move whole library to external APFS/HFS+ drive; all-or-nothing ([Apple Support 108345](https://support.apple.com/en-us/108345)).
- Recently Deleted retention 30 days ([Apple Support 104967](https://support.apple.com/en-us/104967)). A PhotoKit delete does not free iCloud space for 30 days.
- Duplicates detection ([MacRumors iOS 26 guide](https://www.macrumors.com/guide/ios-26-photos-app/)).

WWDC 2025 / iOS 26 / macOS Tahoe 26 Photos: tab-bar return, Spatial Scenes, slideshow maker, full-res Shared Albums, contact posters count against iCloud ([9to5Mac](https://9to5mac.com/2025/10/23/heres-everything-new-for-apple-photos-in-ios-26/), [Apple newsroom](https://www.apple.com/newsroom/2025/06/macos-tahoe-26-makes-the-mac-more-capable-productive-and-intelligent-than-ever/), [Apple Support 108782](https://support.apple.com/en-us/108782)). Nothing about offloading.

WWDC 2026 / iOS 27 / macOS 27: Spatial Reframe, Extend, Clean Up, star ratings, keywords, "Captured by Me" and "Identity Documents" collections, "Sync Immediately", slideshow export, Shared Albums full-res with expiry and Android/Windows contributors. Shared Album content now counts against the owner's iCloud storage, including items added by others ([9to5Mac](https://9to5mac.com/2026/06/16/heres-everything-new-for-apple-photos-in-ios-27/), [MacRumors](https://www.macrumors.com/guide/ios-27-photos-app/), [Cult of Mac](https://www.cultofmac.com/news/ios-27-photos-features), [Apple newsroom](https://www.apple.com/newsroom/2026/06/apple-unveils-next-generation-of-apple-intelligence-siri-ai-and-more/)).

Sherlock assessment: no Apple feature in 26 or 27 offloads individual assets to local storage with restore. Apple's direction is more iCloud consumption, which increases demand. Risks: (a) "Archive to external drive" in a point release, no signal; (b) "Recommended for You" nudging deletion of large videos; (c) Google-style video compression, no signal. Mac App Store competitors focus on duplicates ([Macworld](https://www.macworld.com/article/2434914/gemini-2-duplicate-file-finder-review.html), [MacRumors forums](https://forums.macrumors.com/threads/best-app-to-remove-duplicates-from-apple-photos-library.2111719/)).

## 3. Mac App Store policy for this category

- Sandbox mandatory: guideline 2.4.5(i); (iii) no background processes after quit without consent; (vi) no license keys; (vii) MAS updates only ([App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)).
- 5.1.1(iii) data minimization: "use the out-of-process picker ... rather than requesting full access to protected resources like Photos." Justification: offloading requires enumeration, iCloud download, and delete, which the picker cannot do. 5.1.1(ii) purpose strings must be complete.
- Entitlement: `com.apple.security.personal-information.photos-library` for read-write PhotoKit from the sandbox ([Apple docs](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.personal-information.photos-library)); `NSPhotoLibraryUsageDescription` required ([Apple docs](https://developer.apple.com/documentation/bundleresources/information-property-list/nsphotolibraryusagedescription)). Missing entitlement yields `deny mach-lookup com.apple.photos.service` ([Apple forums](https://developer.apple.com/forums/thread/762839)).
- Deleting photos is permitted: `PHAssetChangeRequest.deleteAssets` shows a system confirmation; assets go to Recently Deleted ([Apple docs](https://developer.apple.com/documentation/photos/phassetchangerequest), [Apple forums](https://developer.apple.com/forums/thread/678736)). Gemini 2 (MAS, $19.99/yr) deletes from Photos, establishing precedent ([App Store](https://apps.apple.com/us/app/gemini-2-the-duplicate-finder/id1090488118?mt=12)).
- No published guideline on storage-cleaner apps; iOS predatory cleaners policed under 4.3 and 3.1.2 ([Connor Tumbleson](https://connortumbleson.com/2025/01/13/predatory-ios-cleanup-applications/), [Apple forums](https://developer.apple.com/forums/thread/112848)).

## 4. Removable-volume access from the sandbox

- Mechanism: `com.apple.security.files.user-selected.read-write` plus `com.apple.security.files.bookmarks.app-scope`; resolve with `URLByResolvingBookmarkData`, wrap with `startAccessingSecurityScopedResource` / `stop…`. Forgetting `stop` leaks kernel resources ([Apple forums](https://developer.apple.com/forums/thread/72867), [CODEBIT](https://codebit-inc.com/blog/mastering-file-access-macos-sandboxed-apps/)). Bookmarks HMAC-signed by ScopedBookmarkAgent ([Microsoft, CVE-2025-31191](https://www.microsoft.com/en-us/security/blog/2025/05/01/analyzing-cve-2025-31191-a-macos-security-scoped-bookmarks-based-sandbox-escape/)).
- Persistence across launches and reconnects works in principle. Pitfalls:
  - macOS 14.7.5/13.7.5 moved the app-scope key to the data-protection keychain; old bookmarks failed with error 259; Apple DTS advised NSOpenPanel re-prompt fallback (FB17100576) ([Apple forums](https://developer.apple.com/forums/thread/779247)).
  - macOS 26.3: sandboxed apps reportedly lose bookmarked-path access mid-session ([Apple forums, App Sandbox tag](https://developer.apple.com/forums/tags/app-sandbox)).
  - Symlinks inside bookmarked trees are problematic ([Apple forums](https://developer.apple.com/forums/thread/814725)).
  - Bookmarks are Mac-local; a catalog moved to another Mac needs re-authorization.
- Design implication: store volume UUID and relative path in the catalog independently of the bookmark, detect `isStale`, always offer "re-select drive".

## 5. Photos automation direction

- PhotoKit is the sanctioned path; no "What's new in PhotoKit" session in 2025 or 2026 found ([Apple forums, photokit tag](https://developer.apple.com/forums/tags/photokit?page=2)). On macOS, public PhotoKit reaches only the System Library and exposes less metadata than iOS ([RhetTbull/photokit](https://github.com/RhetTbull/photokit)).
- AppleScript: Photos' dictionary not removed in Tahoe, but Tahoe introduced AppleScript timeouts; osxphotos calls Photos AppleScript "somewhat buggy" ([MacScripter](https://www.macscripter.net/t/scripting-changes-or-lack-thereof-in-macos-tahoe/77173), [Michael Tsai](https://mjtsai.com/blog/2025/09/17/tahoe-applescript-timeouts/), [osxphotos](https://github.com/RhetTbull/osxphotos)). AppleScript cannot delete; PhotoKit can ([PhotoScript](https://github.com/RhetTbull/PhotoScript)).
- Shortcuts: iOS/macOS 26 added Photos actions and Mac personal automations ([Apple Support 125148](https://support.apple.com/en-us/125148), [9to5Mac](https://9to5mac.com/2025/12/09/ios-26s-shortcuts-app-adds-25-new-actions-heres-everything-new/)). Opportunity: expose archive/restore via App Intents.
- Regressions to track: macOS 26.4 Catalyst PhotoKit fails under Limited Library (`PHPhotosErrorDomain 3303`, FB22318443) ([Apple forums](https://developer.apple.com/forums/thread/820201)); iOS 26 `performChanges` completion not called on delete ([Apple forums](https://developer.apple.com/forums/thread/806349)); iOS 26.2 deleted media reappearing ([Apple forums](https://developer.apple.com/forums/thread/810310)). Restore must be idempotent and verify by asset identifier.

## Could not confirm

Date of the UK price rise; any iCloud+ subscriber count from Apple or a reputable analyst; any Apple statement on PhotoKit changes at WWDC25/26; any Mac App Store rejection of a Photos-deleting utility; whether the macOS 26.3 mid-session bookmark loss is acknowledged by Apple.
