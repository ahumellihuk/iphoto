import Foundation
import Photos

struct StageAConfig {
    var concurrency: Int = 1
    var stallSeconds: TimeInterval = 180
    var absoluteCapSeconds: TimeInterval = 3600
    var attempts: Int = 3
    var backoff: [TimeInterval] = [5, 15, 45]
    var skipDownload = false
    var keepFiles = false
    var onlyCloud = false        // skip download when the locality probe says the original is already local
}

/// Read-only measurements. Never modifies the library.
final class StageA {
    let sample: [SampleVideo]
    let scratch: URL
    let writer: RecordWriter
    let config: StageAConfig
    private let manager = PHAssetResourceManager.default()
    private var sweep: [String: PHAsset] = [:]   // uuid prefix -> asset

    init(sample: [SampleVideo], scratch: URL, writer: RecordWriter, config: StageAConfig) {
        self.sample = sample
        self.scratch = scratch
        self.writer = writer
        self.config = config
    }

    func run() async {
        buildSweep()
        await withTaskGroup(of: Void.self) { group in
            var iterator = sample.makeIterator()
            var running = 0
            func launch(_ v: SampleVideo) {
                group.addTask { await self.measure(v) }
            }
            while running < config.concurrency, let v = iterator.next() { launch(v); running += 1 }
            while await group.next() != nil {
                if let v = iterator.next() { launch(v) }
            }
        }
    }

    // MARK: enumeration

    private func buildSweep() {
        let opts = PHFetchOptions()
        opts.includeHiddenAssets = true
        let result = PHAsset.fetchAssets(with: .video, options: opts)
        result.enumerateObjects { asset, _, _ in
            let prefix = asset.localIdentifier.split(separator: "/").first.map(String.init) ?? asset.localIdentifier
            self.sweep[prefix] = asset
        }
        print("sweep: \(result.count) video assets visible to PhotoKit")
    }

    private func fetchAsset(_ v: SampleVideo) -> (PHAsset?, String) {
        // Direct fetch, both identifier spellings seen on macOS.
        for id in ["\(v.uuid)/L0/001", v.uuid] {
            let r = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil)
            if let a = r.firstObject { return (a, "direct:\(id.hasSuffix("/L0/001") ? "L0" : "bare")") }
        }
        if let a = sweep[v.uuid] { return (a, "sweep-only") }
        return (nil, "missing")
    }

    // MARK: per-video pipeline

    private func measure(_ v: SampleVideo) async {
        let (assetOpt, how) = fetchAsset(v)
        let inSweep = sweep[v.uuid] != nil
        writer.write(record(v, "enumerate", ok: assetOpt != nil, note: how,
                            extra: ["in_sweep": "\(inSweep)"]))
        guard let asset = assetOpt else { return }

        let resources = PHAssetResource.assetResources(for: asset)
        let types: String = resources.map { String($0.type.rawValue) }.joined(separator: ",")
        let video: PHAssetResource? = resources.first { $0.type == .video } ?? resources.first { $0.type == .fullSizeVideo }
        let durationText = String(format: "%.1f", asset.duration)
        let pixelText = "\(asset.pixelWidth)x\(asset.pixelHeight)"
        let filenameText = video?.originalFilename ?? ""
        let resourceExtra: [String: String] = ["original_filename": filenameText, "asset_duration": durationText, "pixels": pixelText]
        writer.write(record(v, "resources", ok: video != nil, note: "types=[" + types + "]", extra: resourceExtra))
        guard let resource = video else { return }

        measureSize(v, resource)

        let localityBefore = await probeLocal(resource)
        let expectedLocal = v.is_local
        let observedLocal = localityBefore.ok
        writer.write(record(v, "locality", ok: observedLocal == expectedLocal, error: localityBefore.error,
                            note: "db_local=\(expectedLocal) observed_local=\(observedLocal)"))

        if config.skipDownload { return }
        if config.onlyCloud && observedLocal {
            writer.write(record(v, "download", ok: false, note: "skipped: original already local"))
            return
        }

        var success = false
        for attempt in 1...config.attempts {
            let dest = scratch.appendingPathComponent("\(v.uuid)-\(v.original_filename)")
            let result = await download(resource, to: dest)
            writer.write(record(v, "download", attempt: attempt, ok: result.ok, error: result.error,
                                bytes: result.bytes, elapsed: result.elapsed, stalls: result.stalls,
                                note: result.note))
            if result.ok {
                verify(v, dest)
                success = true
                break
            }
            try? FileManager.default.removeItem(at: dest)
            if attempt < config.attempts {
                let delay = config.backoff[min(attempt - 1, config.backoff.count - 1)]
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            }
        }

        if success {
            let after = await probeLocal(resource)
            writer.write(record(v, "cache", ok: true, error: after.error,
                                note: after.ok ? "cached_in_library" : "not_cached"))
        }
    }

    private func measureSize(_ v: SampleVideo, _ resource: PHAssetResource) {
        var publicSize: Int? = nil
        if #available(macOS 27, *) {
            publicSize = resource.dataSize
        }
        let privateSize = (resource.value(forKey: "fileSize") as? NSNumber)?.intValue
        let dbSize = v.size_bytes
        let ok = publicSize == dbSize
        writer.write(record(v, "size", ok: ok,
                            note: "public=\(publicSize.map(String.init) ?? "nil") private=\(privateSize.map(String.init) ?? "nil") db=\(dbSize)",
                            extra: ["public_matches_db": "\(publicSize == dbSize)",
                                    "private_matches_db": "\(privateSize == dbSize)"]))
    }

    // MARK: PhotoKit calls

    private struct Probe { let ok: Bool; let error: Error? }

    /// Request with network disallowed. Success means the bytes are local.
    private func probeLocal(_ resource: PHAssetResource) async -> Probe {
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

    private struct DownloadResult {
        let ok: Bool; let error: Error?; let bytes: Int; let elapsed: Double; let stalls: Int; let note: String?
    }

    /// Streams the resource to `dest` with network allowed. Cancels on stall.
    private func download(_ resource: PHAssetResource, to dest: URL) async -> DownloadResult {
        try? FileManager.default.removeItem(at: dest)
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

        // Watchdog: cancel on progress inactivity or absolute cap.
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

    private func verify(_ v: SampleVideo, _ dest: URL) {
        let size = Hashing.fileSize(of: dest) ?? -1
        let start = Date()
        let sha = (try? Hashing.sha256(of: dest)) ?? "error"
        let hashTime = Date().timeIntervalSince(start)
        let sizeOK = size == v.expectedSize
        var hashOK: Bool? = nil
        if let ref = v.reference_sha256 { hashOK = (sha == ref) }
        let ok = sizeOK && (hashOK ?? true)
        writer.write(record(v, "verify", ok: ok, bytes: size, elapsed: hashTime,
                            note: "size_ok=\(sizeOK) hash_ok=\(hashOK.map { "\($0)" } ?? "n/a") expected=\(v.expectedSize)",
                            extra: ["sha256": sha]))
        if !config.keepFiles { try? FileManager.default.removeItem(at: dest) }
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
