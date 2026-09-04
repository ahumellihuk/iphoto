import AppKit
import Foundation
import Photos

/// PhotoKit spike, stage A. Headless: runs from the command line inside a
/// sandboxed bundle so permissions attach to this bundle, not Terminal.
///
///   PhotoKitSpike.app/Contents/MacOS/PhotoKitSpike --variant A1 \
///       [--sample sample.json] [--out results] \
///       [--subset all|paired|icloud|small|medium|large|local] [--concurrency N]
///       [--skip-download] [--keep-files] [--pick-scratch] [--stall 180] [--cap 3600]
///
/// The sandbox hides every path outside the container, so --sample and --out
/// are resolved relative to the user-selected scratch folder, the one folder
/// the app is allowed to touch. Put sample.json there.

struct Args {
    var sample = "sample.json"
    var out = "results"
    var variant = "A1"
    var subset = "all"
    var config = StageAConfig()
    var pickScratch = false

    init() {
        var it = CommandLine.arguments.dropFirst().makeIterator()
        while let a = it.next() {
            switch a {
            case "--sample": sample = it.next() ?? sample
            case "--out": out = it.next() ?? out
            case "--variant": variant = it.next() ?? variant
            case "--subset": subset = it.next() ?? subset
            case "--concurrency": config.concurrency = Int(it.next() ?? "1") ?? 1
            case "--stall": config.stallSeconds = Double(it.next() ?? "180") ?? 180
            case "--cap": config.absoluteCapSeconds = Double(it.next() ?? "3600") ?? 3600
            case "--attempts": config.attempts = Int(it.next() ?? "3") ?? 3
            case "--skip-download": config.skipDownload = true
            case "--keep-files": config.keepFiles = true
            case "--pick-scratch": pickScratch = true
            default: fputs("unknown argument \(a)\n", stderr); exit(2)
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        Task { @MainActor in
            let code = await runSpike()
            exit(code)
        }
    }
}

@MainActor
func runSpike() async -> Int32 {
    let args = Args()

    let scratch: URL
    do {
        let r = try ScratchFolder.obtain(forcePick: args.pickScratch)
        scratch = r.url
        print("scratch: \(scratch.path) stale_bookmark=\(r.wasStale)")
    } catch { fputs("\(error)\n", stderr); return 1 }
    defer { scratch.stopAccessingSecurityScopedResource() }

    // Launched through LaunchServices (`open`) there is no terminal; mirror all
    // output into <scratch>/results/latest.log so a run is never silent.
    if isatty(STDOUT_FILENO) == 0 {
        let logDir = scratch.appendingPathComponent(args.out)
        try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)
        let logPath = logDir.appendingPathComponent("latest.log").path
        freopen(logPath, "a", stdout)
        freopen(logPath, "a", stderr)
        setvbuf(stdout, nil, _IOLBF, 0)
        print("---- \(ISO8601DateFormatter().string(from: Date())) \(CommandLine.arguments.dropFirst().joined(separator: " "))")
    }

    let sampleURL = URL(fileURLWithPath: args.sample, relativeTo: scratch)
    let outURL = URL(fileURLWithPath: args.out, relativeTo: scratch)
    let sample: Sample
    do { sample = try Sample.load(from: sampleURL) } catch {
        fputs("cannot load sample \(sampleURL.path): \(error)\n", stderr); return 1
    }
    let videos = sample.subset(args.subset)
    let totalBytes = videos.reduce(0) { $0 + $1.size_bytes }
    print("sample: \(videos.count) videos, \(totalBytes / 1_048_576) MiB, subset=\(args.subset) variant=\(args.variant) concurrency=\(args.config.concurrency)")

    let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
    print("photos authorization: \(status.rawValue) (\(status == .authorized ? "authorized" : "NOT authorized"))")
    guard status == .authorized else { return 3 }

    if !args.config.skipDownload {
        let free = (try? scratch.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]).volumeAvailableCapacityForImportantUsage) ?? 0
        let need = Int64(Double(totalBytes) * 1.5)
        print("scratch free: \(free / 1_048_576) MiB, need \(need / 1_048_576) MiB")
        if free < need { fputs("not enough scratch space\n", stderr); return 4 }
    }

    let photosRunning = !NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos").isEmpty
    let runID = "\(args.variant)-" + ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "")
    let writer: RecordWriter
    do { writer = try RecordWriter(directory: outURL, runID: runID, variant: args.variant) } catch {
        fputs("cannot open results: \(error)\n", stderr); return 1
    }
    let pv = ProcessInfo.processInfo.operatingSystemVersion
    writer.write(Record(run_id: "", variant: "", ts: "", uuid: "-", band: "-", step: "run_start", attempt: 0, ok: true,
                        error_domain: nil, error_code: nil, error_desc: nil, bytes: totalBytes, elapsed_s: nil, mbps: nil, stalls: nil,
                        note: "macOS \(pv.majorVersion).\(pv.minorVersion).\(pv.patchVersion) photos_running=\(photosRunning) sandboxed=\(ProcessInfo.processInfo.environment["APP_SANDBOX_CONTAINER_ID"] != nil)",
                        extra: ["subset": args.subset, "concurrency": "\(args.config.concurrency)", "videos": "\(videos.count)"]))

    let stage = StageA(sample: videos, scratch: scratch, writer: writer, config: args.config)
    let start = Date()
    await stage.run()
    writer.write(Record(run_id: "", variant: "", ts: "", uuid: "-", band: "-", step: "run_end", attempt: 0, ok: true,
                        error_domain: nil, error_code: nil, error_desc: nil, bytes: nil,
                        elapsed_s: Date().timeIntervalSince(start), mbps: nil, stalls: nil, note: nil, extra: nil))
    writer.close()
    print("results: \(outURL.appendingPathComponent(runID + ".jsonl").path)")
    return 0
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
