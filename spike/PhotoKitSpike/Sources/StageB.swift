import CoreLocation
import Foundation
import Photos

/// Stage B: the destructive measurements, run as separate explicit steps.
///
///   prepare   download each candidate into <scratch>/archive and <scratch>/archive-backup,
///             verify both copies, write archive/manifest.json. Read-only for the library.
///   delete    re-verify both copies, then PHAssetChangeRequest.deleteAssets in ONE change
///             block, then re-fetch to confirm. Requires --i-understand.
///   restore   PHAssetCreationRequest from the archive copy with creationDate and location
///             from the manifest; re-download the new asset and hash it against the manifest.
///   bookmark  resolve the archive bookmark (a mounted disk image stands in for the drive),
///             write and read a probe file, report isStale.
///
/// Nothing in stage B runs unless --stage names it. Candidates come from --uuids.
final class StageB {
    struct Entry: Codable {
        var uuid: String
        var local_identifier: String
        var original_filename: String
        var size_bytes: Int
        var sha256: String
        var reference_sha256: String?
        var creation_date: String?
        var latitude: Double?
        var longitude: Double?
        var duration: Double
        var pixel_width: Int
        var pixel_height: Int
        var is_favorite: Bool
        var archive_path: String
        var backup_path: String
        var prepared_at: String
        var deleted_at: String?
        var restored_identifier: String?
        var restored_at: String?
    }

    let scratch: URL
    let writer: RecordWriter
    let downloader: Downloader
    let iso = ISO8601DateFormatter()

    var archiveDir: URL { scratch.appendingPathComponent("archive") }
    var backupDir: URL { scratch.appendingPathComponent("archive-backup") }
    var manifestURL: URL { archiveDir.appendingPathComponent("manifest.json") }

    init(scratch: URL, writer: RecordWriter, downloadConfig: DownloadConfig) {
        self.scratch = scratch
        self.writer = writer
        self.downloader = Downloader(config: downloadConfig)
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    }

    // MARK: manifest

    private func loadManifest() -> [String: Entry] {
        guard let data = try? Data(contentsOf: manifestURL),
              let entries = try? JSONDecoder().decode([Entry].self, from: data) else { return [:] }
        return Dictionary(uniqueKeysWithValues: entries.map { ($0.uuid, $0) })
    }

    private func saveManifest(_ m: [String: Entry]) {
        try? FileManager.default.createDirectory(at: archiveDir, withIntermediateDirectories: true)
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? enc.encode(m.values.sorted { $0.uuid < $1.uuid }) {
            try? data.write(to: manifestURL)
        }
    }

    private func video(_ uuid: String, _ e: Entry?) -> SampleVideo {
        SampleVideo(uuid: uuid, original_filename: e?.original_filename ?? "", size_bytes: e?.size_bytes ?? 0,
                    is_local: false, band: "stageB", paired: e?.reference_sha256 != nil, moment_name: nil,
                    reference_sha256: e?.reference_sha256, reference_size: e?.size_bytes)
    }

    // MARK: prepare

    func prepare(uuids: [String], references: [String: String]) async -> Bool {
        var manifest = loadManifest()
        var allOK = true
        for uuid in uuids {
            let v = video(uuid, manifest[uuid])
            guard let asset = StageA.fetchAsset(uuid: uuid), let resource = Downloader.originalVideoResource(for: asset) else {
                writer.write(record(v, "prepare", ok: false, note: "asset or original resource not found")); allOK = false; continue
            }
            let filename = resource.originalFilename
            let archivePath = archiveDir.appendingPathComponent("\(uuid)-\(filename)")
            let backupPath = backupDir.appendingPathComponent("\(uuid)-\(filename)")

            let result = await downloader.download(resource, to: archivePath)
            guard result.ok else {
                writer.write(record(v, "prepare", ok: false, error: result.error, note: "download failed: \(result.note ?? "")")); allOK = false; continue
            }
            let size = Hashing.fileSize(of: archivePath) ?? -1
            let sha = (try? Hashing.sha256(of: archivePath)) ?? "error"
            let ref = references[uuid]
            let refOK = ref.map { $0 == sha }

            try? FileManager.default.createDirectory(at: backupDir, withIntermediateDirectories: true)
            try? FileManager.default.removeItem(at: backupPath)
            do { try FileManager.default.copyItem(at: archivePath, to: backupPath) } catch {
                writer.write(record(v, "prepare", ok: false, error: error, note: "backup copy failed")); allOK = false; continue
            }
            let backupSha = (try? Hashing.sha256(of: backupPath)) ?? "error"

            let ok = sha != "error" && backupSha == sha && (refOK ?? true) && size > 0
            manifest[uuid] = Entry(
                uuid: uuid, local_identifier: asset.localIdentifier, original_filename: filename, size_bytes: size,
                sha256: sha, reference_sha256: ref,
                creation_date: asset.creationDate.map { iso.string(from: $0) },
                latitude: asset.location?.coordinate.latitude, longitude: asset.location?.coordinate.longitude,
                duration: asset.duration, pixel_width: asset.pixelWidth, pixel_height: asset.pixelHeight,
                is_favorite: asset.isFavorite,
                archive_path: archivePath.path, backup_path: backupPath.path,
                prepared_at: iso.string(from: Date()), deleted_at: nil, restored_identifier: nil, restored_at: nil)
            saveManifest(manifest)
            writer.write(record(v, "prepare", ok: ok, bytes: size, elapsed: result.elapsed,
                                note: "two copies verified=\(backupSha == sha) reference_match=\(refOK.map { "\($0)" } ?? "n/a") "
                                    + "date=\(asset.creationDate.map { iso.string(from: $0) } ?? "nil") "
                                    + "location=\(asset.location.map { "\($0.coordinate.latitude),\($0.coordinate.longitude)" } ?? "nil")",
                                extra: ["sha256": sha, "archive": archivePath.path]))
            if !ok { allOK = false }
        }
        return allOK
    }

    // MARK: delete

    /// Re-hash both copies now, then delete in one change block, then confirm by re-fetch.
    func delete(uuids: [String]) async -> Bool {
        var manifest = loadManifest()
        var assets: [PHAsset] = []
        for uuid in uuids {
            let v = video(uuid, manifest[uuid])
            guard let e = manifest[uuid] else {
                writer.write(record(v, "delete-precheck", ok: false, note: "not in manifest; run prepare first")); return false
            }
            let a = (try? Hashing.sha256(of: URL(fileURLWithPath: e.archive_path))) ?? "error"
            let b = (try? Hashing.sha256(of: URL(fileURLWithPath: e.backup_path))) ?? "error"
            let copiesOK = a == e.sha256 && b == e.sha256
            guard let asset = StageA.fetchAsset(uuid: uuid) else {
                writer.write(record(v, "delete-precheck", ok: false, note: "asset not found in library")); return false
            }
            let canDelete = asset.canPerform(.delete)
            writer.write(record(v, "delete-precheck", ok: copiesOK && canDelete,
                                note: "archive_ok=\(a == e.sha256) backup_ok=\(b == e.sha256) canPerformDelete=\(canDelete)"))
            guard copiesOK && canDelete else { return false }
            assets.append(asset)
        }

        print("Deleting \(assets.count) assets in one change block. Watch for the system dialog; note its exact wording.")
        let start = Date()
        var completionFired = false
        let outcome: (Bool, Error?) = await withCheckedContinuation { cont in
            var resumed = false
            PHPhotoLibrary.shared().performChanges({
                PHAssetChangeRequest.deleteAssets(assets as NSArray)
            }) { success, error in
                guard !resumed else { return }
                resumed = true
                completionFired = true
                cont.resume(returning: (success, error))
            }
            // Watchdog for the "completion never fires" bug: give up after 120 s.
            DispatchQueue.global().asyncAfter(deadline: .now() + 120) {
                guard !resumed else { return }
                resumed = true
                cont.resume(returning: (false, SpikeError.message("performChanges completion did not fire within 120 s")))
            }
        }
        let elapsed = Date().timeIntervalSince(start)

        var allGone = true
        for uuid in uuids {
            let still = StageA.fetchAsset(uuid: uuid) != nil
            if still { allGone = false }
            let v = video(uuid, manifest[uuid])
            writer.write(record(v, "delete", ok: outcome.0 && !still, error: outcome.1, elapsed: elapsed,
                                note: "completion_fired=\(completionFired) success=\(outcome.0) still_fetchable=\(still)"))
            if !still, var e = manifest[uuid] { e.deleted_at = iso.string(from: Date()); manifest[uuid] = e }
        }
        saveManifest(manifest)
        return outcome.0 && allGone
    }

    // MARK: restore

    func restore(uuids: [String]) async -> Bool {
        var manifest = loadManifest()
        var allOK = true
        for uuid in uuids {
            let v = video(uuid, manifest[uuid])
            guard let e = manifest[uuid] else {
                writer.write(record(v, "restore", ok: false, note: "not in manifest")); allOK = false; continue
            }
            let source = URL(fileURLWithPath: e.archive_path)
            guard (try? Hashing.sha256(of: source)) == e.sha256 else {
                writer.write(record(v, "restore", ok: false, note: "archive copy no longer matches manifest")); allOK = false; continue
            }
            let wantDate = e.creation_date.flatMap { iso.date(from: $0) }
            let wantLocation: CLLocation? = (e.latitude != nil && e.longitude != nil) ? CLLocation(latitude: e.latitude!, longitude: e.longitude!) : nil

            let start = Date()
            var placeholderID: String?
            let outcome: (Bool, Error?) = await withCheckedContinuation { cont in
                var resumed = false
                PHPhotoLibrary.shared().performChanges({
                    let req = PHAssetCreationRequest.forAsset()
                    let opts = PHAssetResourceCreationOptions()
                    opts.originalFilename = e.original_filename
                    opts.shouldMoveFile = false
                    req.addResource(with: .video, fileURL: source, options: opts)
                    if let d = wantDate { req.creationDate = d }
                    if let l = wantLocation { req.location = l }
                    req.isFavorite = e.is_favorite
                    placeholderID = req.placeholderForCreatedAsset?.localIdentifier
                }) { success, error in
                    guard !resumed else { return }
                    resumed = true
                    cont.resume(returning: (success, error))
                }
                DispatchQueue.global().asyncAfter(deadline: .now() + 600) {
                    guard !resumed else { return }
                    resumed = true
                    cont.resume(returning: (false, SpikeError.message("creation completion did not fire within 600 s")))
                }
            }
            let elapsed = Date().timeIntervalSince(start)
            guard outcome.0, let newID = placeholderID,
                  let newAsset = PHAsset.fetchAssets(withLocalIdentifiers: [newID], options: nil).firstObject else {
                writer.write(record(v, "restore", ok: false, error: outcome.1, elapsed: elapsed,
                                    note: "creation failed placeholder=\(placeholderID ?? "nil")")); allOK = false; continue
            }

            // Metadata round trip.
            let gotDate = newAsset.creationDate
            let dateDelta = (wantDate != nil && gotDate != nil) ? abs(gotDate!.timeIntervalSince(wantDate!)) : nil
            let dateOK = wantDate == nil || (dateDelta ?? 1e9) <= 1.0
            var locDelta: Double? = nil
            if let want = wantLocation, let got = newAsset.location { locDelta = got.distance(from: want) }
            let locOK = wantLocation == nil || (locDelta ?? 1e9) <= 10.0
            let durationOK = abs(newAsset.duration - e.duration) <= 0.5

            // Byte round trip: re-download the new asset's original and hash it.
            var bytesOK = false
            var roundTripNote = "no resource"
            if let res = Downloader.originalVideoResource(for: newAsset) {
                let tmp = scratch.appendingPathComponent("restore-check-\(uuid)")
                let dl = await downloader.download(res, to: tmp)
                if dl.ok {
                    let sha = (try? Hashing.sha256(of: tmp)) ?? "error"
                    bytesOK = sha == e.sha256
                    roundTripNote = "redownload_sha_match=\(bytesOK) size=\(Hashing.fileSize(of: tmp) ?? -1)"
                } else {
                    roundTripNote = "redownload failed: \(dl.note ?? dl.error?.localizedDescription ?? "")"
                }
                try? FileManager.default.removeItem(at: tmp)
            }

            let ok = dateOK && locOK && durationOK && bytesOK
            var entry = e
            entry.restored_identifier = newAsset.localIdentifier
            entry.restored_at = iso.string(from: Date())
            manifest[uuid] = entry
            saveManifest(manifest)
            writer.write(record(v, "restore", ok: ok, elapsed: elapsed,
                                note: "new_id=\(newAsset.localIdentifier) date_delta_s=\(dateDelta.map { String(format: "%.3f", $0) } ?? "n/a") "
                                    + "location_delta_m=\(locDelta.map { String(format: "%.1f", $0) } ?? "n/a") duration_ok=\(durationOK) \(roundTripNote)",
                                extra: ["new_local_identifier": newAsset.localIdentifier,
                                        "got_date": gotDate.map { iso.string(from: $0) } ?? "nil",
                                        "got_location": newAsset.location.map { "\($0.coordinate.latitude),\($0.coordinate.longitude)" } ?? "nil"]))
            if !ok { allOK = false }
        }
        return allOK
    }

    // MARK: bookmark

    /// Resolve a separately bookmarked archive volume, write and read a probe file.
    @MainActor
    func bookmark(forcePick: Bool) -> Bool {
        let key = "archiveVolumeBookmark"
        var url: URL?
        var stale = false
        var how = "resolved"
        if !forcePick, let data = UserDefaults.standard.data(forKey: key) {
            // .withoutMounting: a bookmark to a disk image would otherwise mount it on resolve,
            // which a product must never do silently; a physical drive that is unplugged fails here.
            do {
                url = try URL(resolvingBookmarkData: data, options: [.withSecurityScope, .withoutMounting], relativeTo: nil, bookmarkDataIsStale: &stale)
            } catch {
                let ns = error as NSError
                writer.write(record(video("-", nil), "bookmark", ok: false, error: error,
                                    note: "resolve failed stale=\(stale) domain=\(ns.domain) code=\(ns.code)"))
                return false
            }
            if url == nil { how = "resolve failed" }
        }
        if url == nil {
            guard let picked = ScratchFolder.pick(message: "Choose the ARCHIVE volume for the bookmark test (the mounted disk image)",
                                                  startAt: URL(fileURLWithPath: "/Volumes/SpikeArchive"), requirePrefix: "/Volumes/") else {
                writer.write(record(video("-", nil), "bookmark", ok: false, note: "no volume chosen")); return false
            }
            if let data = try? picked.bookmarkData(options: [.withSecurityScope], includingResourceValuesForKeys: nil, relativeTo: nil) {
                UserDefaults.standard.set(data, forKey: key)
            }
            url = picked; how = forcePick ? "picked" : "picked after \(how)"
        }
        guard let volume = url else { return false }
        let started = volume.startAccessingSecurityScopedResource()
        defer { if started { volume.stopAccessingSecurityScopedResource() } }
        let probe = volume.appendingPathComponent("photokit-spike-probe.txt")
        let payload = "probe \(iso.string(from: Date()))"
        var writeOK = false, readOK = false, err: Error?
        do {
            try payload.write(to: probe, atomically: true, encoding: .utf8)
            writeOK = true
            readOK = (try String(contentsOf: probe, encoding: .utf8)) == payload
        } catch { err = error }
        let reachable = (try? volume.checkResourceIsReachable()) ?? false
        let rv = try? volume.resourceValues(forKeys: [.volumeUUIDStringKey, .volumeNameKey, .volumeIsRootFileSystemKey, .volumeTotalCapacityKey, .isVolumeKey])
        let volumeNote = "volume_uuid=\(rv?.volumeUUIDString ?? "nil") volume_name=\(rv?.volumeName ?? "nil") is_root_fs=\(rv?.volumeIsRootFileSystem.map { "\($0)" } ?? "nil") is_volume=\(rv?.isVolume.map { "\($0)" } ?? "nil") capacity_mb=\((rv?.volumeTotalCapacity ?? 0) / 1_048_576)"
        writer.write(record(video("-", nil), "bookmark", ok: writeOK && readOK, error: err,
                            note: "\(how) stale=\(stale) reachable=\(reachable) access_started=\(started) write=\(writeOK) read=\(readOK) path=\(volume.path) \(volumeNote)"))
        if stale, let data = try? volume.bookmarkData(options: [.withSecurityScope], includingResourceValuesForKeys: nil, relativeTo: nil) {
            UserDefaults.standard.set(data, forKey: key)
        }
        return writeOK && readOK
    }
}
