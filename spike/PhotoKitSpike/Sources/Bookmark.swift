import AppKit
import Foundation

/// The scratch folder is reached exactly the way the product will reach an
/// external drive: chosen once in an open panel, persisted as an app-scoped
/// security-scoped bookmark, resolved on every launch.
enum ScratchFolder {
    private static let key = "scratchBookmark"

    /// Resolves the stored bookmark, or shows the panel if there is none or it is stale.
    /// Returns the URL with security scope already started; caller stops it at exit.
    @MainActor
    static func obtain(forcePick: Bool) throws -> (url: URL, wasStale: Bool) {
        if !forcePick, let data = UserDefaults.standard.data(forKey: key) {
            var stale = false
            if let url = try? URL(resolvingBookmarkData: data, options: [.withSecurityScope],
                                  relativeTo: nil, bookmarkDataIsStale: &stale) {
                if url.startAccessingSecurityScopedResource() {
                    if stale { store(url) }
                    return (url, stale)
                }
            }
        }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.prompt = "Use as scratch"
        panel.message = "Choose the scratch folder for PhotoKit spike downloads"
        NSApp.activate(ignoringOtherApps: true)
        guard panel.runModal() == .OK, let url = panel.url else {
            throw SpikeError.message("No scratch folder chosen")
        }
        store(url)
        _ = url.startAccessingSecurityScopedResource()
        return (url, false)
    }

    /// Show an open panel for a directory. Used by stage B for the archive volume.
    @MainActor
    static func pick(message: String) -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.prompt = "Use this folder"
        panel.message = message
        NSApp.activate(ignoringOtherApps: true)
        return panel.runModal() == .OK ? panel.url : nil
    }

    private static func store(_ url: URL) {
        if let data = try? url.bookmarkData(options: [.withSecurityScope], includingResourceValuesForKeys: nil, relativeTo: nil) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}

enum SpikeError: Error, CustomStringConvertible {
    case message(String)
    var description: String {
        switch self { case .message(let m): return m }
    }
}
