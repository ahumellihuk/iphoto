# Engine Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Rewritten 2026-09-06 against [engine spec v2](../specs/2026-09-06-engine-core-v2.md) after the [red team](../research/redteam/2026-09-06-consolidated.md); the [dry run](../research/redteam/2026-09-06-plan-dry-run.md) verified the first version's code compiles on this toolchain, and its thirteen defects are fixed here.

**Goal:** A Swift package `ArchiveCore` that scans the Photos library through PhotoKit, keeps only videos the family alone owns and has not edited, sizes them exactly on macOS 27 and by estimate on 26, reports the library environment including a Shared Library detection attempt, probes whether an original is local, and a headless sandboxed harness that runs all of it on this Mac and writes JSONL.

**Architecture:** PhotoKit is touched in exactly three files (`PhotoKitLibraryScanner.swift`, `LocalityProbe.swift`, `LibraryEnvironment.swift`); everything they decide flows through pure value types (`AssetFacts`, `AssetRecord`, `SizeInfo`, `Classification`, `ScanSummary`, `EnvironmentReport`) whose rules are unit-tested without a library. The harness is a SwiftPM executable wrapped into an app bundle by a Makefile, signed with the sandbox and Photos entitlements using the Apple Development identity, launched through `open -n -W` so permissions attach to the bundle.

**Tech Stack:** Swift 6.4 toolchain in Xcode 27 beta, SwiftPM, Swift Testing (`import Testing`, `@Suite`), PhotoKit, Synchronization (`Mutex`), AppKit for the open panel. Minimum macOS 26; `dataSize` behind `#available(macOS 27, *)`.

---

## File structure

```
engine/
  Package.swift
  Makefile
  Sources/ArchiveCore/
    ArchiveCore.swift                        version constant
    Support/EngineError.swift                typed errors, PhotoKit error mapping
    Support/OneShot.swift                    one-shot continuation box on Mutex
    Library/SizeInfo.swift                   exact or estimated size, estimator table
    Library/AssetFacts.swift                 raw facts read from a PHAsset, PhotoKit-free
    Library/AssetRecord.swift                AssetRecord, Locality
    Library/AssetClassifier.swift            pure include/exclude rules, ExclusionReason, ScanSummary
    Library/PhotoKitLibraryScanner.swift     PHAsset sweep -> AssetFacts -> records (imports Photos)
    Library/LocalityProbe.swift              network-disallowed requestData with timeout (imports Photos)
    Library/LibraryEnvironment.swift         authorization, counts, canaries, Shared Library probe (imports Photos)
  Sources/ArchiveHarness/
    main.swift                               arg parsing, NSApplication, dispatch
    OutputFolder.swift                       security-scoped bookmark to the output folder
    JSONLWriter.swift                        append-only JSONL
    Commands/ScanCommand.swift               `scan`
    Commands/EnvironmentCommand.swift        `environment`
  Harness/Info.plist
  Harness/ArchiveHarness.entitlements
  Tests/ArchiveCoreTests/
    EngineErrorTests.swift
    SizeInfoTests.swift
    AssetRecordTests.swift
    AssetClassifierTests.swift
    ScannerRulesTests.swift
    LocalityProbeTests.swift
    LibraryEnvironmentTests.swift
```

Conventions for every task:
- Run commands from `/Users/camoiloc/IdeaProjects/iphoto/engine` unless a step says otherwise.
- Swift language mode 5 on all targets.
- Every test file wraps its tests in `@Suite struct <FileName>` so `swift test --filter <FileName>` selects exactly that file. Swift Testing prints `Test run with N tests in M suites passed after ...`; the Expected lines below quote that phrasing.
- The working tree has unrelated Python changes (`README.md`, `src/iphoto/*.py`, `tests/test_*.py`). Use only the `git add` paths listed; never `git add -A`, `git add .`, or `git commit -a`.
- One commit per task, prefix `feat(engine):`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- The Makefile signs with the Apple Development identity on this Mac. Ad hoc signing changes the TCC attribution on every rebuild and is not used.

---

### Task 1: Package skeleton

**Files:**
- Create: `engine/Package.swift`
- Create: `engine/Sources/ArchiveCore/ArchiveCore.swift`
- Create: `engine/Sources/ArchiveHarness/main.swift` (placeholder, replaced in Task 9)
- Create: `engine/Tests/ArchiveCoreTests/SmokeTests.swift` (deleted in Task 2)
- Modify: `.gitignore` (repo root)

- [ ] **Step 1: Create the package manifest**

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ArchiveCore",
    platforms: [.macOS("26.0")],
    products: [
        .library(name: "ArchiveCore", targets: ["ArchiveCore"]),
        .executable(name: "ArchiveHarness", targets: ["ArchiveHarness"]),
    ],
    targets: [
        .target(name: "ArchiveCore", swiftSettings: [.swiftLanguageMode(.v5)]),
        .executableTarget(name: "ArchiveHarness", dependencies: ["ArchiveCore"], swiftSettings: [.swiftLanguageMode(.v5)]),
        .testTarget(name: "ArchiveCoreTests", dependencies: ["ArchiveCore"], swiftSettings: [.swiftLanguageMode(.v5)]),
    ]
)
```

- [ ] **Step 2: Library placeholder**

`engine/Sources/ArchiveCore/ArchiveCore.swift`:

```swift
/// ArchiveCore: the Video Attic engine. See docs/specs/2026-09-06-engine-core-v2.md.
public enum ArchiveCore {
    public static let version = "0.1.0"
}
```

- [ ] **Step 3: Harness placeholder**

`engine/Sources/ArchiveHarness/main.swift`:

```swift
import ArchiveCore

print("ArchiveHarness \(ArchiveCore.version)")
```

- [ ] **Step 4: Smoke test**

`engine/Tests/ArchiveCoreTests/SmokeTests.swift`:

```swift
import Testing
@testable import ArchiveCore

@Suite struct SmokeTests {
    @Test func versionIsSet() {
        #expect(ArchiveCore.version == "0.1.0")
    }
}
```

- [ ] **Step 5: Build and test**

Run: `swift build && swift test`
Expected: build succeeds; output ends with `Test run with 1 test in 1 suite passed`.

- [ ] **Step 6: Ignore build products**

Append to the repo-root `.gitignore`:

```
# engine build products and harness output
/engine/.build/
/engine/build/
/engine/scratch/
```

Note: `.build/release` is a symlink to `out/Products/Release` on this toolchain; `make` follows it.

- [ ] **Step 7: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine .gitignore
git commit -m "feat(engine): ArchiveCore package skeleton with harness and test targets

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Errors and the one-shot continuation

**Files:**
- Create: `engine/Sources/ArchiveCore/Support/EngineError.swift`
- Create: `engine/Sources/ArchiveCore/Support/OneShot.swift`
- Create: `engine/Tests/ArchiveCoreTests/EngineErrorTests.swift`
- Delete: `engine/Tests/ArchiveCoreTests/SmokeTests.swift`

- [ ] **Step 1: Write the failing tests**

`engine/Tests/ArchiveCoreTests/EngineErrorTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

@Suite struct EngineErrorTests {
    @Test func photoKitErrorIsClassifiedByCode() {
        let e = EngineError.from(NSError(domain: "PHPhotosErrorDomain", code: 3164))
        #expect(e == .photoKit(domain: "PHPhotosErrorDomain", code: 3164))
        #expect(e.isNetworkAccessRequired)
    }

    @Test func nonPhotoKitErrorIsWrappedAsUnderlying() {
        let e = EngineError.from(NSError(domain: NSPOSIXErrorDomain, code: 2))
        #expect(e == .underlying(domain: NSPOSIXErrorDomain, code: 2))
        #expect(!e.isNetworkAccessRequired)
    }

    @Test func engineErrorPassesThroughUnchanged() {
        #expect(EngineError.from(EngineError.message("x")) == .message("x"))
    }

    @Test func oneShotResumesExactlyOnce() async {
        let value: Int = await withCheckedContinuation { cont in
            let once = OneShot(cont)
            once.resume(1)
            once.resume(2)   // ignored
        }
        #expect(value == 1)
    }
}
```

- [ ] **Step 2: Run to verify failure**

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
    case timedOut(seconds: Int)
    case message(String)

    public static let photoKitDomain = "PHPhotosErrorDomain"
    /// PHPhotosError.networkAccessRequired: the original is not local and network was disallowed.
    public static let networkAccessRequiredCode = 3164
    /// PHPhotosError.userCancelled: what a cancelled request may report.
    public static let userCancelledCode = 3072

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

- [ ] **Step 4: Implement OneShot**

`engine/Sources/ArchiveCore/Support/OneShot.swift`:

```swift
import Synchronization

/// Resumes a checked continuation at most once, from any thread.
/// PhotoKit completions and watchdog timers race; this box makes the race harmless.
public final class OneShot<T: Sendable>: Sendable {
    private let slot: Mutex<CheckedContinuation<T, Never>?>

    public init(_ continuation: CheckedContinuation<T, Never>) {
        slot = Mutex(continuation)
    }

    public func resume(_ value: T) {
        slot.withLock { c in
            c?.resume(returning: value)
            c = nil
        }
    }
}
```

- [ ] **Step 5: Remove the smoke test and run**

```bash
rm Tests/ArchiveCoreTests/SmokeTests.swift
swift test --filter EngineErrorTests
```
Expected: `Test run with 4 tests in 1 suite passed`.

- [ ] **Step 6: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): EngineError with PhotoKit code mapping; OneShot continuation box

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: SizeInfo and the estimator

Background: on macOS 27 `PHAssetResource.dataSize` gives the original's byte size; on 26 it does not exist. The estimator uses Apple's HEVC "High Efficiency" bitrates as measured in the demand research (4K60 about 400 MB/min, 4K30 about 170 MB/min, 1080p60 about 90 MB/min, 1080p30 about 60 MB/min, 720p about 40 MB/min). Frame rate is unknown before download, so each tier uses its 60 fps figure; budgets multiply estimates by 1.25 on top.

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/SizeInfo.swift`
- Create: `engine/Tests/ArchiveCoreTests/SizeInfoTests.swift`

- [ ] **Step 1: Write the failing tests**

`engine/Tests/ArchiveCoreTests/SizeInfoTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

@Suite struct SizeInfoTests {
    @Test func exactWinsWhenKnown() {
        let s = SizeInfo.make(exactBytes: 1_234, durationSeconds: 60, pixelWidth: 3840, pixelHeight: 2160)
        #expect(s == .exact(bytes: 1_234))
        #expect(s.bytes == 1_234)
        #expect(s.budgetBytes == 1_234)
    }

    @Test func fourKEstimateUsesTheSixtyFpsRate() {
        let s = SizeInfo.make(exactBytes: nil, durationSeconds: 60, pixelWidth: 3840, pixelHeight: 2160)
        #expect(s == .estimated(bytes: 400 * 1_048_576))
        #expect(s.budgetBytes == Int(Double(400 * 1_048_576) * 1.25))
    }

    @Test func portraitOrientationIsTheSameTier() {
        let landscape = SizeInfo.make(exactBytes: nil, durationSeconds: 10, pixelWidth: 1920, pixelHeight: 1080)
        let portrait = SizeInfo.make(exactBytes: nil, durationSeconds: 10, pixelWidth: 1080, pixelHeight: 1920)
        #expect(landscape == portrait)
        #expect(landscape == .estimated(bytes: 90 * 1_048_576 * 10 / 60))
    }

    @Test func smallAndZeroDurationsEstimateAtLeastOneMegabyte() {
        #expect(SizeInfo.make(exactBytes: nil, durationSeconds: 0, pixelWidth: 720, pixelHeight: 1280) == .estimated(bytes: 1_048_576))
    }

    @Test func encodesKindAndBytes() throws {
        let data = try JSONEncoder().encode(SizeInfo.estimated(bytes: 5))
        let text = String(data: data, encoding: .utf8)
        #expect(text == #"{"bytes":5,"kind":"estimated"}"# || text == #"{"kind":"estimated","bytes":5}"#)
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `swift test --filter SizeInfoTests`
Expected: compile error, `cannot find 'SizeInfo' in scope`.

- [ ] **Step 3: Implement**

`engine/Sources/ArchiveCore/Library/SizeInfo.swift`:

```swift
import Foundation

/// The size of an original video: exact from PhotoKit on macOS 27, estimated from
/// duration and resolution on macOS 26. Budgets use `budgetBytes`; catalogs record
/// the real size after download.
public enum SizeInfo: Equatable, Sendable, Codable {
    case exact(bytes: Int)
    case estimated(bytes: Int)

    public var bytes: Int {
        switch self { case .exact(let b), .estimated(let b): return b }
    }

    /// Estimates carry a 25 percent safety factor for space planning.
    public var budgetBytes: Int {
        switch self {
        case .exact(let b): return b
        case .estimated(let b): return Int(Double(b) * 1.25)
        }
    }

    public var isExact: Bool { if case .exact = self { return true } else { return false } }

    /// Megabytes per minute at 60 fps, HEVC High Efficiency, by pixel count tier.
    static func megabytesPerMinute(pixels: Int) -> Int {
        switch pixels {
        case 8_000_000...: return 400      // 4K
        case 2_000_000...: return 90       // 1080p
        default: return 40                 // 720p and below
        }
    }

    public static func make(exactBytes: Int?, durationSeconds: Double, pixelWidth: Int, pixelHeight: Int) -> SizeInfo {
        if let exact = exactBytes { return .exact(bytes: exact) }
        let rate = megabytesPerMinute(pixels: pixelWidth * pixelHeight)
        let bytes = Int(Double(rate * 1_048_576) * durationSeconds / 60.0)
        return .estimated(bytes: max(bytes, 1_048_576))
    }

    private enum CodingKeys: String, CodingKey { case kind, bytes }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let kind = try c.decode(String.self, forKey: .kind)
        let bytes = try c.decode(Int.self, forKey: .bytes)
        self = kind == "exact" ? .exact(bytes: bytes) : .estimated(bytes: bytes)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(isExact ? "exact" : "estimated", forKey: .kind)
        try c.encode(bytes, forKey: .bytes)
    }
}
```

- [ ] **Step 4: Run**

Run: `swift test --filter SizeInfoTests`
Expected: `Test run with 5 tests in 1 suite passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): SizeInfo, exact on macOS 27 and estimated by resolution tier on 26

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: AssetFacts and AssetRecord

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/AssetFacts.swift`
- Create: `engine/Sources/ArchiveCore/Library/AssetRecord.swift`
- Create: `engine/Tests/ArchiveCoreTests/AssetRecordTests.swift`

- [ ] **Step 1: Write the failing tests**

`engine/Tests/ArchiveCoreTests/AssetRecordTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

func sampleRecord() -> AssetRecord {
    AssetRecord(
        photosIdentifier: "29953236-D636-4220-A0BD-4FA3537E2D54/L0/001",
        originalFilename: "IMG_9946.MOV",
        size: .exact(bytes: 21_579_228),
        creationDate: Date(timeIntervalSince1970: 1_663_348_475),
        modificationDate: Date(timeIntervalSince1970: 1_663_348_480),
        latitude: 51.5215, longitude: 0.1213, altitude: 12.0,
        durationSeconds: 18.7, pixelWidth: 1920, pixelHeight: 1080,
        isFavorite: false, isHidden: false, hasAdjustments: false,
        mediaSubtypesRaw: 0, albumTitles: ["Family"],
        locality: .unknown, probedAt: nil
    )
}

@Suite struct AssetRecordTests {
    @Test func recordRoundTripsThroughJSON() throws {
        let original = sampleRecord()
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AssetRecord.self, from: data)
        #expect(decoded == original)
    }

    @Test func uuidIsTheIdentifierPrefix() {
        #expect(sampleRecord().uuid == "29953236-D636-4220-A0BD-4FA3537E2D54")
    }

    @Test func malformedIdentifierHasNoUUID() {
        var r = sampleRecord()
        r.photosIdentifier = "not-a-uuid"
        #expect(r.uuid == nil)
    }

    @Test func localityEncodesAsAString() throws {
        let data = try JSONEncoder().encode(Locality.cloudOnly)
        #expect(String(data: data, encoding: .utf8) == "\"cloudOnly\"")
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `swift test --filter AssetRecordTests`
Expected: compile error, `cannot find 'AssetRecord' in scope`.

- [ ] **Step 3: Implement AssetFacts**

`engine/Sources/ArchiveCore/Library/AssetFacts.swift`:

```swift
import Foundation

/// Everything the classifier needs about one PHAsset, read once by the scanner.
/// PhotoKit-free so the rules are testable without a library. Every field that is
/// cheap now and impossible after deletion is captured here (red team finding 13).
public struct AssetFacts: Equatable, Sendable {
    public var photosIdentifier: String
    public var sourceTypeRawValue: Int          // PHAssetSourceType raw value; 1 = user library exactly
    public var hasOriginalVideoResource: Bool   // a `.video` resource exists; `.fullSizeVideo` does not count
    public var originalFilename: String
    public var exactSizeBytes: Int?             // PHAssetResource.dataSize on macOS 27; nil on 26 or when Photos does not know
    public var creationDate: Date?
    public var modificationDate: Date?
    public var latitude: Double?
    public var longitude: Double?
    public var altitude: Double?
    public var durationSeconds: Double
    public var pixelWidth: Int
    public var pixelHeight: Int
    public var isFavorite: Bool
    public var isHidden: Bool
    public var hasAdjustments: Bool
    public var mediaSubtypesRaw: UInt           // PHAssetMediaSubtype raw value
    public var albumTitles: [String]

    public init(photosIdentifier: String, sourceTypeRawValue: Int, hasOriginalVideoResource: Bool,
                originalFilename: String, exactSizeBytes: Int?, creationDate: Date?, modificationDate: Date?,
                latitude: Double?, longitude: Double?, altitude: Double?, durationSeconds: Double,
                pixelWidth: Int, pixelHeight: Int, isFavorite: Bool, isHidden: Bool, hasAdjustments: Bool,
                mediaSubtypesRaw: UInt, albumTitles: [String]) {
        self.photosIdentifier = photosIdentifier
        self.sourceTypeRawValue = sourceTypeRawValue
        self.hasOriginalVideoResource = hasOriginalVideoResource
        self.originalFilename = originalFilename
        self.exactSizeBytes = exactSizeBytes
        self.creationDate = creationDate
        self.modificationDate = modificationDate
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.durationSeconds = durationSeconds
        self.pixelWidth = pixelWidth
        self.pixelHeight = pixelHeight
        self.isFavorite = isFavorite
        self.isHidden = isHidden
        self.hasAdjustments = hasAdjustments
        self.mediaSubtypesRaw = mediaSubtypesRaw
        self.albumTitles = albumTitles
    }

    /// PHAssetMediaSubtype bits, copied so tests need no PhotoKit import.
    public static let subtypePhotoLive: UInt = 1 << 3
    public static let subtypeVideoHighFrameRate: UInt = 1 << 17
    public static let subtypeVideoCinematic: UInt = 1 << 21
}
```

- [ ] **Step 4: Implement AssetRecord and Locality**

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

/// The engine's view of one archivable user-library video. A value; safe to log and persist.
/// `photosIdentifier` is volatile and is never a catalog key (invariant 3).
public struct AssetRecord: Codable, Equatable, Sendable {
    public var photosIdentifier: String
    public var originalFilename: String
    public var size: SizeInfo
    public var creationDate: Date?
    public var modificationDate: Date?
    public var latitude: Double?
    public var longitude: Double?
    public var altitude: Double?
    public var durationSeconds: Double
    public var pixelWidth: Int
    public var pixelHeight: Int
    public var isFavorite: Bool
    public var isHidden: Bool
    public var hasAdjustments: Bool
    public var mediaSubtypesRaw: UInt
    public var albumTitles: [String]
    public var locality: Locality
    public var probedAt: Date?

    public init(photosIdentifier: String, originalFilename: String, size: SizeInfo,
                creationDate: Date?, modificationDate: Date?, latitude: Double?, longitude: Double?, altitude: Double?,
                durationSeconds: Double, pixelWidth: Int, pixelHeight: Int,
                isFavorite: Bool, isHidden: Bool, hasAdjustments: Bool, mediaSubtypesRaw: UInt,
                albumTitles: [String], locality: Locality, probedAt: Date?) {
        self.photosIdentifier = photosIdentifier
        self.originalFilename = originalFilename
        self.size = size
        self.creationDate = creationDate
        self.modificationDate = modificationDate
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.durationSeconds = durationSeconds
        self.pixelWidth = pixelWidth
        self.pixelHeight = pixelHeight
        self.isFavorite = isFavorite
        self.isHidden = isHidden
        self.hasAdjustments = hasAdjustments
        self.mediaSubtypesRaw = mediaSubtypesRaw
        self.albumTitles = albumTitles
        self.locality = locality
        self.probedAt = probedAt
    }

    /// The UUID part of a macOS local identifier ("UUID/L0/001"), or nil when the
    /// identifier does not have that shape. A malformed identifier must fail loudly,
    /// never be retried as if it were a UUID.
    public var uuid: String? {
        guard let first = photosIdentifier.split(separator: "/").first, UUID(uuidString: String(first)) != nil else { return nil }
        return String(first)
    }
}
```

- [ ] **Step 5: Run**

Run: `swift test --filter AssetRecordTests`
Expected: `Test run with 4 tests in 1 suite passed`.

- [ ] **Step 6: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): AssetFacts and AssetRecord with the full pre-deletion field set

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Pure classification rules and the scan summary

Rules from spec v2, in order: not user library → `notUserLibrary`; no `.video` resource → `noOriginalVideoResource`; `hasAdjustments` → `hasAdjustments`; high frame rate → `highFrameRate`; cinematic → `cinematic`; hidden → `hidden`; Live Photo bit → `livePhotoComponent`; size unknown on macOS 27 → `sizeUnknown`. On macOS 26 sizes are estimated, never excluded, so the classifier takes a flag saying whether exact sizes are available on this system.

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/AssetClassifier.swift`
- Create: `engine/Tests/ArchiveCoreTests/AssetClassifierTests.swift`

- [ ] **Step 1: Write the failing tests**

`engine/Tests/ArchiveCoreTests/AssetClassifierTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

private func facts(sourceType: Int = 1, size: Int? = 1_000, hasVideoResource: Bool = true,
                   adjustments: Bool = false, hidden: Bool = false, subtypes: UInt = 0) -> AssetFacts {
    AssetFacts(
        photosIdentifier: "AAAA-1/L0/001", sourceTypeRawValue: sourceType, hasOriginalVideoResource: hasVideoResource,
        originalFilename: "IMG_0001.MOV", exactSizeBytes: size,
        creationDate: Date(timeIntervalSince1970: 0), modificationDate: Date(timeIntervalSince1970: 5),
        latitude: nil, longitude: nil, altitude: nil, durationSeconds: 1, pixelWidth: 10, pixelHeight: 10,
        isFavorite: false, isHidden: hidden, hasAdjustments: adjustments, mediaSubtypesRaw: subtypes, albumTitles: ["A"]
    )
}

@Suite struct AssetClassifierTests {
    @Test func userLibraryVideoWithSizeIsIncludedWithEveryField() {
        let expected = AssetRecord(
            photosIdentifier: "AAAA-1/L0/001", originalFilename: "IMG_0001.MOV", size: .exact(bytes: 1_000),
            creationDate: Date(timeIntervalSince1970: 0), modificationDate: Date(timeIntervalSince1970: 5),
            latitude: nil, longitude: nil, altitude: nil, durationSeconds: 1, pixelWidth: 10, pixelHeight: 10,
            isFavorite: false, isHidden: false, hasAdjustments: false, mediaSubtypesRaw: 0, albumTitles: ["A"],
            locality: .unknown, probedAt: nil)
        #expect(AssetClassifier.classify(facts(), exactSizesAvailable: true) == .included(expected))
    }

    @Test func cloudSharedIsExcluded() {
        #expect(AssetClassifier.classify(facts(sourceType: 2), exactSizesAvailable: true) == .excluded(.notUserLibrary))
    }

    @Test func iTunesSyncedAndMixedSourceTypesAreExcluded() {
        #expect(AssetClassifier.classify(facts(sourceType: 4), exactSizesAvailable: true) == .excluded(.notUserLibrary))
        #expect(AssetClassifier.classify(facts(sourceType: 3), exactSizesAvailable: true) == .excluded(.notUserLibrary))
    }

    @Test func missingVideoResourceIsExcludedAndWinsOverMissingSize() {
        #expect(AssetClassifier.classify(facts(size: nil, hasVideoResource: false), exactSizesAvailable: true) == .excluded(.noOriginalVideoResource))
    }

    @Test func editedVideoIsExcluded() {
        #expect(AssetClassifier.classify(facts(adjustments: true), exactSizesAvailable: true) == .excluded(.hasAdjustments))
    }

    @Test func highFrameRateAndCinematicAreExcluded() {
        #expect(AssetClassifier.classify(facts(subtypes: AssetFacts.subtypeVideoHighFrameRate), exactSizesAvailable: true) == .excluded(.highFrameRate))
        #expect(AssetClassifier.classify(facts(subtypes: AssetFacts.subtypeVideoCinematic), exactSizesAvailable: true) == .excluded(.cinematic))
    }

    @Test func hiddenIsExcluded() {
        #expect(AssetClassifier.classify(facts(hidden: true), exactSizesAvailable: true) == .excluded(.hidden))
    }

    @Test func livePhotoBitIsExcludedEvenIfAVideoFetchReturnedIt() {
        #expect(AssetClassifier.classify(facts(subtypes: AssetFacts.subtypePhotoLive), exactSizesAvailable: true) == .excluded(.livePhotoComponent))
    }

    @Test func missingSizeIsExcludedOnlyWhereExactSizesExist() {
        #expect(AssetClassifier.classify(facts(size: nil), exactSizesAvailable: true) == .excluded(.sizeUnknown))
        guard case .included(let r) = AssetClassifier.classify(facts(size: nil), exactSizesAvailable: false) else {
            Issue.record("expected an estimated inclusion on macOS 26"); return
        }
        #expect(r.size == .estimated(bytes: 1_048_576))
    }

    @Test func precedenceIsSourceThenResourceThenEdits() {
        #expect(AssetClassifier.classify(facts(sourceType: 2, hasVideoResource: false, adjustments: true), exactSizesAvailable: true) == .excluded(.notUserLibrary))
        #expect(AssetClassifier.classify(facts(hasVideoResource: false, adjustments: true), exactSizesAvailable: true) == .excluded(.noOriginalVideoResource))
    }

    @Test func summaryCountsEveryOutcome() {
        var summary = ScanSummary()
        summary.count(AssetClassifier.classify(facts(), exactSizesAvailable: true))
        summary.count(AssetClassifier.classify(facts(sourceType: 2), exactSizesAvailable: true))
        summary.count(AssetClassifier.classify(facts(sourceType: 2), exactSizesAvailable: true))
        summary.count(AssetClassifier.classify(facts(adjustments: true), exactSizesAvailable: true))
        #expect(summary.included == 1)
        #expect(summary.excluded[.notUserLibrary] == 2)
        #expect(summary.excluded[.hasAdjustments] == 1)
        #expect(summary.excluded[.hidden] == nil)
        #expect(summary.total == 4)
    }

    @Test func summaryEncodesReasonsAsObjectKeys() throws {
        var s = ScanSummary()
        s.count(.excluded(.sizeUnknown))
        let enc = JSONEncoder(); enc.outputFormatting = [.sortedKeys]
        #expect(String(data: try enc.encode(s), encoding: .utf8) == #"{"excluded":{"sizeUnknown":1},"included":0}"#)
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `swift test --filter AssetClassifierTests`
Expected: compile error, `cannot find 'AssetClassifier' in scope`.

- [ ] **Step 3: Implement**

`engine/Sources/ArchiveCore/Library/AssetClassifier.swift`:

```swift
import Foundation

/// Why an asset is left alone. Surfaced to the user as counts, one row per case (invariant 6).
public enum ExclusionReason: String, Codable, Sendable, CaseIterable {
    case notUserLibrary            // shared album, iTunes-synced, or any mix: invariant 7
    case noOriginalVideoResource   // no `.video` resource; a rendered `.fullSizeVideo` never substitutes
    case hasAdjustments            // archiving only the original would destroy the edit
    case highFrameRate             // slo-mo range is an adjustment
    case cinematic                 // focus edits are adjustments
    case hidden                    // the family hid it; leave it alone
    case livePhotoComponent        // never archive a paired video and delete the still
    case sizeUnknown               // macOS 27 only: Photos does not know the original's size
}

extension ExclusionReason: CodingKeyRepresentable {}

public enum Classification: Equatable, Sendable {
    case included(AssetRecord)
    case excluded(ExclusionReason)
}

/// The rules. Pure, ordered, and the only place they live.
public enum AssetClassifier {
    /// PHAssetSourceType.typeUserLibrary raw value. Exactly this value, no other bits.
    public static let userLibrarySourceType = 1

    /// `exactSizesAvailable` is true on macOS 27, where `dataSize` exists.
    public static func classify(_ f: AssetFacts, exactSizesAvailable: Bool) -> Classification {
        guard f.sourceTypeRawValue == userLibrarySourceType else { return .excluded(.notUserLibrary) }
        guard f.hasOriginalVideoResource else { return .excluded(.noOriginalVideoResource) }
        guard !f.hasAdjustments else { return .excluded(.hasAdjustments) }
        guard f.mediaSubtypesRaw & AssetFacts.subtypeVideoHighFrameRate == 0 else { return .excluded(.highFrameRate) }
        guard f.mediaSubtypesRaw & AssetFacts.subtypeVideoCinematic == 0 else { return .excluded(.cinematic) }
        guard !f.isHidden else { return .excluded(.hidden) }
        guard f.mediaSubtypesRaw & AssetFacts.subtypePhotoLive == 0 else { return .excluded(.livePhotoComponent) }
        if exactSizesAvailable && f.exactSizeBytes == nil { return .excluded(.sizeUnknown) }
        let size = SizeInfo.make(exactBytes: exactSizesAvailable ? f.exactSizeBytes : nil,
                                 durationSeconds: f.durationSeconds, pixelWidth: f.pixelWidth, pixelHeight: f.pixelHeight)
        return .included(AssetRecord(
            photosIdentifier: f.photosIdentifier, originalFilename: f.originalFilename, size: size,
            creationDate: f.creationDate, modificationDate: f.modificationDate,
            latitude: f.latitude, longitude: f.longitude, altitude: f.altitude,
            durationSeconds: f.durationSeconds, pixelWidth: f.pixelWidth, pixelHeight: f.pixelHeight,
            isFavorite: f.isFavorite, isHidden: f.isHidden, hasAdjustments: f.hasAdjustments,
            mediaSubtypesRaw: f.mediaSubtypesRaw, albumTitles: f.albumTitles,
            locality: .unknown, probedAt: nil))
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

- [ ] **Step 4: Run**

Run: `swift test --filter AssetClassifierTests`
Expected: `Test run with 12 tests in 1 suite passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): AssetClassifier with the full exclusion set and precedence; ScanSummary

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: PhotoKit scanner adapter

The PhotoKit reads are exercised by the harness; the two pure rules (which resource is the original, which identifiers to try) are tested. `dataSize` is behind `#available(macOS 27, *)`; the Swift overlay exposes it as `Int?` and `resource.dataSize` compiles.

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/PhotoKitLibraryScanner.swift`
- Create: `engine/Tests/ArchiveCoreTests/ScannerRulesTests.swift`

- [ ] **Step 1: Write the failing tests**

`engine/Tests/ArchiveCoreTests/ScannerRulesTests.swift`:

```swift
import Foundation
import Photos
import Testing
@testable import ArchiveCore

@Suite struct ScannerRulesTests {
    @Test func onlyTheUnadjustedVideoResourceCounts() {
        #expect(PhotoKitLibraryScanner.originalVideoResourceIndex(in: [.fullSizeVideo, .video]) == 1)
        #expect(PhotoKitLibraryScanner.originalVideoResourceIndex(in: [.video, .fullSizeVideo]) == 0)
    }

    @Test func renderedOnlyVideoIsNotAnOriginal() {
        #expect(PhotoKitLibraryScanner.originalVideoResourceIndex(in: [.photo, .fullSizeVideo]) == nil)
    }

    @Test func noVideoResourceGivesNil() {
        #expect(PhotoKitLibraryScanner.originalVideoResourceIndex(in: [.photo, .adjustmentData]) == nil)
    }

    @Test func bareUUIDTriesTheMacOSFormFirst() {
        #expect(PhotoKitLibraryScanner.candidateIdentifiers(uuid: "ABC") == ["ABC/L0/001", "ABC"])
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `swift test --filter ScannerRulesTests`
Expected: compile error, `cannot find 'PhotoKitLibraryScanner' in scope`.

- [ ] **Step 3: Implement**

`engine/Sources/ArchiveCore/Library/PhotoKitLibraryScanner.swift`:

```swift
import Foundation
import Photos

/// One PhotoKit sweep of all videos, mapped through AssetClassifier. Runs off the main
/// actor: resource and album lookups are an XPC call per asset and the scan is measured,
/// not assumed fast.
public final class PhotoKitLibraryScanner {
    public struct Result: Sendable {
        public var records: [AssetRecord]
        public var summary: ScanSummary
        public var sweepCount: Int
        public var elapsedSeconds: Double
    }

    public init() {}

    /// True where `PHAssetResource.dataSize` exists.
    public static var exactSizesAvailable: Bool {
        if #available(macOS 27, *) { return true } else { return false }
    }

    public func scan() async -> Result {
        await Task.detached(priority: .userInitiated) { Self.scanNow() }.value
    }

    private static func scanNow() -> Result {
        let start = Date()
        let options = PHFetchOptions()
        options.includeHiddenAssets = true
        let fetch = PHAsset.fetchAssets(with: .video, options: options)
        var records: [AssetRecord] = []
        var summary = ScanSummary()
        let exact = exactSizesAvailable
        fetch.enumerateObjects { asset, _, _ in
            let classification = AssetClassifier.classify(facts(for: asset), exactSizesAvailable: exact)
            summary.count(classification)
            if case .included(let record) = classification { records.append(record) }
        }
        return Result(records: records, summary: summary, sweepCount: fetch.count,
                      elapsedSeconds: Date().timeIntervalSince(start))
    }

    /// Index of the resource that is the unedited original: a `.video` resource only.
    /// A `.fullSizeVideo` is a rendition and never substitutes (red team finding 4).
    public static func originalVideoResourceIndex(in types: [PHAssetResourceType]) -> Int? {
        types.firstIndex(of: .video)
    }

    public static func originalVideoResource(for asset: PHAsset) -> PHAssetResource? {
        let resources = PHAssetResource.assetResources(for: asset)
        return originalVideoResourceIndex(in: resources.map(\.type)).map { resources[$0] }
    }

    /// Local identifiers tried in order for a bare UUID (spike finding 5).
    public static func candidateIdentifiers(uuid: String) -> [String] {
        ["\(uuid)/L0/001", uuid]
    }

    public static func fetchAsset(uuid: String) -> PHAsset? {
        for id in candidateIdentifiers(uuid: uuid) {
            if let a = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject { return a }
        }
        return nil
    }

    static func albumTitles(for asset: PHAsset) -> [String] {
        let albums = PHAssetCollection.fetchAssetCollectionsContaining(asset, with: .album, options: nil)
        var titles: [String] = []
        albums.enumerateObjects { collection, _, _ in
            if let t = collection.localizedTitle { titles.append(t) }
        }
        return titles.sorted()
    }

    public static func facts(for asset: PHAsset) -> AssetFacts {
        let resource = originalVideoResource(for: asset)
        var exactSize: Int? = nil
        if #available(macOS 27, *) { exactSize = resource?.dataSize }
        return AssetFacts(
            photosIdentifier: asset.localIdentifier,
            sourceTypeRawValue: Int(asset.sourceType.rawValue),
            hasOriginalVideoResource: resource != nil,
            originalFilename: resource?.originalFilename ?? "",
            exactSizeBytes: exactSize,
            creationDate: asset.creationDate,
            modificationDate: asset.modificationDate,
            latitude: asset.location?.coordinate.latitude,
            longitude: asset.location?.coordinate.longitude,
            altitude: asset.location?.altitude,
            durationSeconds: asset.duration,
            pixelWidth: asset.pixelWidth,
            pixelHeight: asset.pixelHeight,
            isFavorite: asset.isFavorite,
            isHidden: asset.isHidden,
            hasAdjustments: asset.hasAdjustments,
            mediaSubtypesRaw: asset.mediaSubtypes.rawValue,
            albumTitles: albumTitles(for: asset)
        )
    }
}
```

- [ ] **Step 4: Run**

Run: `swift test --filter ScannerRulesTests`
Expected: `Test run with 4 tests in 1 suite passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): PhotoKitLibraryScanner off the main actor, original-only resource rule, album titles

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Locality probe with timeout and early cancel

A network-disallowed `requestData`. The first data chunk proves the bytes are local and cancels the request so a 4 GB local file is not streamed through XPC; error 3164 means cloud-only; a 60 s timeout or any other error is `.unknown` with its cause. The mapping is pure and tested.

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/LocalityProbe.swift`
- Create: `engine/Tests/ArchiveCoreTests/LocalityProbeTests.swift`

- [ ] **Step 1: Write the failing tests**

`engine/Tests/ArchiveCoreTests/LocalityProbeTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

@Suite struct LocalityProbeTests {
    @Test func firstChunkMeansLocalWhateverTheCompletionSays() {
        let cancelled = NSError(domain: "PHPhotosErrorDomain", code: 3072)
        #expect(LocalityProbe.locality(sawData: true, completionError: cancelled) == .local)
        #expect(LocalityProbe.locality(sawData: true, completionError: nil) == .local)
    }

    @Test func networkAccessRequiredMeansCloudOnly() {
        let e = NSError(domain: "PHPhotosErrorDomain", code: 3164)
        #expect(LocalityProbe.locality(sawData: false, completionError: e) == .cloudOnly)
    }

    @Test func otherErrorsAndTimeoutsMeanUnknown() {
        #expect(LocalityProbe.locality(sawData: false, completionError: NSError(domain: "PHPhotosErrorDomain", code: 3303)) == .unknown)
        #expect(LocalityProbe.locality(sawData: false, completionError: EngineError.timedOut(seconds: 60)) == .unknown)
    }

    @Test func completionWithoutDataAndWithoutErrorIsLocalEmptyFile() {
        #expect(LocalityProbe.locality(sawData: false, completionError: nil) == .local)
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `swift test --filter LocalityProbeTests`
Expected: compile error, `cannot find 'LocalityProbe' in scope`.

- [ ] **Step 3: Implement**

`engine/Sources/ArchiveCore/Library/LocalityProbe.swift`:

```swift
import Foundation
import Photos
import Synchronization

/// Decides whether an original's bytes are on this Mac by asking PhotoKit for them
/// with network access disallowed. The first chunk proves "local" and cancels the
/// request; 3164 proves "cloud-only"; anything else, including a 60 s silence, is unknown.
/// Probe only the assets you are about to act on, never the whole library.
public final class LocalityProbe {
    public struct Outcome: Sendable, Equatable {
        public var locality: Locality
        public var errorCode: Int?
        public var elapsedSeconds: Double
    }

    private let manager = PHAssetResourceManager.default()
    public let timeoutSeconds: Int

    public init(timeoutSeconds: Int = 60) { self.timeoutSeconds = timeoutSeconds }

    public static func locality(sawData: Bool, completionError: Error?) -> Locality {
        if sawData { return .local }
        guard let error = completionError else { return .local }
        return EngineError.from(error).isNetworkAccessRequired ? .cloudOnly : .unknown
    }

    public func probe(_ resource: PHAssetResource) async -> Outcome {
        let start = Date()
        let options = PHAssetResourceRequestOptions()
        options.isNetworkAccessAllowed = false
        let sawData = Mutex(false)
        let requestID = Mutex<PHAssetResourceDataRequestID?>(nil)

        let result: ProbeResult = await withCheckedContinuation { continuation in
            let once = OneShot(continuation)
            let id = manager.requestData(for: resource, options: options, dataReceivedHandler: { _ in
                sawData.withLock { $0 = true }
                // Bytes arrived with network disallowed: the original is local. Stop reading it.
                if let id = requestID.withLock({ $0 }) { self.manager.cancelDataRequest(id) }
                once.resume(ProbeResult(errorCode: nil, domain: nil, timedOut: false))
            }) { err in
                let ns = err as NSError?
                once.resume(ProbeResult(errorCode: ns?.code, domain: ns?.domain, timedOut: false))
            }
            requestID.withLock { $0 = id }
            Task {
                try? await Task.sleep(for: .seconds(self.timeoutSeconds))
                self.manager.cancelDataRequest(id)
                once.resume(ProbeResult(errorCode: nil, domain: nil, timedOut: true))
            }
        }
        let error: Error? = result.timedOut
            ? EngineError.timedOut(seconds: timeoutSeconds)
            : result.errorCode.map { NSError(domain: result.domain ?? "", code: $0) }
        let locality = Self.locality(sawData: sawData.withLock { $0 }, completionError: error)
        return Outcome(locality: locality, errorCode: result.errorCode, elapsedSeconds: Date().timeIntervalSince(start))
    }

    /// Convenience for a record: fetches the asset and its original resource, then probes.
    public func probe(uuid: String) async -> Outcome {
        guard let asset = PhotoKitLibraryScanner.fetchAsset(uuid: uuid),
              let resource = PhotoKitLibraryScanner.originalVideoResource(for: asset) else {
            return Outcome(locality: .unknown, errorCode: nil, elapsedSeconds: 0)
        }
        return await probe(resource)
    }
}

/// `Error` is not `Sendable`, so the continuation resumes with plain values.
private struct ProbeResult: Sendable {
    var errorCode: Int?
    var domain: String?
    var timedOut: Bool
}
```

- [ ] **Step 4: Run**

Run: `swift test --filter LocalityProbeTests`
Expected: `Test run with 4 tests in 1 suite passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): LocalityProbe with early cancel on first chunk and a 60 s timeout

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Library environment

Computed before any scan or later any derivation: authorization (`.limited` and `.denied` are refusals inside the engine), the total video count, three canary identifiers, and a Shared Library detection attempt. PhotoKit has no public flag for Shared Library membership; the probe records the evidence macOS exposes (smart album subtypes present, any source-type bit beyond 1, 2, 4) and reports `nil` for "cannot tell". The app treats `nil` as "warn before delete" (decision D2).

**Files:**
- Create: `engine/Sources/ArchiveCore/Library/LibraryEnvironment.swift`
- Create: `engine/Tests/ArchiveCoreTests/LibraryEnvironmentTests.swift`

- [ ] **Step 1: Write the failing tests**

`engine/Tests/ArchiveCoreTests/LibraryEnvironmentTests.swift`:

```swift
import Foundation
import Testing
@testable import ArchiveCore

@Suite struct LibraryEnvironmentTests {
    @Test func onlyFullAuthorizationIsUsable() {
        #expect(EnvironmentReport.Authorization.from(rawStatus: 3) == .authorized)
        #expect(EnvironmentReport.Authorization.from(rawStatus: 4) == .limited)
        #expect(EnvironmentReport.Authorization.from(rawStatus: 2) == .denied)
        #expect(EnvironmentReport.Authorization.from(rawStatus: 0) == .notDetermined)
        #expect(EnvironmentReport.Authorization.authorized.isUsable)
        #expect(!EnvironmentReport.Authorization.limited.isUsable)
    }

    @Test func sharedLibraryEvidenceIsNilWhenNothingIsExposed() {
        #expect(EnvironmentReport.sharedLibraryDetected(unknownSourceBitsSeen: false, sharedLibrarySmartAlbumSeen: false) == nil)
        #expect(EnvironmentReport.sharedLibraryDetected(unknownSourceBitsSeen: true, sharedLibrarySmartAlbumSeen: false) == true)
        #expect(EnvironmentReport.sharedLibraryDetected(unknownSourceBitsSeen: false, sharedLibrarySmartAlbumSeen: true) == true)
    }

    @Test func canariesAreTheFirstThreeIdentifiers() {
        #expect(EnvironmentReport.canaries(from: ["a", "b", "c", "d"]) == ["a", "b", "c"])
        #expect(EnvironmentReport.canaries(from: ["a"]) == ["a"])
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `swift test --filter LibraryEnvironmentTests`
Expected: compile error, `cannot find 'EnvironmentReport' in scope`.

- [ ] **Step 3: Implement**

`engine/Sources/ArchiveCore/Library/LibraryEnvironment.swift`:

```swift
import Foundation
import Photos

/// What the engine knows about the library before acting on it. Pure value; the
/// PhotoKit reads live in `LibraryEnvironment.report()`.
public struct EnvironmentReport: Codable, Equatable, Sendable {
    public enum Authorization: String, Codable, Sendable {
        case authorized, limited, denied, notDetermined

        /// Only full read-write access is usable. Limited access hides assets and would make
        /// every guard in the engine lie (red team finding 6).
        public var isUsable: Bool { self == .authorized }

        public static func from(rawStatus: Int) -> Authorization {
            switch rawStatus {
            case 3: return .authorized      // PHAuthorizationStatus.authorized
            case 4: return .limited         // .limited
            case 2: return .denied          // .denied
            default: return .notDetermined  // .notDetermined (0) and .restricted (1)
            }
        }
    }

    public var authorization: Authorization
    public var exactSizesAvailable: Bool
    public var videoCount: Int
    public var hiddenVideoCount: Int
    public var canaries: [String]
    public var sourceTypeCounts: [String: Int]     // raw source type -> count, evidence for the Shared Library question
    public var smartAlbumSubtypes: [Int]           // raw subtypes present, evidence
    public var sharedLibraryDetected: Bool?        // nil means "cannot tell"; the app treats nil as warn
    public var macOSVersion: String

    public static func sharedLibraryDetected(unknownSourceBitsSeen: Bool, sharedLibrarySmartAlbumSeen: Bool) -> Bool? {
        if unknownSourceBitsSeen || sharedLibrarySmartAlbumSeen { return true }
        return nil
    }

    public static func canaries(from identifiers: [String]) -> [String] {
        Array(identifiers.prefix(3))
    }
}

public enum LibraryEnvironment {
    public static func requestAuthorization() async -> EnvironmentReport.Authorization {
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        return EnvironmentReport.Authorization.from(rawStatus: status.rawValue)
    }

    /// Reads the environment. Cheap: one video fetch, one hidden fetch, one smart-album fetch.
    public static func report() -> EnvironmentReport {
        let auth = EnvironmentReport.Authorization.from(rawStatus: PHPhotoLibrary.authorizationStatus(for: .readWrite).rawValue)
        let pv = ProcessInfo.processInfo.operatingSystemVersion

        let all = PHFetchOptions(); all.includeHiddenAssets = true
        let videos = PHAsset.fetchAssets(with: .video, options: all)
        let visible = PHAsset.fetchAssets(with: .video, options: nil)

        var sourceCounts: [String: Int] = [:]
        var identifiers: [String] = []
        videos.enumerateObjects { asset, index, _ in
            sourceCounts["\(asset.sourceType.rawValue)", default: 0] += 1
            if index < 3 { identifiers.append(asset.localIdentifier) }
        }
        let unknownBits = sourceCounts.keys.contains { !["1", "2", "4"].contains($0) }

        var subtypes: [Int] = []
        var sharedLibraryAlbumSeen = false
        let smart = PHAssetCollection.fetchAssetCollections(with: .smartAlbum, subtype: .any, options: nil)
        smart.enumerateObjects { collection, _, _ in
            subtypes.append(collection.assetCollectionSubtype.rawValue)
            // Evidence only: a smart album whose localized title mentions a shared library.
            if let t = collection.localizedTitle?.lowercased(), t.contains("shared library") { sharedLibraryAlbumSeen = true }
        }

        return EnvironmentReport(
            authorization: auth,
            exactSizesAvailable: PhotoKitLibraryScanner.exactSizesAvailable,
            videoCount: videos.count,
            hiddenVideoCount: videos.count - visible.count,
            canaries: EnvironmentReport.canaries(from: identifiers),
            sourceTypeCounts: sourceCounts,
            smartAlbumSubtypes: subtypes.sorted(),
            sharedLibraryDetected: EnvironmentReport.sharedLibraryDetected(unknownSourceBitsSeen: unknownBits, sharedLibrarySmartAlbumSeen: sharedLibraryAlbumSeen),
            macOSVersion: "\(pv.majorVersion).\(pv.minorVersion).\(pv.patchVersion)")
    }
}
```

- [ ] **Step 4: Run all tests**

Run: `swift test`
Expected: `Test run with 36 tests in 7 suites passed` (4 error, 5 size, 4 record, 12 classifier, 4 scanner rules, 4 probe, 3 environment).

- [ ] **Step 5: Commit**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine
git commit -m "feat(engine): LibraryEnvironment with authorization guard, canaries, and Shared Library evidence

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Harness with `scan` and `environment`

The harness must run as a sandboxed app bundle launched by `open`, or macOS auto-denies Photos access (spike finding 6). It can only write inside a folder the user picks, persisted as a security-scoped bookmark resolved without mounting. Bundle id `dev.videoattic.harness`, never submitted anywhere.

**Files:**
- Replace: `engine/Sources/ArchiveHarness/main.swift`
- Create: `engine/Sources/ArchiveHarness/OutputFolder.swift`
- Create: `engine/Sources/ArchiveHarness/JSONLWriter.swift`
- Create: `engine/Sources/ArchiveHarness/Commands/ScanCommand.swift`
- Create: `engine/Sources/ArchiveHarness/Commands/EnvironmentCommand.swift`
- Create: `engine/Harness/Info.plist`
- Create: `engine/Harness/ArchiveHarness.entitlements`
- Create: `engine/Makefile`

- [ ] **Step 1: Output folder bookmark**

`engine/Sources/ArchiveHarness/OutputFolder.swift`:

```swift
import AppKit
import Foundation

/// The one folder the sandboxed harness may write to. Chosen once in an open panel,
/// persisted as an app-scoped security-scoped bookmark, resolved without mounting.
/// Access is started once here and stopped once at exit (spec: VolumeAccess).
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
        try handle.write(contentsOf: data)
        try handle.write(contentsOf: Data("\n".utf8))
    }

    func close() { try? handle.close() }
}

func runStamp() -> String {
    ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "")
}
```

- [ ] **Step 3: Scan command**

`engine/Sources/ArchiveHarness/Commands/ScanCommand.swift`:

```swift
import ArchiveCore
import Foundation

/// `scan [--probe N]`: sweep the library, write one AssetRecord per line plus a summary line.
/// With --probe N the first N included records are locality-probed so the probe path is
/// exercised on real assets; cheap for cloud-only, one chunk for local ones.
struct ScanCommand {
    var probeCount = 0

    struct SummaryLine: Encodable {
        var kind = "summary"
        var sweepCount: Int
        var included: Int
        var excluded: [String: Int]
        var probed: [String: Int]
        var exactSizesAvailable: Bool
        var elapsedSeconds: Double
    }

    func run(output: URL) async throws {
        let result = await PhotoKitLibraryScanner().scan()
        var records = result.records

        var probed: [String: Int] = [:]
        if probeCount > 0 {
            let probe = LocalityProbe()
            for i in records.indices.prefix(probeCount) {
                guard let uuid = records[i].uuid else { continue }
                let outcome = await probe.probe(uuid: uuid)
                records[i].locality = outcome.locality
                records[i].probedAt = Date()
                probed[outcome.locality.rawValue, default: 0] += 1
                print("probe \(uuid.prefix(8)) \(records[i].originalFilename) \(outcome.locality.rawValue) \(String(format: "%.1fs", outcome.elapsedSeconds)) err=\(outcome.errorCode.map(String.init) ?? "-")")
            }
        }

        let writer = try JSONLWriter(url: output.appendingPathComponent("scan-\(runStamp()).jsonl"))
        defer { writer.close() }
        for record in records { try writer.write(record) }
        let excluded = Dictionary(uniqueKeysWithValues: result.summary.excluded.map { ($0.key.rawValue, $0.value) })
        let summary = SummaryLine(sweepCount: result.sweepCount, included: result.summary.included, excluded: excluded,
                                  probed: probed, exactSizesAvailable: PhotoKitLibraryScanner.exactSizesAvailable,
                                  elapsedSeconds: result.elapsedSeconds)
        try writer.write(summary)
        print("scan: sweep=\(result.sweepCount) included=\(result.summary.included) excluded=\(excluded) probed=\(probed) exact_sizes=\(PhotoKitLibraryScanner.exactSizesAvailable) in \(String(format: "%.1f", result.elapsedSeconds))s")
        print("wrote \(writer.url.path)")
    }
}
```

- [ ] **Step 4: Environment command**

`engine/Sources/ArchiveHarness/Commands/EnvironmentCommand.swift`:

```swift
import ArchiveCore
import Foundation

/// `environment`: write one EnvironmentReport line. Read-only and cheap.
struct EnvironmentCommand {
    func run(output: URL) throws {
        let report = LibraryEnvironment.report()
        let writer = try JSONLWriter(url: output.appendingPathComponent("environment-\(runStamp()).jsonl"))
        defer { writer.close() }
        try writer.write(report)
        print("environment: auth=\(report.authorization.rawValue) videos=\(report.videoCount) hidden=\(report.hiddenVideoCount) sources=\(report.sourceTypeCounts) sharedLibrary=\(report.sharedLibraryDetected.map { "\($0)" } ?? "nil") smartAlbums=\(report.smartAlbumSubtypes) macOS=\(report.macOSVersion) exact_sizes=\(report.exactSizesAvailable)")
        print("wrote \(writer.url.path)")
    }
}
```

- [ ] **Step 5: Entry point**

Replace `engine/Sources/ArchiveHarness/main.swift`:

```swift
import AppKit
import ArchiveCore
import Foundation

/// Headless harness for ArchiveCore. Runs inside a sandboxed bundle launched by `open`
/// so the Photos permission attaches to the bundle. Output goes to a user-chosen folder;
/// stdout is mirrored into <output>/latest.log because `open` has no terminal.
///
///   ArchiveHarness.app --command scan [--probe N] [--pick-output]
///   ArchiveHarness.app --command environment

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

    let auth = await LibraryEnvironment.requestAuthorization()
    print("photos authorization: \(auth.rawValue)")
    guard auth.isUsable else { print("refusing: authorization must be full read-write"); return 3 }
    print("ArchiveCore \(ArchiveCore.version), sandboxed=\(ProcessInfo.processInfo.environment["APP_SANDBOX_CONTAINER_ID"] != nil)")

    do {
        switch args.command {
        case "scan": try await ScanCommand(probeCount: args.probe).run(output: output)
        case "environment": try EnvironmentCommand().run(output: output)
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

- [ ] **Step 6: Bundle metadata**

`engine/Harness/Info.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>dev.videoattic.harness</string>
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
    <string>26.0</string>
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

- [ ] **Step 7: Makefile**

`engine/Makefile`:

```makefile
# Build the ArchiveCore package, wrap ArchiveHarness into a signed sandboxed bundle, run it.
#
#   make                    swift build (release) + bundle + sign with the Apple Development identity
#   make test               swift test
#   make scan ARGS="--probe 10"
#   make environment
#   make reset-tcc          forget the Photos permission for the harness bundle

APP       := build/ArchiveHarness.app
BIN       := $(APP)/Contents/MacOS/ArchiveHarness
BUILT     := .build/release/ArchiveHarness
IDENTITY  ?= $(shell security find-identity -v -p codesigning 2>/dev/null | grep "Apple Development" | head -1 | awk '{print $$2}')
BUNDLE_ID := dev.videoattic.harness
SOURCES   := $(shell find Sources -name '*.swift') Package.swift

.PHONY: all test scan environment reset-tcc clean check-idle

all: $(BIN)

$(BUILT): $(SOURCES)
	swift build -c release --product ArchiveHarness

$(BIN): $(BUILT) Harness/Info.plist Harness/ArchiveHarness.entitlements
	@test -n "$(IDENTITY)" || (echo "no Apple Development identity; ad hoc signing breaks TCC attribution" && exit 1)
	mkdir -p $(APP)/Contents/MacOS
	cp Harness/Info.plist $(APP)/Contents/Info.plist
	cp $(BUILT) $(BIN)
	codesign --force --sign $(IDENTITY) --entitlements Harness/ArchiveHarness.entitlements --timestamp=none $(APP)
	@codesign -d --entitlements - $(APP) 2>&1 | grep -q app-sandbox && echo "signed with sandbox entitlements"

test:
	swift test

check-idle:
	@if pgrep -x ArchiveHarness >/dev/null; then echo "refusing: ArchiveHarness is already running"; exit 1; fi
	@if pgrep -f "iphoto archive" >/dev/null; then echo "refusing: 'iphoto archive' is running"; exit 1; fi

scan: $(BIN) check-idle
	open -n -W -a $(CURDIR)/$(APP) --args --command scan $(ARGS)
	@tail -n 25 scratch/latest.log 2>/dev/null || echo "no scratch/latest.log: the folder picker was cancelled, rerun with ARGS=--pick-output"

environment: $(BIN) check-idle
	open -n -W -a $(CURDIR)/$(APP) --args --command environment $(ARGS)
	@tail -n 5 scratch/latest.log 2>/dev/null || echo "no scratch/latest.log: the folder picker was cancelled, rerun with ARGS=--pick-output"

reset-tcc:
	tccutil reset Photos $(BUNDLE_ID)

clean:
	rm -rf build .build
```

- [ ] **Step 8: Build the bundle**

Run: `make`
Expected: `swift build` succeeds, then `signed with sandbox entitlements`.

- [ ] **Step 9: First run, picking the output folder, then the environment**

```bash
mkdir -p /Users/camoiloc/IdeaProjects/iphoto/engine/scratch
make environment ARGS="--pick-output"
```

A folder picker appears: choose `engine/scratch`. Then the Photos permission prompt for "ArchiveHarness": allow. Both dialogs can open behind other windows because the app is an accessory; check the Dock and Mission Control. Then:

```bash
tail -n 5 scratch/latest.log
```

Expected: `photos authorization: authorized`, then an `environment:` line with `videos=` in the thousands, `hidden=` a small number, `sources=` a dictionary whose keys are among "1", "2", "4", `sharedLibrary=nil` unless evidence was found, and `exact_sizes=true` on this Mac (macOS 27).

If the log does not exist, the picker was cancelled: rerun with `--pick-output`. If it ends at `photos authorization: denied` or `notDetermined`, run `make reset-tcc`, rerun, and allow the prompt; if the prompt still does not appear, enable ArchiveHarness under System Settings > Privacy & Security > Photos. `open -W` returns 0 regardless of the harness's exit code; the log is the only signal.

- [ ] **Step 10: Hidden-asset visibility measurement**

In Photos, hide one video (select, Image > Hide). Rerun `make environment` and compare `videos=` and `hidden=` with the previous run: `hidden` should rise by one if third-party clients receive hidden assets with the locked Hidden album, which the spec assumes and nobody has measured. Unhide it afterwards. Record the observation for the journal in Task 10 either way.

- [ ] **Step 11: Scan with probes**

```bash
make scan ARGS="--probe 10"
tail -n 15 scratch/latest.log
```

Expected: ten `probe` lines with `local` or `cloudOnly` and elapsed times well under a second for cloud-only, then a `scan:` line with `sweep=` equal to the environment's `videos=`, `included=` in the thousands, `excluded=` listing `notUserLibrary` (shared albums, dozens on this library) and possibly `hasAdjustments`, `hidden`, `highFrameRate`, `cinematic`, and an elapsed time that is now a measurement, not a claim. Any `unknown` probe result is worth a journal note and is not a failure.

- [ ] **Step 12: Check the JSONL**

```bash
f=$(ls -t scratch/scan-*.jsonl | head -1); wc -l "$f"; tail -n 1 "$f"; head -n 1 "$f"
```
Expected: line count equals `included + 1`; the last line is the summary with `excluded` as a JSON object keyed by reason; the first line is an `AssetRecord` with `size` as `{"bytes":...,"kind":"exact"}` and `photosIdentifier` ending in `/L0/001`.

Do not commit yet; Task 10 ships the slice with the ledger in the same commit.

---

### Task 10: Ship the slice (ledger in the same commit)

**Files:**
- Modify: `docs/COVERAGE.md`
- Modify: `docs/STATE.md`
- Modify: `CHANGELOG.md`
- Create: `docs/journal/2026-09-06-engine-slice-1.md` (use the actual run date if later)

- [ ] **Step 1: Flip the coverage rows**

In `docs/COVERAGE.md`, Engine table, replace these rows:

```
| Library scan via PhotoKit sweep | shipped (slice 1) | engine | 7 | `engine/Sources/ArchiveCore/Library/PhotoKitLibraryScanner.swift` |
| Locality probe (network-disallowed request) | shipped (slice 1) | engine | 7 | `engine/Sources/ArchiveCore/Library/LocalityProbe.swift` |
| Shared-album exclusion | shipped (slice 1) | engine | 7 | `engine/Sources/ArchiveCore/Library/AssetClassifier.swift` |
| Size before download | shipped (slice 1): exact on 27, estimated on 26 | engine | 6 | `engine/Sources/ArchiveCore/Library/SizeInfo.swift` |
| Developer CLI for the engine | in progress (`scan`, `environment` shipped, slice 1) | engine | 4 | `engine/Sources/ArchiveHarness/` |
```

and add two rows to the Engine table:

```
| Edited, hidden, slo-mo, cinematic exclusion | shipped (slice 1) | engine | 7 | `AssetClassifier.swift` |
| Library environment guard and Shared Library evidence | shipped (slice 1) | engine | 7 | `engine/Sources/ArchiveCore/Library/LibraryEnvironment.swift` |
```

- [ ] **Step 2: Rewrite STATE Now and Next**

In `docs/STATE.md`, replace the `## Now` section with:

```
## Now

- Phase 1, Engine, slice 2: archive log and projection with header, sanitation, layout, v1 adapter with a real fixture, harness `adopt` and `verify`. Plan to be written from spec v2 sections "Archive on the drive" and "Adopting the Python archive". Needs one real `iphoto_manifest_*.json` copied from the Acer drive into `engine/Fixtures/` while the drive is mounted and idle.
```

and remove item 1 ("Execute slice 1") from `## Next (ordered)`, renumbering the rest. Under `## Known risks carried forward`, replace "hidden-asset visibility on macOS 27 (measure in slice 1)" with the measured result from Task 9 Step 10.

- [ ] **Step 3: Changelog line**

Under `## [Unreleased]` in `CHANGELOG.md`, add at the top:

```
- 2026-09-06 engine: slice 1 shipped; ArchiveCore package with PhotoKit scan, exclusion of shared-album, edited, hidden, slo-mo and cinematic videos, exact or estimated sizes, library environment with Shared Library evidence, locality probe, and the sandboxed ArchiveHarness `scan` and `environment` commands (`engine/`).
```

- [ ] **Step 4: Journal entry**

`docs/journal/2026-09-06-engine-slice-1.md`:

```markdown
# Engine slice 1

What shipped: `engine/` package, SizeInfo, AssetFacts and AssetRecord, classifier, scanner, locality probe, library environment, harness `scan` and `environment`.

Real-library run on this Mac: environment videos=<n> hidden=<n> sources=<dict> sharedLibrary=<nil|true> smartAlbums=<list>; scan sweep=<n> included=<n> excluded=<dict> probed=<dict> elapsed=<s>.

Hidden-asset visibility: <hidden count rose by one after hiding a video | did not change>.

Shared Library evidence: <what sourceTypeCounts and smartAlbumSubtypes showed; whether anything distinguishes a Shared Library>.

Surprises: <anything that differed from the spike, or "none">.

Next session should know: slice 2 needs one real Python manifest copied from the Acer drive into `engine/Fixtures/`; pick one that contains an entry with an empty checksum if any exist (`grep -c '"checksum": ""' /Volumes/AcerFA200/Photos-archive/iphoto_manifest_*.json`).
```

Fill the angle brackets from `scratch/latest.log`.

- [ ] **Step 5: Final checks**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto/engine && swift test && make
```
Expected: `Test run with 36 tests in 7 suites passed`, `signed with sandbox entitlements`.

- [ ] **Step 6: Commit code and ledger together**

```bash
cd /Users/camoiloc/IdeaProjects/iphoto
git add engine docs/COVERAGE.md docs/STATE.md CHANGELOG.md docs/journal/2026-09-06-engine-slice-1.md
git commit -m "feat(engine): slice 1, sandboxed harness scan and environment on the real library

ArchiveHarness bundle (dev.videoattic.harness) built from the SwiftPM
executable, signed with the sandbox, Photos, and bookmark entitlements,
launched via open -n. scan sweeps the library through the classifier and
writes JSONL plus a summary; --probe N exercises LocalityProbe on real
assets; environment reports authorization, counts, canaries, and Shared
Library evidence. Coverage rows flip to shipped; STATE moves to slice 2.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review against spec v2

- Signals: `ExclusionReason` complete with all eight cases (Task 5); `Locality` and the probe outcome (Task 7); `EnvironmentReport.Authorization` (Task 8). `FailureReason`, `RefusalReason`, `DeleteOutcome`, `BudgetShortfall` belong to slices 3 to 5 where they are first used.
- Data model: every `AssetFacts` and `AssetRecord` field in the spec table is present (Task 4), including `modificationDate`, `altitude`, `isHidden`, `mediaSubtypesRaw`, `albumTitles`, `probedAt`; `SizeInfo` per D1 (Task 3).
- Classification order and the no-fallback rule: Task 5 tests each case and the precedence; Task 6 tests that `.fullSizeVideo` is never an original.
- LibraryEnvironment: `.limited` refused in the engine (`isUsable`), canaries, counts, Shared Library evidence with `nil` for "cannot tell" (Task 8). `iCloudPhotosLikely`, `optimizeStorageLikely`, and `libraryVolume` need probe results and the archive job; they arrive in slice 3.
- LocalityProbe: first chunk cancels, 3164 is cloud-only, 60 s timeout (Task 7).
- Scanner off the main actor, timing measured (Task 6); hidden-asset visibility measured (Task 9 Step 10).
- Harness: `open -n -W`, running-instance guard, `dev.videoattic.harness`, Apple Development identity required (Task 9).
- Dry-run defects: `@Suite` wrappers, corrected expected strings, `CodingKeyRepresentable` unconditional with an encoding test, extracted scanner rules with tests, full-record equality test, precedence test, error passthrough test, no dead fallbacks, resolved dates, `git add` paths only, file structure complete, `.build/release` symlink note.
- Type consistency: `SizeInfo.make(exactBytes:durationSeconds:pixelWidth:pixelHeight:)`, `AssetClassifier.classify(_:exactSizesAvailable:)`, `PhotoKitLibraryScanner.exactSizesAvailable`, `LocalityProbe.Outcome`, `EnvironmentReport`, `LibraryEnvironment.report()`, `runStamp()` are named identically everywhere they appear.
- Test count: 4 + 5 + 4 + 12 + 4 + 4 + 3 = 36, quoted in Task 8 Step 4 and Task 10 Step 5.
