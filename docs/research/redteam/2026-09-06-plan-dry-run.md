# Red team: slice 1 plan dry run (2026-09-06)

Fable 5.1 reviewer report, verbatim.

# Dry-run report: `docs/plans/2026-09-06-engine-slice-1.md`

## Defects (ordered by task)

### 1. Task 1, Step 5: expected output string is wrong
Swift Testing on this toolchain prints `Test run with 1 test in 0 suites passed after 0.001 seconds.`, not `Test run with 1 test passed`. Replace the Expected line with:

> Expected: build succeeds; output ends with `Test run with 1 test in 0 suites passed`.

The `.macOS("27.0")` fallback paragraph ("If `.macOS("27.0")` is rejected ...") is dead: the manifest is accepted as written and the binary gets `LC_BUILD_VERSION minos 27.0`. Delete the paragraph.

### 2. Task 2 Steps 2 and 4, Task 3 Steps 2 and 5, Task 5 Steps 1 and 2: `swift test --filter <File>Tests` runs zero tests
Swift Testing free functions have IDs of the form `ArchiveCoreTests/photoKitErrorIsClassifiedByCode()`; the file name is not part of the ID. `swift test --filter EngineErrorTests` prints `warning: No matching test cases were run` and exits 0, so Task 2 Step 4's "Expected: `2 tests passed`" and Task 3 Step 5's "`7 tests passed`" never happen. The Step 2 "compile error" expectations still hold (the build precedes filtering).

Fix: wrap the body of every test file in a suite named after the file. Exact form for `EngineErrorTests.swift` (apply the same to `AssetRecordTests.swift`, `AssetClassifierTests.swift`, `LocalityProbeTests.swift`; keep the `private func` helpers above the suite, unindented):

```swift
import Foundation
import Testing
@testable import ArchiveCore

@Suite struct EngineErrorTests {
    @Test func photoKitErrorIsClassifiedByCode() { ... }
    @Test func nonPhotoKitErrorIsWrappedAsUnderlying() { ... }
}
```

Verified: with the wrapper, `swift test --filter AssetClassifierTests` runs exactly that file. Update the Expected lines to the real phrasing: Task 2 Step 4 `Test run with 2 tests in 1 suite passed`; Task 3 Step 5 `Test run with 7 tests in 1 suite passed` (see defect 8 for the revised counts).

### 3. Task 3, Step 5: the `CodingKeyRepresentable` claim is false and the trigger never fires
`ScanSummary` compiles as `Codable` with `[ExclusionReason: Int]` regardless, so "If `ScanSummary` fails to compile ... add the extension" never triggers. Without the extension, `JSONEncoder` emits the dictionary as a flat array: `{"excluded":["notUserLibrary",1],"included":0}`. The sentence "on macOS 27 `String`-raw enums encode as dictionary keys without it" is wrong; SE-0320 requires an explicit conformance.

Fix: append unconditionally to `AssetClassifier.swift`:

```swift
extension ExclusionReason: CodingKeyRepresentable {}
```

Verified output afterwards: `{"excluded":{"notUserLibrary":1},"included":0}`. Add this test to `AssetClassifierTests` so the shape is pinned (Step 1):

```swift
@Test func summaryEncodesReasonsAsObjectKeys() throws {
    var s = ScanSummary()
    s.count(.excluded(.sizeUnknown))
    let enc = JSONEncoder(); enc.outputFormatting = [.sortedKeys]
    #expect(String(data: try enc.encode(s), encoding: .utf8) == #"{"excluded":{"sizeUnknown":1},"included":0}"#)
}
```

Replace the Step 5 sentence with: "Expected: `Test run with 9 tests in 1 suite passed`."

### 4. Task 4, Step 2: dead fallback about `__dataSize`
The macOS 27 SDK header declares `dataSize` as `NSNumber * NS_REFINED_FOR_SWIFT`, and the Photos Swift overlay exposes `public var dataSize: Swift.Int? { get }` under `@available(macOS 27, *)`. `resource?.dataSize` compiles as `Int?` with the 27.0 deployment target. Delete the "If `resource?.dataSize` fails to compile ..." paragraph. Note the spike compiled this under an `#available(macOS 27, *)` guard with `-target arm64-apple-macos26.0`; the guard is unnecessary here because the package's minimum is 27.0.

### 5. Task 4: "No unit test" leaves two pure rules untested
Two decisions in `PhotoKitLibraryScanner` are pure and are the spec's actual LibraryScanner rules: which resource counts as the original, and which identifiers are tried. Extract them. Replace `originalVideoResource(for:)` and `fetchAsset(uuid:)` in Step 1 with:

```swift
    /// Index of the resource to treat as the original: the first `.video`, else the first `.fullSizeVideo`.
    public static func originalVideoResourceIndex(in types: [PHAssetResourceType]) -> Int? {
        types.firstIndex(of: .video) ?? types.firstIndex(of: .fullSizeVideo)
    }

    /// The original video resource: `.video`, or `.fullSizeVideo` when there is no unedited original.
    public static func originalVideoResource(for asset: PHAsset) -> PHAssetResource? {
        let resources = PHAssetResource.assetResources(for: asset)
        return originalVideoResourceIndex(in: resources.map(\.type)).map { resources[$0] }
    }

    /// Local identifiers tried in order for a bare UUID (spike finding 5).
    public static func candidateIdentifiers(uuid: String) -> [String] {
        ["\(uuid)/L0/001", uuid]
    }

    /// Direct fetch by local identifier. macOS identifiers take the form "UUID/L0/001" (spike finding 5).
    public static func fetchAsset(uuid: String) -> PHAsset? {
        for id in candidateIdentifiers(uuid: uuid) {
            if let a = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject { return a }
        }
        return nil
    }
```

Add `engine/Tests/ArchiveCoreTests/ScannerRulesTests.swift` (a test target may `import Photos` without library access; verified):

```swift
import Foundation
import Photos
import Testing
@testable import ArchiveCore

@Suite struct ScannerRulesTests {
    @Test func unadjustedVideoResourceIsPreferredWhateverTheOrder() {
        #expect(PhotoKitLibraryScanner.originalVideoResourceIndex(in: [.fullSizeVideo, .video]) == 1)
        #expect(PhotoKitLibraryScanner.originalVideoResourceIndex(in: [.video, .fullSizeVideo]) == 0)
    }
    @Test func editedOnlyVideoFallsBackToFullSize() {
        #expect(PhotoKitLibraryScanner.originalVideoResourceIndex(in: [.photo, .fullSizeVideo]) == 1)
    }
    @Test func noVideoResourceGivesNil() {
        #expect(PhotoKitLibraryScanner.originalVideoResourceIndex(in: [.photo, .adjustmentData]) == nil)
    }
    @Test func bareUUIDTriesTheMacOSFormFirst() {
        #expect(PhotoKitLibraryScanner.candidateIdentifiers(uuid: "ABC") == ["ABC/L0/001", "ABC"])
    }
}
```

Change Task 4's Files list to include the test file, replace "No unit test: ..." with "The PhotoKit reads are exercised by the harness; the two pure rules are tested.", and change Step 2 to `swift test --filter ScannerRulesTests`, Expected `Test run with 4 tests in 1 suite passed`.

### 6. Task 3, Step 1 and Task 2, Step 1: tests that pass with a wrong implementation
- `userLibraryVideoWithSizeIsIncluded` only checks `sizeBytes` and `locality`; an implementation that drops the filename, date, or dimensions passes. Replace its body with a full-record comparison:

```swift
@Test func userLibraryVideoWithSizeIsIncluded() {
    let expected = AssetRecord(
        photosIdentifier: "AAAA-1/L0/001", originalFilename: "IMG_0001.MOV", sizeBytes: 1_000,
        creationDate: Date(timeIntervalSince1970: 0), latitude: nil, longitude: nil,
        durationSeconds: 1, pixelWidth: 10, pixelHeight: 10, isFavorite: false, hasAdjustments: false,
        locality: .unknown)
    #expect(AssetClassifier.classify(facts()) == .included(expected))
}
```

- Rule precedence is untested: an asset with no video resource always has nil size, and the reason reported must be `noOriginalVideoResource`. Add to `AssetClassifierTests`:

```swift
@Test func missingResourceWinsOverMissingSize() {
    #expect(AssetClassifier.classify(facts(size: nil, hasVideoResource: false)) == .excluded(.noOriginalVideoResource))
}
```

- `EngineError.from` has an untested branch (passthrough of an existing `EngineError`). Add to `EngineErrorTests`:

```swift
@Test func engineErrorPassesThroughUnchanged() {
    #expect(EngineError.from(EngineError.message("x")) == .message("x"))
}
```

### 7. Task 6, Step 7: dead fallback about signing
`security find-identity -v -p codesigning` on this Mac returns one identity, `Apple Development: Dmitri Samoilov (55C99545MK)`; `make` signs with it and prints `signed with sandbox entitlements` (verified, entitlements listed correctly by `codesign -d --entitlements -`). Replace the "If `security find-identity` returns nothing ..." sentence with: "The Makefile picks the Apple Development identity present on this Mac."

### 8. Test counts after defects 3, 5, 6
Recount: Task 2 = 3 + 3 = 6; Task 3 = 9 (7 + precedence + encoding), running total 15; Task 4 = 4, total 19; Task 5 = 3, total 22. Replace:
- Task 2 Step 8: `Test run with 6 tests in 2 suites passed`
- Task 5 Step 4: `Test run with 22 tests in 5 suites passed (6 from Task 2, 9 from Task 3, 4 from Task 4, 3 here)`
- Task 7 Step 5: `22 tests passed, bundle signed`

### 9. Task 6, Steps 8 and 9: no instruction for the failure paths
`open -W` returns 0 whatever the harness's exit code, and every failure before `freopen` (picker cancelled, bookmark unresolvable) goes to a stderr nobody sees. Add after the "Expected" paragraph in Step 8:

> If `scratch/latest.log` does not exist after the run, the folder picker was cancelled or the folder was not chosen: rerun with `--pick-output`. If the log ends at `photos authorization: 2` (denied) or `0` (not determined, the prompt did not appear), run `make reset-tcc`, rerun, and allow the prompt; if it still does not appear, enable ArchiveHarness under System Settings > Privacy & Security > Photos. Exit codes are visible only in the log line order, not from `make`. Both dialogs can open behind other windows because the app is an accessory; check the Dock and Mission Control.

### 10. Task 7, Files list and Step 4: unresolved date placeholder
`docs/journal/2026-09-XX-engine-slice-1.md` and `docs/journal/<date>-engine-slice-1.md` should both read `docs/journal/2026-09-06-engine-slice-1.md`; the CHANGELOG line's `<date>` should read `2026-09-06`. The plan was written today; there is no reason to leave it open.

### 11. Task 7, Step 6 and all commits: pre-existing dirty tree
The repo already has uncommitted modifications (`README.md`, `src/iphoto/cli.py`, `src/iphoto/mover.py`, `src/iphoto/scanner.py`) and untracked `tests/test_cli_resume.py`, `tests/test_mover.py`, `tests/test_scanner.py` that are not part of this slice. Add to "Conventions for every task": "The working tree has unrelated Python changes. Use only the `git add` paths listed; never `git add -A`, `git add .`, or `git commit -a`."

### 12. File structure block: missing entries
Add `Sources/ArchiveCore/ArchiveCore.swift`, `Tests/ArchiveCoreTests/LocalityProbeTests.swift`, and `Tests/ArchiveCoreTests/ScannerRulesTests.swift`; the block currently lists neither of the first two though Tasks 1 and 5 create them.

### 13. Task 6, Step 6 (minor): `.build/release` is a symlink on this toolchain
`.build/release` resolves to `out/Products/Release`; `make` follows it and the second `make` is a no-op (`Nothing to be done for 'all'`). No change needed, but add a note so the engineer does not treat the symlink as a wrong path.

## Verified as written

- `Package.swift` with `swift-tools-version: 6.0`, `.macOS("27.0")`, `.swiftLanguageMode(.v5)` on all three targets: builds; `swift test` builds the AppKit executable target too.
- Every Swift file in Tasks 1 through 6 compiles verbatim, in task order, with zero warnings on a clean `swift build --build-tests`. All cross-task names resolve (`fetchAsset(uuid:)`, `originalVideoResource(for:)`, `HarnessError`, `ArchiveCore.version`, `PhotoKitLibraryScanner.Result`).
- `Equatable`/`Sendable` synthesis for `Classification` (contains `AssetRecord`), `Codable` for `AssetRecord` with `Date?`, `Sendable` on `PhotoKitLibraryScanner.Result`; `#expect(... == .excluded(.notUserLibrary))` and `guard case .included(let record)` with `Issue.record("expected included")` compile and behave.
- `@testable import ArchiveCore` under language mode 5; `NSError(domain:code:)` without `userInfo`; `withCheckedContinuation` with a captured `var resumed` in mode 5; `PHAssetResourceManager.requestData` unused result produces no warning.
- All 15 planned tests pass (plus the 7 proposed above: 22 total, 23 with the encoding probe I used).
- Makefile: `find` in `SOURCES`, `swift build -c release --product ArchiveHarness`, copy into the bundle, `codesign` with the entitlements on a bundle whose executable has no embedded Info.plist (the bundle's `Contents/Info.plist` supplies the identifier `com.videoattic.ArchiveHarness`), and the `grep -q app-sandbox` check. Binary is a thin arm64 Mach-O linked against `/usr/lib/swift/libswiftCore.dylib` and the system frameworks, rpath `@loader_path` only, so it runs standalone inside the bundle. Argument parsing runs: `--bogus` exits 2 with `unknown argument --bogus`.
- `freopen` ordering: `OutputFolder.obtain` calls `startAccessingSecurityScopedResource()` before returning on both the bookmark and picker paths; `run()` calls `freopen` after that; `stopAccessingSecurityScopedResource()` is deferred to `run()`'s return, and `exit` follows. Correct.
- `open -W -a <app> --args --command scan --pick-output --probe 10` is the same pattern the spike used with `--stage` arguments; `make scan ARGS="--pick-output --probe 10"` expands to that.
- `.gitignore`: root already ignores `build/` and `*.log`, so `/engine/build/` is redundant but harmless; `/engine/.build/` (Task 1) and `/engine/scratch/` (Task 6 Step 10) are needed and are added before the commits that would otherwise pick up build products or JSONL.
- Task ordering: Tasks 1 through 5 each commit; Task 6 intentionally does not, and Task 7 Step 6 adds `engine`, `.gitignore`, and the four ledger files, leaving nothing from the slice uncommitted.
- Task 7 ledger edits: the three COVERAGE rows and the "Developer CLI" row exist verbatim in `docs/COVERAGE.md`; `docs/STATE.md` has the `## Now` section and item 1 of `## Next (ordered)` as described; `CHANGELOG.md` has `## [Unreleased]`.

result: Dry run of the engine slice 1 plan found 13 defects (dead test filters, false Codable claim, missing tests, dead fallbacks, unresolved placeholders) with replacement text; all plan code compiles and the bundle builds and signs on this toolchain.