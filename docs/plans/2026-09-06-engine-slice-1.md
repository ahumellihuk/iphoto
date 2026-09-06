# Engine Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Swift package `ArchiveCore` that scans the Photos library through PhotoKit, excludes everything that is not a user-library video, probes whether an original is local or iCloud-only, and a headless sandboxed harness that runs the scan on this Mac and writes JSONL.

**Architecture:** PhotoKit is touched in exactly two files (`PhotoKitLibraryScanner.swift`, `LocalityProbe.swift`); everything they decide is expressed as pure value types (`AssetFacts`, `AssetRecord`, `Classification`, `ScanSummary`) so the rules are unit-tested without a library. The harness is a SwiftPM executable wrapped into an app bundle by a Makefile, signed with the sandbox and Photos entitlements, launched through `open` so permissions attach to the bundle (spike finding 6).

**Tech Stack:** Swift 6.4 toolchain in Xcode 27 beta, SwiftPM, Swift Testing (`import Testing`), PhotoKit, AppKit for the open panel. Minimum macOS 27. Spec: `docs/specs/2026-09-06-engine-core.md`. Reference code: `spike/PhotoKitSpike/Sources/`.

---

## File structure

```
engine/
  Package.swift
  Makefile                                   builds the harness bundle
  Sources/ArchiveCore/
    Support/EngineError.swift                typed errors, PhotoKit error mapping
    Library/AssetRecord.swift                AssetRecord, Locality (Codable value types)
    Library/AssetFacts.swift                 the raw facts read from a PHAsset, PhotoKit-free
    Library/AssetClassifier.swift            pure include/exclude rules + ScanSummary
    Library/PhotoKitLibraryScanner.swift     PHAsset sweep -> AssetFacts -> records (imports Photos)
    Library/LocalityProbe.swift              network-disallowed requestData (imports Photos)
  Sources/ArchiveHarness/
    main.swift                               arg parsing, NSApplication, dispatch
    OutputFolder.swift                       security-scoped bookmark to the output folder
    JSONLWriter.swift                        append-only JSONL
    Commands/ScanCommand.swift               `scan` command
  Harness/Info.plist
  Harness/ArchiveHarness.entitlements
  Tests/ArchiveCoreTests/
    AssetRecordTests.swift
    AssetClassifierTests.swift
    EngineErrorTests.swift
```

Everything lives under a new top-level `engine/` directory. The Python package in `src/` and the spike in `spike/` are untouched.

Conventions for every task:
- Run commands from `/Users/camoiloc/IdeaProjects/iphoto/engine` unless a step says otherwise.
- Swift language mode 5 (PhotoKit closures are not yet audited for strict concurrency).
- One commit per task, message prefix `feat(engine):`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

### Task 1: Package skeleton

**Files:**
- Create: `engine/Package.swift`
- Create: `engine/Sources/ArchiveCore/ArchiveCore.swift`
- Create: `engine/Sources/ArchiveHarness/main.swift` (placeholder, replaced in Task 6)
- Create: `engine/Tests/ArchiveCoreTests/SmokeTests.swift`
- Modify: `.gitignore` (repo root)

- [ ] **Step 1: Create the package manifest**

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ArchiveCore",
    platforms: [.macOS("27.0")],
    products: [
        .library(name: "ArchiveCore", targets: ["ArchiveCore"]),
        .executable(name: "ArchiveHarness", targets: ["ArchiveHarness"]),
    ],
    targets: [
        .target(
            name: "ArchiveCore",
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .executableTarget(
            name: "ArchiveHarness",
            dependencies: ["ArchiveCore"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "ArchiveCoreTests",
            dependencies: ["ArchiveCore"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
```

- [ ] **Step 2: Create the library placeholder**

`engine/Sources/ArchiveCore/ArchiveCore.swift`:

```swift
/// ArchiveCore: the Video Attic engine. See docs/specs/2026-09-06-engine-core.md.
public enum ArchiveCore {
    public static let version = "0.1.0"
}
```

- [ ] **Step 3: Create the harness placeholder**

`engine/Sources/ArchiveHarness/main.swift`:

```swift
import ArchiveCore

print("ArchiveHarness \(ArchiveCore.version)")
```

- [ ] **Step 4: Write the smoke test**

`engine/Tests/ArchiveCoreTests/SmokeTests.swift`:

```swift
import Testing
@testable import ArchiveCore

@Test func versionIsSet() {
    #expect(ArchiveCore.version == "0.1.0")
}
```

- [ ] **Step 5: Build and test**

Run: `swift build && swift test`
Expected: build succeeds; output ends with `Test run with 1 test passed`.

If `.macOS("27.0")` is rejected by the toolchain, use `.macOS(.v26)` in `Package.swift` and add `@available(macOS 27, *)` guards where `dataSize` is used in Task 4. Note it in the commit message.

- [ ] **Step 6: Ignore build products**

Append to the repo-root `.gitignore`:

```
# engine build products
/engine/.build/
/engine/build/
```

- [ ] **Step 7: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine .gitignore
git commit -m "feat(engine): ArchiveCore package skeleton with harness and test targets

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Errors and the record types

**Files:**
- Create: `engine/Sources/ArchiveCore/Support/EngineError.swift`
- Create: `engine/Sources/ArchiveCore/Library/AssetRecord.swift`
- Create: `engine/Tests/ArchiveCoreTests/EngineErrorTests.swift`
- Create: `engine/Tests/ArchiveCoreTests/AssetRecordTests.swift`
- Delete: `engine/Tests/ArchiveCoreTests/SmokeTests.swift`

- [ ] **Step 1: Write the failing error-mapping test**

`engine/Tests/ArchiveCoreTests/EngineErrorTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

@Test func photoKitErrorIsClassifiedByCode() {
    let networkRequired = NSError(domain: "PHPhotosErrorDomain", code: 3164)
    let e = EngineError.from(networkRequired)
    #expect(e == .photoKit(domain: "PHPhotosErrorDomain", code: 3164))
    #expect(e.isNetworkAccessRequired)
}

@Test func nonPhotoKitErrorIsWrappedAsUnderlying() {
    let posix = NSError(domain: NSPOSIXErrorDomain, code: 2)
    let e = EngineError.from(posix)
    #expect(e == .underlying(domain: NSPOSIXErrorDomain, code: 2))
    #expect(!e.isNetworkAccessRequired)
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `swift test --filter EngineErrorTests`
Expected: compile error, `cannot find 'EngineError' in scope`.

- [ ] **Step 3: Implement EngineError**

`engine/Sources/ArchiveCore/Support/EngineError.swift`:

```swift
import Foundation

/// Typed engine errors. PhotoKit codes that matter get named accessors;
/// everything else is carried as domain and code so nothing is lost.
public enum EngineError: Error, Equatable, Sendable {
    case photoKit(domain: String, code: Int)
    case underlying(domain: String, code: Int)
    case assetNotFound(identifier: String)
    case noOriginalVideoResource(identifier: String)
    case message(String)

    public static let photoKitDomain = "PHPhotosErrorDomain"

    /// PHPhotosError.networkAccessRequired: the original is not local and network was disallowed.
    public static let networkAccessRequiredCode = 3164

    public static func from(_ error: Error) -> EngineError {
        if let e = error as? EngineError { return e }
        let ns = error as NSError
        if ns.domain == photoKitDomain { return .photoKit(domain: ns.domain, code: ns.code) }
        return .underlying(domain: ns.domain, code: ns.code)
    }

    public var isNetworkAccessRequired: Bool {
        if case .photoKit(let domain, let code) = self {
            return domain == Self.photoKitDomain && code == Self.networkAccessRequiredCode
        }
        return false
    }
}
```

- [ ] **Step 4: Run the error tests**

Run: `swift test --filter EngineErrorTests`
Expected: `2 tests passed`.

- [ ] **Step 5: Write the failing record tests**

`engine/Tests/ArchiveCoreTests/AssetRecordTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

private func sampleRecord() -> AssetRecord {
    AssetRecord(
        photosIdentifier: "29953236-D636-4220-A0BD-4FA3537E2D54/L0/001",
        originalFilename: "IMG_9946.MOV",
        sizeBytes: 21_579_228,
        creationDate: Date(timeIntervalSince1970: 1_663_348_475),
        latitude: 51.5215,
        longitude: 0.1213,
        durationSeconds: 18.7,
        pixelWidth: 1920,
        pixelHeight: 1080,
        isFavorite: false,
        hasAdjustments: true,
        locality: .unknown
    )
}

@Test func recordRoundTripsThroughJSON() throws {
    let original = sampleRecord()
    let data = try JSONEncoder().encode(original)
    let decoded = try JSONDecoder().decode(AssetRecord.self, from: data)
    #expect(decoded == original)
}

@Test func uuidIsTheIdentifierPrefix() {
    #expect(sampleRecord().uuid == "29953236-D636-4220-A0BD-4FA3537E2D54")
}

@Test func localityEncodesAsAString() throws {
    let data = try JSONEncoder().encode(Locality.cloudOnly)
    #expect(String(data: data, encoding: .utf8) == "\"cloudOnly\"")
}
```

- [ ] **Step 6: Run them to verify they fail**

Run: `swift test --filter AssetRecordTests`
Expected: compile error, `cannot find 'AssetRecord' in scope`.

- [ ] **Step 7: Implement AssetRecord and Locality**

`engine/Sources/ArchiveCore/Library/AssetRecord.swift`:

```swift
import Foundation

/// Where an asset's original bytes are, as decided by a PhotoKit probe.
/// Never derived from a database flag (north star invariant 7).
public enum Locality: String, Codable, Sendable, Equatable {
    case local
    case cloudOnly
    case unknown
}

/// The engine's view of one user-library video. A value; safe to log and persist.
/// `photosIdentifier` is volatile and is never a catalog key (invariant 3).
public struct AssetRecord: Codable, Equatable, Sendable {
    public var photosIdentifier: String
    public var originalFilename: String
    public var sizeBytes: Int
    public var creationDate: Date?
    public var latitude: Double?
    public var longitude: Double?
    public var durationSeconds: Double
    public var pixelWidth: Int
    public var pixelHeight: Int
    public var isFavorite: Bool
    public var hasAdjustments: Bool
    public var locality: Locality

    public init(photosIdentifier: String, originalFilename: String, sizeBytes: Int,
                creationDate: Date?, latitude: Double?, longitude: Double?,
                durationSeconds: Double, pixelWidth: Int, pixelHeight: Int,
                isFavorite: Bool, hasAdjustments: Bool, locality: Locality) {
        self.photosIdentifier = photosIdentifier
        self.originalFilename = originalFilename
        self.sizeBytes = sizeBytes
        self.creationDate = creationDate
        self.latitude = latitude
        self.longitude = longitude
        self.durationSeconds = durationSeconds
        self.pixelWidth = pixelWidth
        self.pixelHeight = pixelHeight
        self.isFavorite = isFavorite
        self.hasAdjustments = hasAdjustments
        self.locality = locality
    }

    /// The UUID part of a macOS local identifier ("UUID/L0/001").
    public var uuid: String {
        photosIdentifier.split(separator: "/").first.map(String.init) ?? photosIdentifier
    }
}
```

- [ ] **Step 8: Remove the smoke test and run everything**

```bash
rm Tests/ArchiveCoreTests/SmokeTests.swift
swift test
```
Expected: `5 tests passed`.

- [ ] **Step 9: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): EngineError with PhotoKit code mapping; AssetRecord and Locality

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Pure classification rules and the scan summary

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/AssetFacts.swift`
- Create: `engine/Sources/ArchiveCore/Library/AssetClassifier.swift`
- Create: `engine/Tests/ArchiveCoreTests/AssetClassifierTests.swift`

Background for the engineer: `PHAsset.sourceType` is an option set. Raw value 1 is the user library, 2 is a cloud-shared (shared album) asset, 4 is iTunes-synced. The spike showed shared-album assets refuse deletion and report no size (spike results, finding 12). Only raw value exactly 1 is archivable. `dataSize` is nil for assets the engine must not archive; a user-library asset with nil size is excluded with its own reason so the count is visible.

- [ ] **Step 1: Write the failing classifier tests**

`engine/Tests/ArchiveCoreTests/AssetClassifierTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

private func facts(sourceType: Int = 1, size: Int? = 1_000, hasVideoResource: Bool = true) -> AssetFacts {
    AssetFacts(
        photosIdentifier: "AAAA-1/L0/001",
        sourceTypeRawValue: sourceType,
        hasOriginalVideoResource: hasVideoResource,
        originalFilename: "IMG_0001.MOV",
        sizeBytes: size,
        creationDate: Date(timeIntervalSince1970: 0),
        latitude: nil,
        longitude: nil,
        durationSeconds: 1,
        pixelWidth: 10,
        pixelHeight: 10,
        isFavorite: false,
        hasAdjustments: false
    )
}

@Test func userLibraryVideoWithSizeIsIncluded() {
    let c = AssetClassifier.classify(facts())
    guard case .included(let record) = c else { Issue.record("expected included"); return }
    #expect(record.sizeBytes == 1_000)
    #expect(record.locality == .unknown)
}

@Test func cloudSharedIsExcluded() {
    #expect(AssetClassifier.classify(facts(sourceType: 2)) == .excluded(.notUserLibrary))
}

@Test func iTunesSyncedIsExcluded() {
    #expect(AssetClassifier.classify(facts(sourceType: 4)) == .excluded(.notUserLibrary))
}

@Test func mixedSourceTypeIsExcluded() {
    #expect(AssetClassifier.classify(facts(sourceType: 3)) == .excluded(.notUserLibrary))
}

@Test func missingSizeIsExcluded() {
    #expect(AssetClassifier.classify(facts(size: nil)) == .excluded(.sizeUnknown))
}

@Test func missingVideoResourceIsExcluded() {
    #expect(AssetClassifier.classify(facts(hasVideoResource: false)) == .excluded(.noOriginalVideoResource))
}

@Test func summaryCountsEveryOutcome() {
    var summary = ScanSummary()
    summary.count(AssetClassifier.classify(facts()))
    summary.count(AssetClassifier.classify(facts(sourceType: 2)))
    summary.count(AssetClassifier.classify(facts(sourceType: 2)))
    summary.count(AssetClassifier.classify(facts(size: nil)))
    #expect(summary.included == 1)
    #expect(summary.excluded[.notUserLibrary] == 2)
    #expect(summary.excluded[.sizeUnknown] == 1)
    #expect(summary.excluded[.noOriginalVideoResource] == nil)
    #expect(summary.total == 4)
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `swift test --filter AssetClassifierTests`
Expected: compile error, `cannot find 'AssetFacts' in scope`.

- [ ] **Step 3: Implement AssetFacts**

`engine/Sources/ArchiveCore/Library/AssetFacts.swift`:

```swift
import Foundation

/// Everything the classifier needs about one PHAsset, read once by the scanner.
/// PhotoKit-free so the rules are testable without a library.
public struct AssetFacts: Equatable, Sendable {
    public var photosIdentifier: String
    public var sourceTypeRawValue: Int          // PHAssetSourceType raw value; 1 = user library
    public var hasOriginalVideoResource: Bool
    public var originalFilename: String
    public var sizeBytes: Int?                  // PHAssetResource.dataSize, nil when Photos does not know
    public var creationDate: Date?
    public var latitude: Double?
    public var longitude: Double?
    public var durationSeconds: Double
    public var pixelWidth: Int
    public var pixelHeight: Int
    public var isFavorite: Bool
    public var hasAdjustments: Bool

    public init(photosIdentifier: String, sourceTypeRawValue: Int, hasOriginalVideoResource: Bool,
                originalFilename: String, sizeBytes: Int?, creationDate: Date?,
                latitude: Double?, longitude: Double?, durationSeconds: Double,
                pixelWidth: Int, pixelHeight: Int, isFavorite: Bool, hasAdjustments: Bool) {
        self.photosIdentifier = photosIdentifier
        self.sourceTypeRawValue = sourceTypeRawValue
        self.hasOriginalVideoResource = hasOriginalVideoResource
        self.originalFilename = originalFilename
        self.sizeBytes = sizeBytes
        self.creationDate = creationDate
        self.latitude = latitude
        self.longitude = longitude
        self.durationSeconds = durationSeconds
        self.pixelWidth = pixelWidth
        self.pixelHeight = pixelHeight
        self.isFavorite = isFavorite
        self.hasAdjustments = hasAdjustments
    }
}
```

- [ ] **Step 4: Implement the classifier and summary**

`engine/Sources/ArchiveCore/Library/AssetClassifier.swift`:

```swift
import Foundation

/// Why an asset is left alone. Surfaced to the user as counts ("12 videos in shared albums were left alone").
public enum ExclusionReason: String, Codable, Sendable, CaseIterable {
    case notUserLibrary          // shared album, iTunes-synced, or any mix: invariant 7
    case noOriginalVideoResource
    case sizeUnknown             // dataSize nil; Photos itself does not know the original's size
}

public enum Classification: Equatable, Sendable {
    case included(AssetRecord)
    case excluded(ExclusionReason)
}

/// The rules. Pure, and the only place they live.
public enum AssetClassifier {
    /// PHAssetSourceType.typeUserLibrary raw value. Exactly this value, no other bits.
    public static let userLibrarySourceType = 1

    public static func classify(_ f: AssetFacts) -> Classification {
        guard f.sourceTypeRawValue == userLibrarySourceType else { return .excluded(.notUserLibrary) }
        guard f.hasOriginalVideoResource else { return .excluded(.noOriginalVideoResource) }
        guard let size = f.sizeBytes else { return .excluded(.sizeUnknown) }
        return .included(AssetRecord(
            photosIdentifier: f.photosIdentifier,
            originalFilename: f.originalFilename,
            sizeBytes: size,
            creationDate: f.creationDate,
            latitude: f.latitude,
            longitude: f.longitude,
            durationSeconds: f.durationSeconds,
            pixelWidth: f.pixelWidth,
            pixelHeight: f.pixelHeight,
            isFavorite: f.isFavorite,
            hasAdjustments: f.hasAdjustments,
            locality: .unknown
        ))
    }
}

/// Counts by outcome for one scan.
public struct ScanSummary: Codable, Equatable, Sendable {
    public var included = 0
    public var excluded: [ExclusionReason: Int] = [:]

    public init() {}

    public var total: Int { included + excluded.values.reduce(0, +) }

    public mutating func count(_ c: Classification) {
        switch c {
        case .included: included += 1
        case .excluded(let reason): excluded[reason, default: 0] += 1
        }
    }
}
```

- [ ] **Step 5: Run the classifier tests**

Run: `swift test --filter AssetClassifierTests`
Expected: `7 tests passed`. If `ScanSummary` fails to compile as `Codable` because of the dictionary key, add `extension ExclusionReason: CodingKeyRepresentable {}` at the bottom of the file; on macOS 27 `String`-raw enums encode as dictionary keys without it.

- [ ] **Step 6: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): AssetFacts, pure AssetClassifier with shared-album exclusion, ScanSummary

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: PhotoKit scanner adapter

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/PhotoKitLibraryScanner.swift`

No unit test: this file only reads PhotoKit and hands the facts to the tested classifier. It is exercised by the harness in Task 6 on the real library.

- [ ] **Step 1: Implement the scanner**

`engine/Sources/ArchiveCore/Library/PhotoKitLibraryScanner.swift`:

```swift
import Foundation
import Photos

/// One PhotoKit sweep of all videos, mapped through AssetClassifier.
/// The only PhotoKit reads in the engine's library layer live here.
public final class PhotoKitLibraryScanner {
    public struct Result: Sendable {
        public var records: [AssetRecord]
        public var summary: ScanSummary
        public var sweepCount: Int
        public var elapsedSeconds: Double
    }

    public init() {}

    /// Requests read-write authorization (deletion later needs it) and returns the status.
    public static func requestAuthorization() async -> PHAuthorizationStatus {
        await PHPhotoLibrary.requestAuthorization(for: .readWrite)
    }

    public func scan() -> Result {
        let start = Date()
        let options = PHFetchOptions()
        options.includeHiddenAssets = true
        let fetch = PHAsset.fetchAssets(with: .video, options: options)

        var records: [AssetRecord] = []
        var summary = ScanSummary()
        fetch.enumerateObjects { asset, _, _ in
            let classification = AssetClassifier.classify(Self.facts(for: asset))
            summary.count(classification)
            if case .included(let record) = classification { records.append(record) }
        }
        return Result(records: records, summary: summary, sweepCount: fetch.count,
                      elapsedSeconds: Date().timeIntervalSince(start))
    }

    /// The original video resource: `.video`, or `.fullSizeVideo` when there is no unedited original.
    public static func originalVideoResource(for asset: PHAsset) -> PHAssetResource? {
        let resources = PHAssetResource.assetResources(for: asset)
        return resources.first { $0.type == .video } ?? resources.first { $0.type == .fullSizeVideo }
    }

    public static func facts(for asset: PHAsset) -> AssetFacts {
        let resource = originalVideoResource(for: asset)
        return AssetFacts(
            photosIdentifier: asset.localIdentifier,
            sourceTypeRawValue: Int(asset.sourceType.rawValue),
            hasOriginalVideoResource: resource != nil,
            originalFilename: resource?.originalFilename ?? "",
            sizeBytes: resource?.dataSize,
            creationDate: asset.creationDate,
            latitude: asset.location?.coordinate.latitude,
            longitude: asset.location?.coordinate.longitude,
            durationSeconds: asset.duration,
            pixelWidth: asset.pixelWidth,
            pixelHeight: asset.pixelHeight,
            isFavorite: asset.isFavorite,
            hasAdjustments: asset.hasAdjustments
        )
    }

    /// Direct fetch by local identifier. macOS identifiers take the form "UUID/L0/001" (spike finding 5).
    public static func fetchAsset(uuid: String) -> PHAsset? {
        for id in ["\(uuid)/L0/001", uuid] {
            if let a = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject { return a }
        }
        return nil
    }
}
```

- [ ] **Step 2: Build**

Run: `swift build`
Expected: succeeds. If `resource?.dataSize` fails to compile as `Int?`, replace it with `resource.flatMap { $0.dataSize }` and, if the property is exposed as `__dataSize` (NS_REFINED_FOR_SWIFT), use `resource?.__dataSize?.intValue`. The spike compiled `resource.dataSize` as `Int?` against the macOS 27 SDK, so the first form should work.

- [ ] **Step 3: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): PhotoKitLibraryScanner sweep mapped through the classifier

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Locality probe

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/LocalityProbe.swift`
- Create: `engine/Tests/ArchiveCoreTests/LocalityProbeTests.swift`

The probe is a `requestData` with network disallowed: success means the bytes are local, PhotoKit error 3164 means cloud-only, anything else is unknown (spike results, findings 3 and 8). The mapping from outcome to `Locality` is pure and tested; the PhotoKit call is not.

- [ ] **Step 1: Write the failing mapping tests**

`engine/Tests/ArchiveCoreTests/LocalityProbeTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

@Test func noErrorMeansLocal() {
    #expect(LocalityProbe.locality(fromProbeError: nil) == .local)
}

@Test func networkAccessRequiredMeansCloudOnly() {
    let e = NSError(domain: "PHPhotosErrorDomain", code: 3164)
    #expect(LocalityProbe.locality(fromProbeError: e) == .cloudOnly)
}

@Test func otherErrorsMeanUnknown() {
    let e = NSError(domain: "PHPhotosErrorDomain", code: 3303)
    #expect(LocalityProbe.locality(fromProbeError: e) == .unknown)
    let posix = NSError(domain: NSPOSIXErrorDomain, code: 5)
    #expect(LocalityProbe.locality(fromProbeError: posix) == .unknown)
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `swift test --filter LocalityProbeTests`
Expected: compile error, `cannot find 'LocalityProbe' in scope`.

- [ ] **Step 3: Implement the probe**

`engine/Sources/ArchiveCore/Library/LocalityProbe.swift`:

```swift
import Foundation
import Photos

/// Decides whether an original's bytes are on this Mac by asking PhotoKit for them
/// with network access disallowed. Reads the whole file when it is local, so callers
/// probe only the assets they are about to act on, never the whole library.
public final class LocalityProbe {
    private let manager = PHAssetResourceManager.default()

    public init() {}

    public static func locality(fromProbeError error: Error?) -> Locality {
        guard let error else { return .local }
        return EngineError.from(error).isNetworkAccessRequired ? .cloudOnly : .unknown
    }

    public func probe(_ resource: PHAssetResource) async -> Locality {
        let options = PHAssetResourceRequestOptions()
        options.isNetworkAccessAllowed = false
        let error: Error? = await withCheckedContinuation { continuation in
            var resumed = false
            manager.requestData(for: resource, options: options, dataReceivedHandler: { _ in }) { error in
                guard !resumed else { return }
                resumed = true
                continuation.resume(returning: error)
            }
        }
        return Self.locality(fromProbeError: error)
    }

    /// Convenience for a record: fetches the asset and its original resource, then probes.
    public func probe(uuid: String) async -> Locality {
        guard let asset = PhotoKitLibraryScanner.fetchAsset(uuid: uuid),
              let resource = PhotoKitLibraryScanner.originalVideoResource(for: asset) else { return .unknown }
        return await probe(resource)
    }
}
```

- [ ] **Step 4: Run all tests**

Run: `swift test`
Expected: `15 tests passed` (5 from Task 2, 7 from Task 3, 3 here).

- [ ] **Step 5: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): LocalityProbe with pure error-to-locality mapping

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Harness with the `scan` command

**Files:**
- Replace: `engine/Sources/ArchiveHarness/main.swift`
- Create: `engine/Sources/ArchiveHarness/OutputFolder.swift`
- Create: `engine/Sources/ArchiveHarness/JSONLWriter.swift`
- Create: `engine/Sources/ArchiveHarness/Commands/ScanCommand.swift`
- Create: `engine/Harness/Info.plist`
- Create: `engine/Harness/ArchiveHarness.entitlements`
- Create: `engine/Makefile`

The harness must run as a sandboxed app bundle launched by `open`, or macOS auto-denies Photos access (spike finding 6). The bundle can only write inside a folder the user picks, persisted as a security-scoped bookmark (spike, stage A update). This mirrors `spike/PhotoKitSpike/` and the Makefile there.

- [ ] **Step 1: Bookmark to the output folder**

`engine/Sources/ArchiveHarness/OutputFolder.swift`:

```swift
import AppKit
import Foundation

/// The one folder the sandboxed harness may write to. Chosen once in an open panel,
/// persisted as an app-scoped security-scoped bookmark, resolved without mounting.
enum OutputFolder {
    private static let key = "outputFolderBookmark"

    @MainActor
    static func obtain(forcePick: Bool) throws -> URL {
        if !forcePick, let data = UserDefaults.standard.data(forKey: key) {
            var stale = false
            if let url = try? URL(resolvingBookmarkData: data, options: [.withSecurityScope, .withoutMounting],
                                  relativeTo: nil, bookmarkDataIsStale: &stale),
               url.startAccessingSecurityScopedResource() {
                if stale { store(url) }
                return url
            }
        }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.prompt = "Use as output folder"
        panel.message = "Choose the folder where ArchiveHarness writes its results"
        NSApp.activate(ignoringOtherApps: true)
        guard panel.runModal() == .OK, let url = panel.url else {
            throw HarnessError.message("no output folder chosen")
        }
        store(url)
        _ = url.startAccessingSecurityScopedResource()
        return url
    }

    private static func store(_ url: URL) {
        if let data = try? url.bookmarkData(options: [.withSecurityScope], includingResourceValuesForKeys: nil, relativeTo: nil) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}

enum HarnessError: Error, CustomStringConvertible {
    case message(String)
    var description: String { switch self { case .message(let m): return m } }
}
```

- [ ] **Step 2: JSONL writer**

`engine/Sources/ArchiveHarness/JSONLWriter.swift`:

```swift
import Foundation

/// Append-only JSON Lines file. One encodable value per line.
final class JSONLWriter {
    private let handle: FileHandle
    private let encoder: JSONEncoder
    let url: URL

    init(url: URL) throws {
        self.url = url
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        handle = try FileHandle(forWritingTo: url)
        try handle.seekToEnd()
        encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
    }

    func write<T: Encodable>(_ value: T) throws {
        let data = try encoder.encode(value)
        handle.write(data)
        handle.write(Data("\n".utf8))
    }

    func close() { try? handle.close() }
}
```

- [ ] **Step 3: The scan command**

`engine/Sources/ArchiveHarness/Commands/ScanCommand.swift`:

```swift
import ArchiveCore
import Foundation

/// `scan [--probe N]`: sweep the library, write one AssetRecord per line plus a summary line.
/// With --probe N, the first N included records are locality-probed (cheap for cloud-only,
/// reads the file for local ones) so the probe path is exercised on real assets.
struct ScanCommand {
    var probeCount = 0

    struct SummaryLine: Encodable {
        var kind = "summary"
        var sweepCount: Int
        var included: Int
        var excluded: [String: Int]
        var probed: [String: Int]
        var elapsedSeconds: Double
    }

    func run(output: URL) async throws {
        let scanner = PhotoKitLibraryScanner()
        let result = scanner.scan()
        var records = result.records

        var probed: [String: Int] = [:]
        if probeCount > 0 {
            let probe = LocalityProbe()
            for i in records.indices.prefix(probeCount) {
                let locality = await probe.probe(uuid: records[i].uuid)
                records[i].locality = locality
                probed[locality.rawValue, default: 0] += 1
                print("probe \(records[i].uuid.prefix(8)) \(records[i].originalFilename) \(locality.rawValue)")
            }
        }

        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "")
        let writer = try JSONLWriter(url: output.appendingPathComponent("scan-\(stamp).jsonl"))
        defer { writer.close() }
        for record in records { try writer.write(record) }
        let excluded = Dictionary(uniqueKeysWithValues: result.summary.excluded.map { ($0.key.rawValue, $0.value) })
        let summary = SummaryLine(sweepCount: result.sweepCount, included: result.summary.included,
                                  excluded: excluded, probed: probed, elapsedSeconds: result.elapsedSeconds)
        try writer.write(summary)
        print("scan: sweep=\(result.sweepCount) included=\(result.summary.included) excluded=\(excluded) probed=\(probed) in \(String(format: "%.2f", result.elapsedSeconds))s")
        print("wrote \(writer.url.path)")
    }
}
```

- [ ] **Step 4: The entry point**

Replace `engine/Sources/ArchiveHarness/main.swift`:

```swift
import AppKit
import ArchiveCore
import Foundation
import Photos

/// Headless harness for ArchiveCore. Runs inside a sandboxed bundle launched by `open`
/// so the Photos permission attaches to the bundle. Output goes to a user-chosen folder;
/// stdout is mirrored into <output>/latest.log because `open` has no terminal.
///
///   ArchiveHarness.app --command scan [--probe N] [--pick-output]

struct Args {
    var command = "scan"
    var probe = 0
    var pickOutput = false

    init() {
        var it = CommandLine.arguments.dropFirst().makeIterator()
        while let a = it.next() {
            switch a {
            case "--command": command = it.next() ?? command
            case "--probe": probe = Int(it.next() ?? "0") ?? 0
            case "--pick-output": pickOutput = true
            default: fputs("unknown argument \(a)\n", stderr); exit(2)
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        Task { @MainActor in exit(await run()) }
    }
}

@MainActor
func run() async -> Int32 {
    let args = Args()
    let output: URL
    do { output = try OutputFolder.obtain(forcePick: args.pickOutput) } catch {
        fputs("\(error)\n", stderr); return 1
    }
    defer { output.stopAccessingSecurityScopedResource() }

    if isatty(STDOUT_FILENO) == 0 {
        let log = output.appendingPathComponent("latest.log").path
        freopen(log, "a", stdout)
        freopen(log, "a", stderr)
        setvbuf(stdout, nil, _IOLBF, 0)
        print("---- \(ISO8601DateFormatter().string(from: Date())) \(CommandLine.arguments.dropFirst().joined(separator: " "))")
    }

    let status = await PhotoKitLibraryScanner.requestAuthorization()
    print("photos authorization: \(status.rawValue) (\(status == .authorized ? "authorized" : "NOT authorized"))")
    guard status == .authorized else { return 3 }
    print("ArchiveCore \(ArchiveCore.version), sandboxed=\(ProcessInfo.processInfo.environment["APP_SANDBOX_CONTAINER_ID"] != nil)")

    do {
        switch args.command {
        case "scan": try await ScanCommand(probeCount: args.probe).run(output: output)
        default: fputs("unknown command \(args.command)\n", stderr); return 2
        }
    } catch {
        fputs("failed: \(error)\n", stderr); return 5
    }
    return 0
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
```

- [ ] **Step 5: Bundle metadata**

`engine/Harness/Info.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.videoattic.ArchiveHarness</string>
    <key>CFBundleName</key>
    <string>ArchiveHarness</string>
    <key>CFBundleExecutable</key>
    <string>ArchiveHarness</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>27.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSPhotoLibraryUsageDescription</key>
    <string>ArchiveHarness is the developer harness for Video Attic's engine. It scans videos in your library and, for commands you run explicitly, downloads, deletes, or restores them.</string>
</dict>
</plist>
```

`engine/Harness/ArchiveHarness.entitlements`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.app-sandbox</key>
    <true/>
    <key>com.apple.security.personal-information.photos-library</key>
    <true/>
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>
    <key>com.apple.security.files.bookmarks.app-scope</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 6: Makefile**

`engine/Makefile`:

```makefile
# Build the ArchiveCore package, wrap ArchiveHarness into a signed sandboxed bundle, run it.
#
#   make                 swift build (release) + bundle + sign
#   make test            swift test
#   make scan ARGS="--probe 10"
#   make reset-tcc       forget the Photos permission for the harness bundle

APP       := build/ArchiveHarness.app
BIN       := $(APP)/Contents/MacOS/ArchiveHarness
BUILT     := .build/release/ArchiveHarness
IDENTITY  ?= $(shell security find-identity -v -p codesigning 2>/dev/null | grep "Apple Development" | head -1 | awk '{print $$2}')
BUNDLE_ID := com.videoattic.ArchiveHarness
SOURCES   := $(shell find Sources -name '*.swift') Package.swift

.PHONY: all test scan reset-tcc clean

all: $(BIN)

$(BUILT): $(SOURCES)
	swift build -c release --product ArchiveHarness

$(BIN): $(BUILT) Harness/Info.plist Harness/ArchiveHarness.entitlements
	mkdir -p $(APP)/Contents/MacOS
	cp Harness/Info.plist $(APP)/Contents/Info.plist
	cp $(BUILT) $(BIN)
	codesign --force --sign $(IDENTITY) --entitlements Harness/ArchiveHarness.entitlements --timestamp=none $(APP)
	@codesign -d --entitlements - $(APP) 2>&1 | grep -q app-sandbox && echo "signed with sandbox entitlements"

test:
	swift test

scan: $(BIN)
	open -W -a $(CURDIR)/$(APP) --args --command scan $(ARGS)
	@echo "output is in the chosen folder's latest.log"

reset-tcc:
	tccutil reset Photos $(BUNDLE_ID)

clean:
	rm -rf build .build
```

- [ ] **Step 7: Build the bundle**

Run: `make`
Expected: `swift build` succeeds, then `signed with sandbox entitlements`. If `security find-identity` returns nothing, run `make IDENTITY=-` to sign ad hoc; the sandbox still applies.

- [ ] **Step 8: First run, picking the output folder**

Create the output folder and run:

```bash
mkdir -p /Users/camoiloc/IdeaProjects/iphoto/engine/scratch
make scan ARGS="--pick-output --probe 10"
```

A folder picker appears: choose `engine/scratch`. Then the Photos permission prompt for "ArchiveHarness": allow. Then read the log:

```bash
tail -n 20 scratch/latest.log
```

Expected, on this Mac (numbers from the spike as of 2026-09-06): `sweep=53xx`, `included` several thousand, `excluded` containing `notUserLibrary` in the dozens or more (shared albums), `sizeUnknown` zero or near zero, and ten `probe` lines with `local` or `cloudOnly`. Any `unknown` probe result or a non-empty `noOriginalVideoResource` count is worth a note in the journal but does not fail the slice.

- [ ] **Step 9: Check the JSONL**

```bash
f=$(ls -t scratch/scan-*.jsonl | head -1); wc -l "$f"; tail -n 1 "$f"; head -n 1 "$f"
```
Expected: line count equals `included + 1`; the last line is the summary; the first line is an `AssetRecord` with `sizeBytes` and `photosIdentifier` ending in `/L0/001`.

- [ ] **Step 10: Ignore the scratch folder**

Append to the repo-root `.gitignore`:

```
/engine/scratch/
```

Do not commit yet; Task 7 ships the slice with the ledger in the same commit.

---

### Task 7: Ship the slice (ledger in the same commit)

**Files:**
- Modify: `docs/COVERAGE.md` (three engine rows)
- Modify: `docs/STATE.md` (Now, Next)
- Modify: `CHANGELOG.md` (Unreleased)
- Create: `docs/journal/2026-09-XX-engine-slice-1.md` (use the real date)

- [ ] **Step 1: Flip the coverage rows**

In `docs/COVERAGE.md`, change these three rows in the Engine table:

```
| Library scan via PhotoKit sweep | shipped (slice 1) | engine | 7 | `engine/Sources/ArchiveCore/Library/PhotoKitLibraryScanner.swift` |
| Locality probe (network-disallowed request) | shipped (slice 1) | engine | 7 | `engine/Sources/ArchiveCore/Library/LocalityProbe.swift` |
| Shared-album exclusion | shipped (slice 1) | engine | 7 | `engine/Sources/ArchiveCore/Library/AssetClassifier.swift` |
```

and the last row of the Engine table:

```
| Developer CLI for the engine | in progress (`scan` shipped, slice 1) | engine | 4 | `engine/Sources/ArchiveHarness/` |
```

- [ ] **Step 2: Rewrite STATE Now and Next**

In `docs/STATE.md`, replace the `## Now` section with:

```
## Now

- Phase 1, Engine, slice 2: Manifest v2, ArchiveLayout, ManifestV1Adapter with a real fixture, harness `adopt`. Plan to be written from spec section "Archive layout" and "Adopting the existing archive".
```

and remove item 1 from `## Next (ordered)`, renumbering the rest.

- [ ] **Step 3: Changelog line**

Under `## [Unreleased]` in `CHANGELOG.md`, add at the top:

```
- <date> engine: slice 1 shipped; ArchiveCore package with PhotoKit scan, shared-album exclusion, locality probe, and the sandboxed ArchiveHarness `scan` command (`engine/`).
```

- [ ] **Step 4: Journal entry**

`docs/journal/<date>-engine-slice-1.md`:

```markdown
# Engine slice 1

What shipped: `engine/` package, scanner, classifier, probe, harness `scan`.

Real-library run on this Mac: sweep=<n> included=<n> excluded={notUserLibrary: <n>, ...} probed={local: <n>, cloudOnly: <n>}.

Surprises: <anything that differed from the spike, or "none">.

Next session should know: slice 2 needs one real Python manifest copied from the Acer drive into `engine/Fixtures/` while the drive is mounted and idle.
```

Fill the angle brackets from `scratch/latest.log`.

- [ ] **Step 5: Run the full checks one last time**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto/engine && swift test && make
```
Expected: `15 tests passed`, bundle signed.

- [ ] **Step 6: Commit code and ledger together**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine .gitignore docs/COVERAGE.md docs/STATE.md CHANGELOG.md docs/journal
git commit -m "feat(engine): slice 1, sandboxed harness scan on the real library

ArchiveHarness bundle built from the SwiftPM executable, signed with the
sandbox, Photos, and bookmark entitlements, launched via open. The scan
command sweeps the library through the classifier and writes JSONL plus
a summary; --probe N exercises LocalityProbe on real assets. Coverage
rows for scan, probe, and shared-album exclusion flip to shipped; STATE
moves to slice 2.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review against the spec

- Spec "LibraryScanner": Task 4 (sweep, hidden assets, exclusion before anything else, summary by reason). Covered.
- Spec "LocalityProbe": Task 5 (network-disallowed request, 3164, on demand not whole library). Covered; the harness limits probing to `--probe N`.
- Spec data model `AssetRecord` fields: Task 2 matches the table, with `sourceType` consumed by the classifier rather than stored, since only user-library assets become records. `locality` defaults to `.unknown` until probed.
- Spec "Harness": Task 6 provides `scan`; the other commands belong to later slices as the spec's slice list says.
- Spec invariants 4 and 7: sandbox entitlements in Task 6, exclusion rule in Task 3, no private API anywhere.
- Types: `AssetFacts`, `AssetRecord`, `Locality`, `Classification`, `ExclusionReason`, `ScanSummary`, `EngineError`, `PhotoKitLibraryScanner`, `LocalityProbe` are named identically across tasks. `PhotoKitLibraryScanner.fetchAsset(uuid:)` and `originalVideoResource(for:)` are defined in Task 4 and used in Task 5.
- Placeholders: none. The only angle brackets are in the journal template, to be filled from the real log.
