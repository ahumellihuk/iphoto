import Foundation
import Photos

struct DownloadConfig {
    var stallSeconds: TimeInterval = 180
    var absoluteCapSeconds: TimeInterval = 3600
}

struct DownloadResult {
    let ok: Bool; let error: Error?; let bytes: Int; let elapsed: Double; let stalls: Int; let note: String?
}

struct Probe { let ok: Bool; let error: Error? }

/// Shared PhotoKit resource access for stages A and B: locality probe and
/// streamed download with stall cancellation.
final class Downloader {
    private let manager = PHAssetResourceManager.default()
    let config: DownloadConfig

    init(config: DownloadConfig) { self.config = config }

    static func originalVideoResource(for asset: PHAsset) -> PHAssetResource? {
        let resources = PHAssetResource.assetResources(for: asset)
        return resources.first { $0.type == .video } ?? resources.first { $0.type == .fullSizeVideo }
    }

    /// Request with network disallowed. Success means the bytes are local.
    func probeLocal(_ resource: PHAssetResource) async -> Probe {
        let opts = PHAssetResourceRequestOptions()
        opts.isNetworkAccessAllowed = false
        return await withCheckedContinuation { cont in
            var done = false
            manager.requestData(for: resource, options: opts, dataReceivedHandler: { _ in }) { error in
                guard !done else { return }
                done = true
                cont.resume(returning: Probe(ok: error == nil, error: error))
            }
        }
    }

    /// Streams the resource to `dest` with network allowed. Cancels on stall.
    func download(_ resource: PHAssetResource, to dest: URL) async -> DownloadResult {
        try? FileManager.default.removeItem(at: dest)
        try? FileManager.default.createDirectory(at: dest.deletingLastPathComponent(), withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: dest.path, contents: nil)
        guard let handle = try? FileHandle(forWritingTo: dest) else {
            return DownloadResult(ok: false, error: SpikeError.message("cannot open dest"), bytes: 0, elapsed: 0, stalls: 0, note: nil)
        }
        let opts = PHAssetResourceRequestOptions()
        opts.isNetworkAccessAllowed = true

        let state = DownloadState()
        opts.progressHandler = { p in state.touch(progress: p) }
        let start = Date()

        let requestID = manager.requestData(for: resource, options: opts, dataReceivedHandler: { data in
            handle.write(data)
            state.touch(bytes: data.count)
        }) { error in
            state.finish(error: error)
        }

        while !state.isFinished {
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            let now = Date()
            if now.timeIntervalSince(state.lastActivity) > config.stallSeconds {
                state.stalls += 1
                state.note = "stalled after \(state.bytes) B, no activity for \(Int(config.stallSeconds))s"
                manager.cancelDataRequest(requestID)
                state.waitFinish(timeout: 10)
                break
            }
            if now.timeIntervalSince(start) > config.absoluteCapSeconds {
                state.note = "absolute cap \(Int(config.absoluteCapSeconds))s exceeded"
                manager.cancelDataRequest(requestID)
                state.waitFinish(timeout: 10)
                break
            }
        }
        try? handle.close()
        let elapsed = Date().timeIntervalSince(start)
        let ok = state.error == nil && state.isFinished && state.note == nil
        return DownloadResult(ok: ok, error: state.error, bytes: state.bytes, elapsed: elapsed,
                              stalls: state.stalls, note: state.note ?? state.progressSummary)
    }
}

/// Mutable state shared between PhotoKit callbacks and the watchdog.
final class DownloadState {
    private let lock = NSLock()
    private let done = DispatchSemaphore(value: 0)
    private(set) var lastActivity = Date()
    private(set) var bytes = 0
    private(set) var error: Error?
    private(set) var isFinished = false
    var stalls = 0
    var note: String?
    private var progressSamples: [Double] = []

    func touch(bytes n: Int) { lock.lock(); bytes += n; lastActivity = Date(); lock.unlock() }
    func touch(progress p: Double) {
        lock.lock(); lastActivity = Date()
        if progressSamples.last.map({ p - $0 >= 0.1 }) ?? true { progressSamples.append(p) }
        lock.unlock()
    }
    func finish(error e: Error?) {
        lock.lock(); error = e; isFinished = true; lock.unlock(); done.signal()
    }
    func waitFinish(timeout: TimeInterval) { _ = done.wait(timeout: .now() + timeout) }
    var progressSummary: String? {
        progressSamples.isEmpty ? nil : "progress=" + progressSamples.map { String(format: "%.1f", $0) }.joined(separator: ",")
    }
}
