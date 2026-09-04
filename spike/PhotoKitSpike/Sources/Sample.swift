import Foundation

/// One video in the spike sample, produced by spike/select_sample.py and
/// enriched by spike/ground_truth.py. Field names match the JSON on disk.
struct SampleVideo: Codable {
    let uuid: String
    let original_filename: String
    let size_bytes: Int
    let is_local: Bool
    let band: String            // small | medium | large | local
    let paired: Bool
    let moment_name: String?
    var reference_sha256: String?
    var reference_size: Int?

    /// Byte size the download is compared against: the AppleScript export
    /// when paired, otherwise the Photos database value.
    var expectedSize: Int { reference_size ?? size_bytes }
}

struct Sample: Codable {
    let created: String
    let library_path: String?
    let videos: [SampleVideo]

    static func load(from url: URL) throws -> Sample {
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(Sample.self, from: data)
    }

    func subset(_ name: String) -> [SampleVideo] {
        switch name {
        case "all": return videos
        case "paired": return videos.filter { $0.paired }
        case "icloud": return videos.filter { !$0.is_local }
        default: return videos.filter { $0.band == name }
        }
    }
}
