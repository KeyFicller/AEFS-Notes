import AppKit
import Foundation

enum InboxEnqueueResult {
    case accepted(Int)
    case full
    case invalidImage
}

final class InboxQueue {
    static let maxCount = 32

    let directory: URL
    private var items: [URL] = []

    var count: Int { items.count }
    var isEmpty: Bool { items.isEmpty }
    var head: URL? { items.first }

    init(directory: URL) {
        self.directory = directory
    }

    func loadFromDisk() {
        let fm = FileManager.default
        try? fm.createDirectory(at: directory, withIntermediateDirectories: true)
        guard let files = try? fm.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else { return }
        items = files
            .filter { $0.pathExtension.lowercased() == "png" }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
            .filter { url in
                if NSImage(contentsOf: url) != nil { return true }
                fputs("DeskPet: skip unreadable inbox file \(url.lastPathComponent)\n", stderr)
                return false
            }
    }

    func enqueue(_ data: Data) -> InboxEnqueueResult {
        guard items.count < Self.maxCount else { return .full }
        guard NSImage(data: data) != nil else { return .invalidImage }
        let fm = FileManager.default
        try? fm.createDirectory(at: directory, withIntermediateDirectories: true)
        let stamp = Self.stamp.string(from: Date())
        let rand = String(UUID().uuidString.prefix(8))
        let url = directory.appendingPathComponent("\(stamp)-\(rand).png")
        do {
            try data.write(to: url, options: .atomic)
        } catch {
            fputs("DeskPet: failed to write inbox file: \(error)\n", stderr)
            return .invalidImage
        }
        items.append(url)
        return .accepted(items.count)
    }

    func dequeue(_ url: URL) {
        items.removeAll { $0 == url }
        do {
            try FileManager.default.removeItem(at: url)
        } catch {
            fputs("DeskPet: failed to delete inbox file \(url.lastPathComponent): \(error)\n", stderr)
        }
    }

    private static let stamp: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMddHHmmss"
        return formatter
    }()

    static func isImage(_ data: Data) -> Bool {
        guard data.count >= 3 else { return false }
        if data.starts(with: [0x89, 0x50, 0x4E, 0x47]) { return true }
        if data.starts(with: [0xFF, 0xD8, 0xFF]) { return true }
        if data.starts(with: [0x47, 0x49, 0x46]) { return true }
        return NSImage(data: data) != nil
    }
}
