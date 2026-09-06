import Foundation
import Photos

struct StageAConfig {
    var concurrency: Int = 1
    var download = DownloadConfig()
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
    private let downloader: Downloader
    private var sweep: [String: PHAsset] = [:]   // uuid prefix -> asset

    init(sample: [SampleVideo], scratch: URL, writer: RecordWriter, config: StageAConfig) {
        self.sample = sample
        self.scratch = scratch
        self.writer = writer
        self.config = config
        self.downloader = Downloader(config: config.download)
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

    static func fetchAsset(uuid: String) -> PHAsset? {
        for id in ["\(uuid)/L0/001", uuid] {
            if let a = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject { return a }
        }
        return nil
    }

    private func fetchAsset(_ v: SampleVideo) -> (PHAsset?, String) {
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
        let video: PHAssetResource? = Downloader.originalVideoResource(for: asset)
        let durationText = String(format: "%.1f", asset.duration)
        let pixelText = "\(asset.pixelWidth)x\(asset.pixelHeight)"
        let filenameText = video?.originalFilename ?? ""
        let resourceExtra: [String: String] = ["original_filename": filenameText, "asset_duration": durationText, "pixels": pixelText]
        writer.write(record(v, "resources", ok: video != nil, note: "types=[" + types + "]", extra: resourceExtra))
        guard let resource = video else { return }

        measureSize(v, resource)

        let localityBefore = await downloader.probeLocal(resource)
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
            let result = await downloader.download(resource, to: dest)
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
            let after = await downloader.probeLocal(resource)
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
