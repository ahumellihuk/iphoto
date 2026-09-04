# Research: PhotoKit feasibility for a sandboxed Mac App Store app (2026-09-04)

Agent-gathered from Apple docs, Apple Developer Forums, local Xcode 27 SDK headers, osxphotos source, GitHub issues. UNCONFIRMED items are marked.

## A. Downloading iCloud originals

Confirmed (Apple docs):
- `PHAssetResourceManager.requestData(...)`: "Depending on the options you specify and the current state of the asset, Photos may download asset data from the network... progressively providing chunks of data" ([docs](https://developer.apple.com/documentation/photos/phassetresourcemanager/requestdata(for:options:datareceivedhandler:completionhandler:))).
- `writeData(for:toFile:options:)`: "Photos progressively writes the data into the specified file" ([docs](https://developer.apple.com/documentation/photos/phassetresourcemanager/writedata(for:tofile:options:completionhandler:))). This is the bounded-memory path for multi-GB files.
- `isNetworkAccessAllowed = true` downloads from iCloud if not local; default false yields an error ([docs](https://developer.apple.com/documentation/photos/phassetresourcerequestoptions/isnetworkaccessallowed)). `progressHandler` is called periodically during download ([docs](https://developer.apple.com/documentation/photos/phassetresourcerequestoptions/progresshandler)).
- Resource types: `.video` = original video data; `.fullSizeVideo` = rendered edit, not original; `.pairedVideo` = Live Photo video ([docs](https://developer.apple.com/documentation/photos/phassetresourcetype)).
- osxphotos on macOS uses PhotoKit with `networkAccessAllowed=True` to fetch iCloud originals ([photokit.py](https://raw.githubusercontent.com/RhetTbull/osxphotos/main/osxphotos/photokit.py)).

Known failures:
- Error codes (`PHError.h`): -1 internalError; 3072 userCancelled; 3164 networkAccessRequired; 3169 networkError; 3300 changeNotSupported; 3301 operationInterrupted (transient); 3302 invalidResource; 3303 missingResource; 3305 notEnoughSpace; 3306 requestNotSupportedForAsset ([docs](https://developer.apple.com/documentation/photos/phphotoserror-swift.struct/code)).
- `writeData` on an Optimize Storage library: progress stops at 0.5 then `NSCocoaErrorDomain -1` "Unable to locate resource"; community advice is retry ([forum](https://developer.apple.com/forums/thread/66477)).
- Callbacks never firing for iCloud assets, iOS 17-26. Apple DTS: "most likely a PhotoKit framework bug... Implement defensive timeouts and fallbacks" ([forum](https://developer.apple.com/forums/thread/813354)).
- osxphotos wraps every PhotoKit request in a 300 s timeout because "If iCloud stalls, the completion/result handler never fires" ([photokit.py](https://raw.githubusercontent.com/RhetTbull/osxphotos/main/osxphotos/photokit.py)).
- `requestAVAsset` returns nil with `PHImageResultIsInCloudKey = 1` even after a full download; unresolved ([forum](https://developer.apple.com/forums/thread/98669)).
- Larger videos fail more often via export session (AVFoundation -11800) ([forum](https://developer.apple.com/forums/thread/24559)).
- Shared-album assets return empty resources ([forum](https://developer.apple.com/forums/thread/113692)).
- "Device storage is full" blocks background download jobs ([forum](https://developer.apple.com/forums/thread/819034)).
- No source found on explicit rate limiting (UNCONFIRMED).

Alternatives compared:
- `requestAVAsset` / `requestExportSession` give AVFoundation representations; `.mediumQualityFormat` fetches a 720p file ([forum](https://developer.apple.com/forums/thread/676918)). Reported size mismatch versus `PHAssetResource.fileSize` ([forum](https://developer.apple.com/forums/thread/763764)). `PHAssetResourceManager` with `.video` is the only API documented as byte-original.
- macOS 26+: `PHAssetResourceUploadJobChangeRequest.creationRequestForDownloadJob(resource:)` lets the system download in the background; "The system may purge downloaded resources due to disk space constraints. After a download-only job succeeds, process the resource promptly" ([docs](https://developer.apple.com/documentation/photokit/uploading-asset-resources-in-the-background)).

Photos.app dependency: transfers are performed by `cloudphotod` / `photolibraryd` daemons, not Photos.app ([man page](https://keith.github.io/xcode-man-pages/cloudphotod.8.html), [osxdaily](https://osxdaily.com/2025/06/02/explaining-cloudd-photolibraryd-cloudphotod-processes-in-macos/)). Requires iCloud Photos enabled for the library. Sleep and App Nap effects UNCONFIRMED.

## B. Deletion

- `PHAssetChangeRequest.deleteAssets(_:)` available macOS 10.15+ ([docs](https://developer.apple.com/documentation/photos/phassetchangerequest/deleteassets(_:))).
- One `performChanges` block with N assets yields one system prompt ([docs](https://developer.apple.com/documentation/photos/phphotolibrary/performchanges(_:completionhandler:))). Exact macOS dialog wording UNCONFIRMED.
- Requires `com.apple.security.personal-information.photos-library` entitlement plus `NSPhotoLibraryUsageDescription`; missing yields `.denied` / error 3311 ([forum](https://developer.apple.com/forums/thread/749286)). Needs `PHAccessLevel.readWrite`. `canPerformEditOperation(.delete)` pre-checks.
- Deleted items go to Recently Deleted for 30 days ([Apple](https://support.apple.com/guide/photos/delete-photos-and-videos-pht3bfab2f96/mac)); no API can fetch Recently Deleted ([forum](https://developer.apple.com/forums/thread/719540)). iCloud propagates deletion to all devices.
- Known bug: completion never fires for certain ProRAW DNGs on iOS 26.x, Apple acknowledged FB18720533 ([forum](https://developer.apple.com/forums/thread/806349)). macOS not reported.
- No evidence of App Review rejections for deleteAssets; Gemini 2 precedent exists.

## C. Metadata available on macOS

- Original file size: `PHAssetResource.dataSize` is public only on macOS 27 / iOS 27 (`PHAssetResource.h`, [docs](https://developer.apple.com/documentation/photos/phassetresource)). Below that, private KVC `value(forKey: "fileSize")` works in practice ([alexwlchan](https://alexwlchan.net/2023/finding-big-photos/)) but Apple DTS warns it may be caught at ingestion ([forum](https://developer.apple.com/forums/thread/771861)) and guideline 2.5.1 forbids private API. Whether `fileSize` is populated for iCloud-only originals is UNCONFIRMED ([unanswered thread](https://developer.apple.com/forums/thread/818002)).
- Moments: `PHAssetCollectionType.moment` and moment lists are `API_UNAVAILABLE(macos)`; they do not compile for macOS ([SDK header](https://github.com/phracker/MacOSX-SDKs/blob/041600eda65c6a668f66cb7d56b7d1da3e8bcc93/MacOSX11.3.sdk/System/Library/Frameworks/Photos.framework/Versions/A/Headers/PHCollection.h)).
- Place names: no Photos API gives location names, only `PHAsset.location` ([forum](https://developer.apple.com/forums/thread/650505)). Alternative: cluster coordinates and reverse-geocode once per cluster with `CLGeocoder`, which is rate-limited.
- Local versus iCloud-only: no public flag. Apple staff: "try to request the data... and see if an iCloud download is triggered" ([forum](https://developer.apple.com/forums/thread/79296)). Probes: `PHImageResultIsInCloudKey`, or a resource request with network disallowed that fails with 3164.
- Available on `PHAsset`: location, creationDate, modificationDate, duration, pixel dimensions, mediaSubtypes, isFavorite, isHidden, sourceType, hasAdjustments (12), addedDate and contentType (26), rating (27). On `PHAssetResource`: originalFilename, contentType, pixel dimensions (13), dataSize (27).
- Direct SQLite reading of Photos.sqlite is not viable for the Mac App Store: Full Disk Access does not bypass sandbox checks ([forum](https://developer.apple.com/forums/thread/807142)); MAS apps must work without it ([forum](https://developer.apple.com/forums/thread/124895)).

## D. Re-import

- `PHAssetCreationRequest.addResource(with:fileURL:options:)` macOS 10.15+ ([docs](https://developer.apple.com/documentation/photos/phassetcreationrequest/addresource(with:fileurl:options:))). `shouldMoveFile` avoids an intermediate copy ([docs](https://developer.apple.com/documentation/photos/phassetresourcecreationoptions/shouldmovefile)).
- `creationDate` and `location` settable on the request ([docs](https://developer.apple.com/documentation/photos/phassetchangerequest/creationdate)). Whether embedded QuickTime metadata wins over explicit values is UNCONFIRMED.
- The created asset gets a new local identifier via `placeholderForCreatedAsset`; this is a new asset, not a restoration of the old one ([docs](https://developer.apple.com/documentation/photos/phassetchangerequest/placeholderforcreatedasset)).
- Errors: 3302 on invalid video and on insufficient disk space ([forum](https://developer.apple.com/forums/thread/696924)); large-video failures as `PHPhotosErrorDomain -1` ([GitHub](https://github.com/react-native-cameraroll/react-native-cameraroll/issues/186)).
- Behavior of Optimize Mac Storage for re-imported originals UNCONFIRMED.

## E. Non-PhotoKit routes, assessed

- AppleScript from the sandbox needs `com.apple.security.scripting-targets` (only if Photos' sdef defines access groups, UNCONFIRMED) or a temporary-exception entitlement that Apple DTS calls "tantamount to shipping a non-sandboxed app" ([QA1888](https://developer.apple.com/library/archive/qa/qa1888/_index.html), [forum](https://developer.apple.com/forums/thread/794326)). User-installed scripts via `NSUserAppleScriptTask` run outside the sandbox but are meant for user-authored scripts ([forum](https://developer.apple.com/forums/thread/794355)). Not a product foundation.
- Shortcuts: runnable via URL scheme or CLI ([Apple](https://support.apple.com/guide/shortcuts-mac/use-a-url-scheme-to-run-a-shortcut-apd624386f42/mac)); whether a sandboxed app may spawn the CLI and get unmodified originals is UNCONFIRMED.
- iCloud web API (icloudpd / pyicloud): requires "Access iCloud Data on the Web" and Advanced Data Protection off ([GitHub](https://github.com/icloud-photos-downloader/icloud_photos_downloader)); recurring auth breakage; handles Apple ID passwords in-app. Poor fit for App Store review.
- Photos Project Extensions offer nothing beyond normal PhotoKit access ([docs](https://developer.apple.com/documentation/photosui/phprojectextensioncontext)).

## Verdict and spike list

PhotoKit is viable and is the only route compatible with the Mac App Store. The spike must measure:
1. Success rate and throughput of `writeData` with network access on 20+ iCloud-only videos over 1 GB on an Optimize Storage library, with a 300 s stall timeout and retry.
2. Whether `dataSize` on macOS 27, and the private `fileSize` on 26, report sizes for iCloud-only originals.
3. Behavior during sleep and with Photos.app closed.
4. The macOS deletion dialog wording and batch behavior.
5. Round trip: re-import with explicit creationDate and location, then compare metadata and bytes.
6. Security-scoped bookmark survival across drive reconnects and reboots.

## F. Open-source reference projects

- [rcarmo/PhotosExport](https://github.com/rcarmo/PhotosExport): Swift CLI, MIT, not sandboxed. Uses `writeData` per resource with network access; no progress handler, no timeout, no retry.
- [valtteriluomapareto/photo-export](https://github.com/valtteriluomapareto/photo-export): SwiftUI, MIT, macOS 15+, sandboxed and on the Mac App Store. Originals via `writeData`, edited videos via `requestExportSession`. Exponential-backoff retries. Issues: private `CloudPhotoLibraryErrorDomain error 1005` during iCloud downloads ([#80](https://github.com/valtteriluomapareto/photo-export/issues/80)); download blocks UI ([#110](https://github.com/valtteriluomapareto/photo-export/issues/110)); enumeration beachball ([#116](https://github.com/valtteriluomapareto/photo-export/issues/116)). This is the closest reference for our architecture.
- [tijs/ladder](https://github.com/tijs/ladder): Swift library, Apache-2.0, macOS 13+, not sandboxed. Streams PhotoKit export with inline SHA-256. Key finding: iCloud-only assets under Optimize Mac Storage were not returned by `PHAsset.fetchAssets(withLocalIdentifiers:)` at all, so it falls back to AppleScript export with a 10-minute per-asset timeout ([design plan](https://github.com/tijs/ladder/blob/main/docs/plans/2026-03-21-001-feat-applescript-fallback-icloud-assets-plan.md)). Must be reproduced in the spike.
- [abentele/PhotosExporter](https://github.com/abentele/PhotosExporter): Swift CLI, 169 stars, dormant since 2024.
- osxphotos `--use-photokit` is "highly experimental" but "faster and more reliable than the default AppleScript interface" ([docs](https://rhettbull.github.io/osxphotos/cli.html)). Issues: [#1504](https://github.com/RhetTbull/osxphotos/issues/1504) photokit download-missing 10 min to 9 h on 80k library; [#555](https://github.com/RhetTbull/osxphotos/issues/555) thousands of AppleScript export failures at 40k photos, individual retries succeed; [#626](https://github.com/RhetTbull/osxphotos/issues/626) shared-album downloads inconsistent; [Discussion #1883](https://github.com/RhetTbull/osxphotos/discussions/1883) "Photos.app and its background agents is slow and unpredictable". PhotoScript [#47](https://github.com/RhetTbull/PhotoScript/issues/47): AppleScript exported about 20 of 1000 videos as XML plist instead of .MOV.
- Proxy risk: flutter_photo_manager [#1118](https://github.com/fluttercandies/flutter_photo_manager/issues/1118) and Immich [#29543](https://github.com/immich-app/immich/issues/29543) report `writeData` with network access returning downsampled proxies under Optimize Storage on iOS, because `PHAssetResourceRequestOptions` has no `deliveryMode`. Byte-size and checksum verification against the expected original is mandatory, not optional.

Takeaways: every Swift project uses `writeData` with network access; none uses `progressHandler`; only osxphotos bounds the wait with a timeout. Two independent failure modes are documented: iCloud-only assets invisible or stalled, and resource APIs silently returning proxies.
