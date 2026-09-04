import Foundation

/// One JSONL line. One record per video per step per attempt.
struct Record: Codable {
    var run_id: String
    var variant: String
    var ts: String
    var uuid: String
    var band: String
    var step: String            // enumerate | resources | size | locality | download | verify | cache
    var attempt: Int
    var ok: Bool
    var error_domain: String?
    var error_code: Int?
    var error_desc: String?
    var bytes: Int?
    var elapsed_s: Double?
    var mbps: Double?
    var stalls: Int?
    var note: String?
    var extra: [String: String]?
}

/// Appends records to a JSONL file and echoes a one-line summary to stdout.
final class RecordWriter {
    private let handle: FileHandle
    private let encoder = JSONEncoder()
    private let lock = NSLock()
    let runID: String
    let variant: String

    init(directory: URL, runID: String, variant: String) throws {
        self.runID = runID
        self.variant = variant
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("\(runID).jsonl")
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        handle = try FileHandle(forWritingTo: url)
        try handle.seekToEnd()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    }

    func write(_ partial: Record) {
        var r = partial
        r.run_id = runID
        r.variant = variant
        r.ts = ISO8601DateFormatter().string(from: Date())
        lock.lock(); defer { lock.unlock() }
        if let data = try? encoder.encode(r) {
            handle.write(data)
            handle.write("\n".data(using: .utf8)!)
        }
        let status = r.ok ? "ok " : "FAIL"
        var line = "[\(status)] \(r.uuid.prefix(8)) \(r.band.padding(toLength: 6, withPad: " ", startingAt: 0)) \(r.step)#\(r.attempt)"
        if let b = r.bytes { line += " \(b) B" }
        if let e = r.elapsed_s { line += String(format: " %.1fs", e) }
        if let m = r.mbps { line += String(format: " %.1f MB/s", m) }
        if let s = r.stalls, s > 0 { line += " stalls=\(s)" }
        if let c = r.error_code { line += " err=\(r.error_domain ?? "?"):\(c)" }
        if let n = r.note { line += " \(n)" }
        print(line)
        fflush(stdout)
    }

    func close() { try? handle.close() }
}

/// Convenience constructor so call sites stay short.
func record(_ v: SampleVideo, _ step: String, attempt: Int = 1, ok: Bool,
            error: Error? = nil, bytes: Int? = nil, elapsed: Double? = nil,
            stalls: Int? = nil, note: String? = nil, extra: [String: String]? = nil) -> Record {
    let ns = error.map { $0 as NSError }
    var mbps: Double? = nil
    if let b = bytes, let e = elapsed, e > 0 { mbps = Double(b) / e / 1_048_576 }
    return Record(run_id: "", variant: "", ts: "", uuid: v.uuid, band: v.band, step: step,
                  attempt: attempt, ok: ok, error_domain: ns?.domain, error_code: ns?.code,
                  error_desc: ns?.localizedDescription, bytes: bytes, elapsed_s: elapsed,
                  mbps: mbps, stalls: stalls, note: note, extra: extra)
}
