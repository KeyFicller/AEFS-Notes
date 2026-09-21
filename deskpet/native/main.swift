import AppKit
import Foundation

struct Config: Codable {
    var character: String
    var cardsDir: [String]
    var cardMaxWidth: Int
    var zoom: Double
    var awayAfterMinutes: Double
    var inboxPort: Int
    var inboxTunnel: Bool
    var inboxHostname: String
    var repeatHoverAfter: Int
    var repeatHoverWindowMinutes: Double
    var hoverExitSeconds: Double
    var studyMode: StudyMode
    var explainModel: String
    var explainApiBase: String
    var explainPrompt: String
    var explainBubbleWidth: Double
    var explainBubbleHeight: Double
    var explainFontSize: Double

    enum CodingKeys: String, CodingKey {
        case character
        case cardsDir = "cards_dir"
        case cardMaxWidth = "card_max_width"
        case zoom
        case awayAfterMinutes = "away_after_minutes"
        case disdainAfterMinutes = "disdain_after_minutes"
        case inboxPort = "inbox_port"
        case inboxTunnel = "inbox_tunnel"
        case inboxHostname = "inbox_hostname"
        case repeatHoverAfter = "repeat_hover_after"
        case repeatHoverWindowMinutes = "repeat_hover_window_minutes"
        case hoverExitSeconds = "hover_exit_seconds"
        case studyMode = "study_mode"
        case explainModel = "explain_model"
        case explainApiBase = "explain_api_base"
        case explainPrompt = "explain_prompt"
        case explainBubbleWidth = "explain_bubble_width"
        case explainBubbleHeight = "explain_bubble_height"
        case explainFontSize = "explain_font_size"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        character = try box.decode(String.self, forKey: .character)
        cardsDir = decodeCardsDir(box)
        cardMaxWidth = try box.decodeIfPresent(Int.self, forKey: .cardMaxWidth) ?? 460
        zoom = try box.decodeIfPresent(Double.self, forKey: .zoom) ?? 1.0
        awayAfterMinutes = try box.decodeIfPresent(Double.self, forKey: .awayAfterMinutes)
            ?? (try box.decodeIfPresent(Double.self, forKey: .disdainAfterMinutes) ?? 10)
        inboxPort = try box.decodeIfPresent(Int.self, forKey: .inboxPort) ?? 8765
        inboxTunnel = try box.decodeIfPresent(Bool.self, forKey: .inboxTunnel) ?? true
        inboxHostname = try box.decodeIfPresent(String.self, forKey: .inboxHostname) ?? ""
        repeatHoverAfter = try box.decodeIfPresent(Int.self, forKey: .repeatHoverAfter) ?? 5
        repeatHoverWindowMinutes = try box.decodeIfPresent(Double.self, forKey: .repeatHoverWindowMinutes) ?? 1
        hoverExitSeconds = try box.decodeIfPresent(Double.self, forKey: .hoverExitSeconds) ?? 1
        if let raw = try box.decodeIfPresent(String.self, forKey: .studyMode) {
            studyMode = StudyMode(rawValue: raw) ?? .annotate
        } else {
            studyMode = .annotate
        }
        explainModel = try box.decodeIfPresent(String.self, forKey: .explainModel)
            ?? ExplainConfig.defaults.model
        explainApiBase = try box.decodeIfPresent(String.self, forKey: .explainApiBase)
            ?? ExplainConfig.defaults.apiBase
        explainPrompt = try box.decodeIfPresent(String.self, forKey: .explainPrompt)
            ?? ExplainConfig.defaults.promptTemplate
        explainBubbleWidth = try box.decodeIfPresent(Double.self, forKey: .explainBubbleWidth)
            ?? Double(BubbleStyle.defaults.width)
        explainBubbleHeight = try box.decodeIfPresent(Double.self, forKey: .explainBubbleHeight)
            ?? Double(BubbleStyle.defaults.height)
        explainFontSize = try box.decodeIfPresent(Double.self, forKey: .explainFontSize)
            ?? Double(BubbleStyle.defaults.fontSize)
    }

    func encode(to encoder: Encoder) throws {
        var box = encoder.container(keyedBy: CodingKeys.self)
        try box.encode(character, forKey: .character)
        try box.encode(cardsDir, forKey: .cardsDir)
        try box.encode(cardMaxWidth, forKey: .cardMaxWidth)
        try box.encode(zoom, forKey: .zoom)
        try box.encode(awayAfterMinutes, forKey: .awayAfterMinutes)
        try box.encode(inboxPort, forKey: .inboxPort)
        try box.encode(inboxTunnel, forKey: .inboxTunnel)
        try box.encode(inboxHostname, forKey: .inboxHostname)
        try box.encode(repeatHoverAfter, forKey: .repeatHoverAfter)
        try box.encode(repeatHoverWindowMinutes, forKey: .repeatHoverWindowMinutes)
        try box.encode(hoverExitSeconds, forKey: .hoverExitSeconds)
        try box.encode(studyMode.rawValue, forKey: .studyMode)
        try box.encode(explainModel, forKey: .explainModel)
        try box.encode(explainApiBase, forKey: .explainApiBase)
        try box.encode(explainPrompt, forKey: .explainPrompt)
        try box.encode(explainBubbleWidth, forKey: .explainBubbleWidth)
        try box.encode(explainBubbleHeight, forKey: .explainBubbleHeight)
        try box.encode(explainFontSize, forKey: .explainFontSize)
    }

    var explain: ExplainConfig {
        ExplainConfig(
            apiBase: explainApiBase,
            model: explainModel,
            promptTemplate: explainPrompt
        )
    }

    var bubbleStyle: BubbleStyle {
        BubbleStyle(
            width: max(CGFloat(explainBubbleWidth), 180),
            height: max(CGFloat(explainBubbleHeight), 120),
            fontSize: min(max(CGFloat(explainFontSize), 10), 28)
        )
    }
}

enum StudyMode: String {
    case annotate
    case reveal
}

struct CharacterSpec: Decodable {
    let id: String?
    let name: String?
    let idle: String
    let hover: String
    let peek: String?
    let peekHover: String?
    let peekAway: String?
    let inbox: String?
    let peekInbox: String?
    let repeatHover: String?
    let peekRepeatHover: String?
    let reveal: String?
    let peekReveal: String?
    let away: String?
    let size: Int?
    let scale: String?
    let peekScale: Double?

    enum CodingKeys: String, CodingKey {
        case id, name, idle, hover, peek, inbox, away, size, scale
        case peekHover = "peek_hover"
        case peekAway = "peek_away"
        case peekInbox = "peek_inbox"
        case repeatHover = "repeat_hover"
        case peekRepeatHover = "peek_repeat_hover"
        case reveal
        case peekReveal = "peek_reveal"
        case peekScale = "peek_scale"
        case awayLegacy = "disdain"
        case peekAwayLegacy = "peek_disdain"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        id = try box.decodeIfPresent(String.self, forKey: .id)
        name = try box.decodeIfPresent(String.self, forKey: .name)
        idle = try box.decode(String.self, forKey: .idle)
        hover = try box.decode(String.self, forKey: .hover)
        peek = try box.decodeIfPresent(String.self, forKey: .peek)
        peekHover = try box.decodeIfPresent(String.self, forKey: .peekHover)
        peekAway = try box.decodeIfPresent(String.self, forKey: .peekAway)
            ?? box.decodeIfPresent(String.self, forKey: .peekAwayLegacy)
        inbox = try box.decodeIfPresent(String.self, forKey: .inbox)
        peekInbox = try box.decodeIfPresent(String.self, forKey: .peekInbox)
        repeatHover = try box.decodeIfPresent(String.self, forKey: .repeatHover)
        peekRepeatHover = try box.decodeIfPresent(String.self, forKey: .peekRepeatHover)
        reveal = try box.decodeIfPresent(String.self, forKey: .reveal)
        peekReveal = try box.decodeIfPresent(String.self, forKey: .peekReveal)
        away = try box.decodeIfPresent(String.self, forKey: .away)
            ?? box.decodeIfPresent(String.self, forKey: .awayLegacy)
        size = try box.decodeIfPresent(Int.self, forKey: .size)
        scale = try box.decodeIfPresent(String.self, forKey: .scale)
        peekScale = try box.decodeIfPresent(Double.self, forKey: .peekScale)
    }
}

struct CharacterPack {
    let id: String
    let name: String
    let idle: NSImage
    let hover: NSImage
    let peek: NSImage
    let peekHover: NSImage
    let peekAway: NSImage
    let inbox: NSImage
    let peekInbox: NSImage
    let repeatHover: NSImage
    let peekRepeatHover: NSImage
    let reveal: NSImage
    let peekReveal: NSImage
    let away: NSImage
    let size: CGFloat
    let nearest: Bool
    let peekScale: CGFloat
}

enum DockedEdge {
    case none, left, right, top, bottom
}

func deskpetRoot() -> URL {
    let fm = FileManager.default
    let exeDir = URL(fileURLWithPath: CommandLine.arguments[0])
        .standardizedFileURL
        .deletingLastPathComponent()
    let cwd = URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true)
    let candidates = [
        exeDir,
        cwd.appendingPathComponent("deskpet"),
        cwd,
        exeDir.deletingLastPathComponent().appendingPathComponent("deskpet"),
    ]
    for candidate in candidates {
        if fm.fileExists(atPath: candidate.appendingPathComponent("config.json").path) {
            return candidate
        }
    }
    fputs("DeskPet: config.json not found. Run `python3 -m deskpet` from the repo root.\n", stderr)
    exit(1)
}

func loadJSON<T: Decodable>(_ type: T.Type, from url: URL) -> T {
    do {
        return try JSONDecoder().decode(type, from: Data(contentsOf: url))
    } catch {
        fputs("DeskPet: failed to read \(url.lastPathComponent): \(error)\n", stderr)
        exit(1)
    }
}

func saveJSON<T: Encodable>(_ value: T, to url: URL) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    do {
        try encoder.encode(value).write(to: url)
    } catch {
        fputs("DeskPet: failed to write \(url.lastPathComponent): \(error)\n", stderr)
    }
}

func decodeCardsDir(_ box: KeyedDecodingContainer<Config.CodingKeys>) -> [String] {
    let fallback = ["../notes/cards"]
    guard box.contains(.cardsDir) else { return fallback }
    if let list = try? box.decode([String].self, forKey: .cardsDir) {
        return list.isEmpty ? fallback : list
    }
    if let one = try? box.decode(String.self, forKey: .cardsDir), !one.isEmpty {
        return [one]
    }
    return fallback
}

func matchesCardExclude(_ card: URL, pattern: String, relativeTo root: URL) -> Bool {
    let dirs = card.deletingLastPathComponent().pathComponents
    if dirs.contains(where: { $0 == pattern || $0.hasPrefix(pattern + "-") }) {
        return true
    }
    guard pattern.contains("/") || pattern.contains("\\") || pattern.hasPrefix(".") else {
        return false
    }
    let dir = URL(fileURLWithPath: pattern, isDirectory: true, relativeTo: root)
        .absoluteURL
        .standardizedFileURL
    let prefix = dir.path.hasSuffix("/") ? dir.path : dir.path + "/"
    return card.path == dir.path || card.path.hasPrefix(prefix)
}

func listCanonicalCards(fromPatterns patterns: [String], relativeTo root: URL) -> [URL] {
    var includes: [URL] = []
    var excludes: [String] = []
    for raw in patterns {
        let trimmed = raw.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix("!") {
            let value = String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces)
            if !value.isEmpty { excludes.append(value) }
        } else if !trimmed.isEmpty {
            includes.append(
                URL(fileURLWithPath: trimmed, isDirectory: true, relativeTo: root)
                    .absoluteURL
                    .standardizedFileURL
            )
        }
    }
    if includes.isEmpty {
        includes = [
            URL(fileURLWithPath: "../notes/cards", isDirectory: true, relativeTo: root)
                .absoluteURL
                .standardizedFileURL
        ]
    }
    var seen = Set<String>()
    var cards: [URL] = []
    for include in includes {
        for card in listCanonicalCards(root: include) {
            let url = card.standardizedFileURL
            if seen.insert(url.path).inserted {
                cards.append(url)
            }
        }
    }
    if !excludes.isEmpty {
        cards = cards.filter { card in
            !excludes.contains { matchesCardExclude(card, pattern: $0, relativeTo: root) }
        }
    }
    return cards.sorted { $0.path < $1.path }
}

func listCanonicalCards(root: URL) -> [URL] {
    let fm = FileManager.default
    guard let phases = try? fm.contentsOfDirectory(
        at: root,
        includingPropertiesForKeys: [.isDirectoryKey],
        options: [.skipsHiddenFiles]
    ) else { return [] }
    var cards: [URL] = []
    for phase in phases {
        var isDir: ObjCBool = false
        guard fm.fileExists(atPath: phase.path, isDirectory: &isDir), isDir.boolValue else { continue }
        guard let files = try? fm.contentsOfDirectory(
            at: phase,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else { continue }
        cards.append(contentsOf: files.filter { $0.pathExtension.lowercased() == "png" })
    }
    return cards.sorted { $0.path < $1.path }
}

func rasterize(_ source: NSImage) -> (data: [UInt8], width: Int, height: Int)? {
    guard let cg = source.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return nil
    }
    let width = cg.width
    let height = cg.height
    var data = [UInt8](repeating: 0, count: height * width * 4)
    guard let ctx = CGContext(
        data: &data,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { return nil }
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
    return (data, width, height)
}

func imageFromRGBA(_ data: inout [UInt8], width: Int, height: Int, pointSize: NSSize) -> NSImage? {
    guard let ctx = CGContext(
        data: &data,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ), let cg = ctx.makeImage() else { return nil }
    return NSImage(cgImage: cg, size: pointSize)
}

func prepareSprite(_ source: NSImage) -> NSImage {
    guard let raster = rasterize(source) else { return source }
    var data = raster.data
    knockOutEdge(&data, width: raster.width, height: raster.height)
    peelWhiteFringe(&data, width: raster.width, height: raster.height, passes: 4)
    let radius = max(3, raster.width / 110)
    addNavyOutline(&data, width: raster.width, height: raster.height, radius: radius)
    return cropRGBA(
        data,
        width: raster.width,
        height: raster.height,
        pointScale: source.size.width / CGFloat(raster.width),
        pad: radius + 2
    ) ?? source
}

func knockOutEdge(_ data: inout [UInt8], width: Int, height: Int) {
    func idx(_ x: Int, _ y: Int) -> Int { (y * width + x) * 4 }
    func isBackground(_ x: Int, _ y: Int) -> Bool {
        let i = idx(x, y)
        if data[i + 3] == 0 { return true }
        let r = Int(data[i]), g = Int(data[i + 1]), b = Int(data[i + 2])
        let nearWhite = r >= 242 && g >= 242 && b >= 242
        let nearBlack = r <= 22 && g <= 22 && b <= 22
        return nearWhite || nearBlack
    }
    var seen = [Bool](repeating: false, count: width * height)
    var queue: [(Int, Int)] = []
    for x in 0..<width {
        queue.append((x, 0))
        queue.append((x, height - 1))
    }
    for y in 0..<height {
        queue.append((0, y))
        queue.append((width - 1, y))
    }
    var head = 0
    while head < queue.count {
        let (x, y) = queue[head]
        head += 1
        if x < 0 || y < 0 || x >= width || y >= height { continue }
        let slot = y * width + x
        if seen[slot] { continue }
        seen[slot] = true
        if !isBackground(x, y) { continue }
        let i = idx(x, y)
        data[i] = 0
        data[i + 1] = 0
        data[i + 2] = 0
        data[i + 3] = 0
        queue.append((x + 1, y))
        queue.append((x - 1, y))
        queue.append((x, y + 1))
        queue.append((x, y - 1))
    }
}

func peelWhiteFringe(_ data: inout [UInt8], width: Int, height: Int, passes: Int) {
    func idx(_ x: Int, _ y: Int) -> Int { (y * width + x) * 4 }
    func nearTransparent(_ x: Int, _ y: Int) -> Bool {
        if x < 0 || y < 0 || x >= width || y >= height { return true }
        return data[idx(x, y) + 3] < 16
    }
    for _ in 0..<passes {
        var kill: [Int] = []
        for y in 0..<height {
            for x in 0..<width {
                let i = idx(x, y)
                let a = data[i + 3]
                if a == 0 { continue }
                let r = Int(data[i]), g = Int(data[i + 1]), b = Int(data[i + 2])
                let fringe = (r >= 220 && g >= 220 && b >= 220) || a < 90
                if fringe, nearTransparent(x + 1, y) || nearTransparent(x - 1, y)
                    || nearTransparent(x, y + 1) || nearTransparent(x, y - 1) {
                    kill.append(i)
                }
            }
        }
        for i in kill {
            data[i] = 0
            data[i + 1] = 0
            data[i + 2] = 0
            data[i + 3] = 0
        }
    }
}

func addNavyOutline(_ data: inout [UInt8], width: Int, height: Int, radius: Int) {
    let count = width * height
    var opaque = [Bool](repeating: false, count: count)
    for i in 0..<count {
        opaque[i] = data[i * 4 + 3] > 40
    }
    var dilated = opaque
    for _ in 0..<radius {
        var next = dilated
        for y in 0..<height {
            for x in 0..<width {
                let s = y * width + x
                if dilated[s] { continue }
                var hit = false
                for dy in -1...1 where !hit {
                    for dx in -1...1 where !hit {
                        let nx = x + dx, ny = y + dy
                        if nx < 0 || ny < 0 || nx >= width || ny >= height { continue }
                        if dilated[ny * width + nx] { hit = true }
                    }
                }
                if hit { next[s] = true }
            }
        }
        dilated = next
    }
    for i in 0..<count where dilated[i] && !opaque[i] {
        let p = i * 4
        data[p] = 22
        data[p + 1] = 42
        data[p + 2] = 96
        data[p + 3] = 255
    }
}

func cropRGBA(
    _ data: [UInt8],
    width: Int,
    height: Int,
    pointScale: CGFloat,
    pad: Int
) -> NSImage? {
    var minX = width, minY = height, maxX = 0, maxY = 0
    var found = false
    for y in 0..<height {
        for x in 0..<width {
            if data[(y * width + x) * 4 + 3] > 12 {
                found = true
                minX = min(minX, x)
                maxX = max(maxX, x)
                minY = min(minY, y)
                maxY = max(maxY, y)
            }
        }
    }
    guard found else { return nil }
    minX = max(0, minX - pad)
    minY = max(0, minY - pad)
    maxX = min(width - 1, maxX + pad)
    maxY = min(height - 1, maxY + pad)
    let cropW = maxX - minX + 1
    let cropH = maxY - minY + 1
    var out = [UInt8](repeating: 0, count: cropW * cropH * 4)
    for y in minY...maxY {
        for x in minX...maxX {
            let si = (y * width + x) * 4
            let di = ((y - minY) * cropW + (x - minX)) * 4
            out[di] = data[si]
            out[di + 1] = data[si + 1]
            out[di + 2] = data[si + 2]
            out[di + 3] = data[si + 3]
        }
    }
    return imageFromRGBA(
        &out,
        width: cropW,
        height: cropH,
        pointSize: NSSize(width: CGFloat(cropW) * pointScale, height: CGFloat(cropH) * pointScale)
    )
}

func loadImage(_ url: URL) -> NSImage? {
    guard let image = NSImage(contentsOf: url) else { return nil }
    return prepareSprite(image)
}

func requireImage(_ url: URL) -> NSImage {
    guard let image = loadImage(url) else {
        fputs("DeskPet: missing image \(url.path)\n", stderr)
        exit(1)
    }
    return image
}

func flippedHorizontally(_ image: NSImage) -> NSImage {
    guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return image
    }
    let width = cg.width
    let height = cg.height
    let bytesPerRow = width * 4
    var data = [UInt8](repeating: 0, count: height * bytesPerRow)
    guard let ctx = CGContext(
        data: &data,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: bytesPerRow,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { return image }
    ctx.translateBy(x: CGFloat(width), y: 0)
    ctx.scaleBy(x: -1, y: 1)
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
    guard let out = ctx.makeImage() else { return image }
    return NSImage(cgImage: out, size: image.size)
}

func fitted(_ image: NSImage, maxShortSide: CGFloat, maxWidth: CGFloat, maxHeight: CGFloat) -> NSSize {
    let size = image.size
    let short = min(size.width, size.height)
    let scale = min(
        maxShortSide / max(short, 1),
        maxWidth / max(size.width, 1),
        maxHeight / max(size.height, 1),
        1
    )
    return NSSize(width: size.width * scale, height: size.height * scale)
}

func rangesOverlap(_ aMin: CGFloat, _ aMax: CGFloat, _ bMin: CGFloat, _ bMax: CGFloat) -> Bool {
    aMin < bMax && bMin < aMax
}

func distanceFrom(_ point: NSPoint, to rect: NSRect) -> CGFloat {
    let x = min(max(point.x, rect.minX), rect.maxX)
    let y = min(max(point.y, rect.minY), rect.maxY)
    return hypot(point.x - x, point.y - y)
}

func screenAt(_ point: NSPoint) -> NSScreen? {
    NSScreen.screens.first { $0.frame.contains(point) }
}

func bestScreen(for frame: NSRect) -> NSScreen? {
    let screens = NSScreen.screens
    guard !screens.isEmpty else { return nil }
    if let hit = screenAt(NSPoint(x: frame.midX, y: frame.midY)) {
        return hit
    }
    var best: NSScreen?
    var bestOverlap: CGFloat = 0
    for screen in screens {
        let overlap = frame.intersection(screen.frame)
        let area = max(0, overlap.width) * max(0, overlap.height)
        if area > bestOverlap {
            bestOverlap = area
            best = screen
        }
    }
    if let best { return best }
    let center = NSPoint(x: frame.midX, y: frame.midY)
    return screens.min { distanceFrom(center, to: $0.frame) < distanceFrom(center, to: $1.frame) }
}

func isSharedEdge(_ edge: DockedEdge, of screen: NSScreen, along window: NSRect) -> Bool {
    let home = screen.frame
    let slop: CGFloat = 24
    for other in NSScreen.screens where other !== screen {
        let frame = other.frame
        switch edge {
        case .right:
            if abs(frame.minX - home.maxX) <= slop,
               rangesOverlap(window.minY, window.maxY, frame.minY, frame.maxY) { return true }
        case .left:
            if abs(frame.maxX - home.minX) <= slop,
               rangesOverlap(window.minY, window.maxY, frame.minY, frame.maxY) { return true }
        case .top:
            if abs(frame.minY - home.maxY) <= slop,
               rangesOverlap(window.minX, window.maxX, frame.minX, frame.maxX) { return true }
        case .bottom:
            if abs(frame.maxY - home.minY) <= slop,
               rangesOverlap(window.minX, window.maxX, frame.minX, frame.maxX) { return true }
        case .none:
            return false
        }
    }
    return false
}

struct ScribbleStyle {
    var color: NSColor
    var width: CGFloat

    static let initial = ScribbleStyle(
        color: NSColor.systemYellow.withAlphaComponent(0.5),
        width: 16
    )
}

final class Chip: NSView {
    enum Kind {
        case color(NSColor)
        case width(CGFloat)
        case shapeCircle
        case shapeRect
    }

    let kind: Kind
    var selected = false { didSet { needsDisplay = true } }
    var onPick: (() -> Void)?

    init(kind: Kind) {
        self.kind = kind
        super.init(frame: .zero)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    override func draw(_ dirtyRect: NSRect) {
        switch kind {
        case .color(let color):
            color.setFill()
            NSBezierPath(ovalIn: bounds.insetBy(dx: 4, dy: 4)).fill()
        case .width(let width):
            NSColor.white.setFill()
            let diameter = min(max(width * 0.65, 5), bounds.width - 10)
            let rect = NSRect(
                x: (bounds.width - diameter) / 2,
                y: (bounds.height - diameter) / 2,
                width: diameter,
                height: diameter
            )
            NSBezierPath(ovalIn: rect).fill()
        case .shapeCircle:
            NSColor.white.setFill()
            NSBezierPath(ovalIn: bounds.insetBy(dx: 6, dy: 6)).fill()
        case .shapeRect:
            NSColor.white.setFill()
            NSBezierPath(rect: bounds.insetBy(dx: 7, dy: 7)).fill()
        }
        if selected {
            NSColor.white.setStroke()
            let ring = NSBezierPath(ovalIn: bounds.insetBy(dx: 1.5, dy: 1.5))
            ring.lineWidth = 2
            ring.stroke()
        }
    }

    override func mouseDown(with event: NSEvent) { onPick?() }
}

private func barButton(_ title: String, symbol: String) -> NSButton {
    let button = NSButton(title: "", target: nil, action: nil)
    button.toolTip = title
    button.isBordered = false
    button.bezelStyle = .regularSquare
    button.imagePosition = .imageOnly
    button.imageScaling = .scaleProportionallyUpOrDown
    button.contentTintColor = NSColor(white: 1, alpha: 0.92)
    if let image = NSImage(systemSymbolName: symbol, accessibilityDescription: title) {
        button.image = image.withSymbolConfiguration(.init(pointSize: 16, weight: .semibold))
    }
    return button
}

final class OpacitySlider: NSView {
    var minValue: CGFloat = 0.12
    var maxValue: CGFloat = 1
    var value: CGFloat = 0.5 {
        didSet {
            let clamped = min(max(value, minValue), maxValue)
            if clamped != value {
                value = clamped
                return
            }
            needsDisplay = true
        }
    }
    var tint: NSColor = .white { didSet { needsDisplay = true } }
    var onChange: ((CGFloat) -> Void)?

    override func draw(_ dirtyRect: NSRect) {
        let track = NSRect(x: 7, y: (bounds.height - 8) / 2, width: max(0, bounds.width - 14), height: 8)
        let trackPath = NSBezierPath(roundedRect: track, xRadius: 4, yRadius: 4)
        NSGraphicsContext.saveGraphicsState()
        trackPath.addClip()
        NSColor(white: 0.28, alpha: 1).setFill()
        trackPath.fill()
        let cell: CGFloat = 4
        var row: CGFloat = track.minY
        var flip = false
        while row < track.maxY {
            var col = track.minX
            var on = flip
            while col < track.maxX {
                if on {
                    NSColor(white: 0.55, alpha: 1).setFill()
                    NSBezierPath(rect: NSRect(x: col, y: row, width: cell, height: cell)).fill()
                }
                on.toggle()
                col += cell
            }
            flip.toggle()
            row += cell
        }
        let fade = tint.usingColorSpace(.deviceRGB) ?? tint
        let gradient = NSGradient(colors: [
            fade.withAlphaComponent(0.08),
            fade.withAlphaComponent(1),
        ])
        gradient?.draw(in: track, angle: 0)
        NSGraphicsContext.restoreGraphicsState()

        let t = (value - minValue) / max(maxValue - minValue, 0.001)
        let knobX = track.minX + t * track.width
        let knob = NSRect(x: knobX - 7, y: bounds.midY - 7, width: 14, height: 14)
        NSColor.white.setFill()
        NSBezierPath(ovalIn: knob).fill()
        NSColor(white: 0.15, alpha: 0.85).setStroke()
        let ring = NSBezierPath(ovalIn: knob.insetBy(dx: 0.5, dy: 0.5))
        ring.lineWidth = 1
        ring.stroke()
    }

    override func mouseDown(with event: NSEvent) {
        apply(event)
        while let next = window?.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]) {
            apply(next)
            if next.type == .leftMouseUp { break }
        }
    }

    private func apply(_ event: NSEvent) {
        let x = convert(event.locationInWindow, from: nil).x
        let track = NSRect(x: 7, y: 0, width: max(1, bounds.width - 14), height: 1)
        let t = min(max((x - track.minX) / track.width, 0), 1)
        value = minValue + t * (maxValue - minValue)
        onChange?(value)
    }
}

final class PenToolbar: NSView {
    static let barHeight: CGFloat = 44

    var onStyleChange: ((ScribbleStyle) -> Void)?
    var onUndo: (() -> Void)?
    var onRedo: (() -> Void)?
    var onClear: (() -> Void)?

    private var colorIndex = 0
    private var widthIndex = 1
    private var colorChips: [Chip] = []
    private var widthChips: [Chip] = []
    private let opacitySlider = OpacitySlider()
    private let undoButton = barButton("撤销", symbol: "arrow.uturn.backward")
    private let redoButton = barButton("重做", symbol: "arrow.uturn.forward")
    private let clearButton = NSButton(title: "清除", target: nil, action: nil)

    private static let chipColors: [NSColor] = [
        .systemYellow, .systemRed, .systemBlue, .systemGreen, .black,
    ]
    private static let widths: [CGFloat] = [8, 16, 24]

    var style: ScribbleStyle {
        ScribbleStyle(
            color: Self.chipColors[colorIndex].withAlphaComponent(opacitySlider.value),
            width: Self.widths[widthIndex]
        )
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor(white: 0.12, alpha: 0.88).cgColor
        for (index, color) in Self.chipColors.enumerated() {
            let chip = Chip(kind: .color(color))
            chip.onPick = { [weak self] in self?.pickColor(index) }
            colorChips.append(chip)
            addSubview(chip)
        }
        for (index, width) in Self.widths.enumerated() {
            let chip = Chip(kind: .width(width))
            chip.onPick = { [weak self] in self?.pickWidth(index) }
            widthChips.append(chip)
            addSubview(chip)
        }
        opacitySlider.tint = Self.chipColors[colorIndex]
        opacitySlider.onChange = { [weak self] _ in self?.opacityChanged() }
        addSubview(opacitySlider)
        undoButton.target = self
        undoButton.action = #selector(undoTapped)
        redoButton.target = self
        redoButton.action = #selector(redoTapped)
        addSubview(undoButton)
        addSubview(redoButton)
        clearButton.target = self
        clearButton.action = #selector(clearTapped)
        clearButton.bezelStyle = .rounded
        clearButton.font = .systemFont(ofSize: 11)
        addSubview(clearButton)
        refreshSelection()
        setHistoryEnabled(undo: false, redo: false)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    override func layout() {
        super.layout()
        var x: CGFloat = 10
        let y: CGFloat = 10
        let size: CGFloat = 24
        for chip in colorChips {
            chip.frame = NSRect(x: x, y: y, width: size, height: size)
            x += size + 6
        }
        x += 12
        for chip in widthChips {
            chip.frame = NSRect(x: x, y: y, width: size, height: size)
            x += size + 6
        }
        x += 12
        let historyWidth: CGFloat = 28
        let clearWidth: CGFloat = 52
        let trailing = historyWidth + 6 + historyWidth + 6 + clearWidth + 8
        let sliderWidth = max(48, bounds.width - x - trailing - 8)
        opacitySlider.frame = NSRect(x: x, y: y, width: sliderWidth, height: size)
        var buttonX = bounds.width - trailing
        undoButton.frame = NSRect(x: buttonX, y: 8, width: historyWidth, height: 28)
        buttonX += historyWidth + 6
        redoButton.frame = NSRect(x: buttonX, y: 8, width: historyWidth, height: 28)
        buttonX += historyWidth + 6
        clearButton.frame = NSRect(x: buttonX, y: 8, width: clearWidth, height: 28)
    }

    private func pickColor(_ index: Int) {
        colorIndex = index
        opacitySlider.tint = Self.chipColors[index]
        refreshSelection()
        onStyleChange?(style)
    }

    private func pickWidth(_ index: Int) {
        widthIndex = index
        refreshSelection()
        onStyleChange?(style)
    }

    @objc private func opacityChanged() {
        onStyleChange?(style)
    }

    private func refreshSelection() {
        for (index, chip) in colorChips.enumerated() { chip.selected = index == colorIndex }
        for (index, chip) in widthChips.enumerated() { chip.selected = index == widthIndex }
    }

    func setHistoryEnabled(undo: Bool, redo: Bool) {
        undoButton.isEnabled = undo
        redoButton.isEnabled = redo
    }

    @objc private func undoTapped() { onUndo?() }
    @objc private func redoTapped() { onRedo?() }
    @objc private func clearTapped() { onClear?() }
}

enum EraserShape {
    case circle
    case rectangle
}

struct EraserStyle {
    var shape: EraserShape
    var width: CGFloat

    static let initial = EraserStyle(shape: .circle, width: 64)
}

final class RevealToolbar: NSView {
    static let barHeight: CGFloat = 44

    var onStyleChange: ((EraserStyle) -> Void)?
    var onUndo: (() -> Void)?
    var onRedo: (() -> Void)?
    var onReset: (() -> Void)?

    private var shape: EraserShape = .circle
    private var widthIndex = 1
    private var shapeChips: [Chip] = []
    private var widthChips: [Chip] = []
    private let undoButton = barButton("撤销", symbol: "arrow.uturn.backward")
    private let redoButton = barButton("重做", symbol: "arrow.uturn.forward")
    private let resetButton = NSButton(title: "重置", target: nil, action: nil)
    private static let widths: [CGFloat] = [36, 64, 96]

    var style: EraserStyle {
        EraserStyle(shape: shape, width: Self.widths[widthIndex])
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor(white: 0.12, alpha: 0.88).cgColor
        let circle = Chip(kind: .shapeCircle)
        circle.onPick = { [weak self] in self?.pickShape(.circle) }
        let rect = Chip(kind: .shapeRect)
        rect.onPick = { [weak self] in self?.pickShape(.rectangle) }
        shapeChips = [circle, rect]
        shapeChips.forEach(addSubview)
        for (index, chipSize) in [CGFloat(8), 14, 20].enumerated() {
            let chip = Chip(kind: .width(chipSize))
            chip.onPick = { [weak self] in self?.pickWidth(index) }
            widthChips.append(chip)
            addSubview(chip)
        }
        undoButton.target = self
        undoButton.action = #selector(undoTapped)
        redoButton.target = self
        redoButton.action = #selector(redoTapped)
        addSubview(undoButton)
        addSubview(redoButton)
        resetButton.target = self
        resetButton.action = #selector(resetTapped)
        resetButton.bezelStyle = .rounded
        resetButton.font = .systemFont(ofSize: 11)
        addSubview(resetButton)
        refreshSelection()
        setHistoryEnabled(undo: false, redo: false)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    override func layout() {
        super.layout()
        var x: CGFloat = 10
        let y: CGFloat = 10
        let size: CGFloat = 24
        for chip in shapeChips {
            chip.frame = NSRect(x: x, y: y, width: size, height: size)
            x += size + 6
        }
        x += 12
        for chip in widthChips {
            chip.frame = NSRect(x: x, y: y, width: size, height: size)
            x += size + 6
        }
        let historyWidth: CGFloat = 28
        let resetWidth: CGFloat = 52
        var buttonX = bounds.width - (historyWidth + 6 + historyWidth + 6 + resetWidth + 8)
        buttonX = max(x + 8, buttonX)
        undoButton.frame = NSRect(x: buttonX, y: 8, width: historyWidth, height: 28)
        buttonX += historyWidth + 6
        redoButton.frame = NSRect(x: buttonX, y: 8, width: historyWidth, height: 28)
        buttonX += historyWidth + 6
        resetButton.frame = NSRect(x: buttonX, y: 8, width: resetWidth, height: 28)
    }

    private func pickShape(_ shape: EraserShape) {
        self.shape = shape
        refreshSelection()
        onStyleChange?(style)
    }

    private func pickWidth(_ index: Int) {
        widthIndex = index
        refreshSelection()
        onStyleChange?(style)
    }

    private func refreshSelection() {
        shapeChips[0].selected = shape == .circle
        shapeChips[1].selected = shape == .rectangle
        for (index, chip) in widthChips.enumerated() { chip.selected = index == widthIndex }
    }

    func setHistoryEnabled(undo: Bool, redo: Bool) {
        undoButton.isEnabled = undo
        redoButton.isEnabled = redo
    }

    @objc private func undoTapped() { onUndo?() }
    @objc private func redoTapped() { onRedo?() }
    @objc private func resetTapped() { onReset?() }
}

final class ScribbleOverlay: NSView {
    var style = ScribbleStyle.initial
    var onHistoryChange: (() -> Void)?
    private var strokes: [Stroke] = []
    private var redoStrokes: [Stroke] = []
    private var live: Stroke?

    private struct Stroke {
        var points: [NSPoint]
        var color: NSColor
        var width: CGFloat
    }

    var canUndo: Bool { live == nil && !strokes.isEmpty }
    var canRedo: Bool { live == nil && !redoStrokes.isEmpty }

    override var isOpaque: Bool { false }

    func begin(at point: NSPoint) {
        live = Stroke(points: [point], color: style.color, width: style.width)
        needsDisplay = true
        onHistoryChange?()
    }

    func extend(to point: NSPoint) {
        guard var stroke = live, let last = stroke.points.last else { return }
        if hypot(point.x - last.x, point.y - last.y) < 1.5 { return }
        stroke.points.append(point)
        live = stroke
        needsDisplay = true
    }

    func end() {
        if let live {
            strokes.append(live)
            redoStrokes.removeAll()
        }
        live = nil
        needsDisplay = true
        onHistoryChange?()
    }

    func undo() {
        guard canUndo, let last = strokes.popLast() else { return }
        redoStrokes.append(last)
        needsDisplay = true
        onHistoryChange?()
    }

    func redo() {
        guard canRedo, let last = redoStrokes.popLast() else { return }
        strokes.append(last)
        needsDisplay = true
        onHistoryChange?()
    }

    func clear() {
        strokes.removeAll()
        redoStrokes.removeAll()
        live = nil
        needsDisplay = true
        onHistoryChange?()
    }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func draw(_ dirtyRect: NSRect) {
        for stroke in strokes { draw(stroke) }
        if let live { draw(live) }
    }

    private func draw(_ stroke: Stroke) {
        stroke.color.setStroke()
        path(stroke.points, width: stroke.width).stroke()
    }

    private func path(_ points: [NSPoint], width: CGFloat) -> NSBezierPath {
        let path = NSBezierPath()
        path.lineWidth = width
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        guard let first = points.first else { return path }
        path.move(to: first)
        if points.count == 1 {
            path.line(to: NSPoint(x: first.x + 0.1, y: first.y))
            return path
        }
        for point in points.dropFirst() {
            path.line(to: point)
        }
        return path
    }
}

final class RevealOverlay: NSView {
    var style = EraserStyle.initial
    var onHistoryChange: (() -> Void)?
    private var strokes: [Stroke] = []
    private var redoStrokes: [Stroke] = []
    private var live: Stroke?

    private struct Stroke {
        var points: [NSPoint]
        var width: CGFloat
        var shape: EraserShape
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.isOpaque = false
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    override var isOpaque: Bool { false }

    var canUndo: Bool { live == nil && !strokes.isEmpty }
    var canRedo: Bool { live == nil && !redoStrokes.isEmpty }

    func begin(at point: NSPoint) {
        live = Stroke(points: [point], width: style.width, shape: style.shape)
        needsDisplay = true
        onHistoryChange?()
    }

    func extend(to point: NSPoint) {
        guard var stroke = live, let last = stroke.points.last else { return }
        if hypot(point.x - last.x, point.y - last.y) < 1.5 { return }
        stroke.points.append(point)
        live = stroke
        needsDisplay = true
    }

    func end() {
        if let live {
            strokes.append(live)
            redoStrokes.removeAll()
        }
        live = nil
        needsDisplay = true
        onHistoryChange?()
    }

    func undo() {
        guard canUndo, let last = strokes.popLast() else { return }
        redoStrokes.append(last)
        needsDisplay = true
        onHistoryChange?()
    }

    func redo() {
        guard canRedo, let last = redoStrokes.popLast() else { return }
        strokes.append(last)
        needsDisplay = true
        onHistoryChange?()
    }

    func reset() {
        strokes.removeAll()
        redoStrokes.removeAll()
        live = nil
        needsDisplay = true
        onHistoryChange?()
    }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func draw(_ dirtyRect: NSRect) {
        let titleBand = bounds.height * 0.18
        let fog = NSRect(x: 0, y: 0, width: bounds.width, height: max(0, bounds.height - titleBand))
        NSColor(white: 0.78, alpha: 0.94).setFill()
        fog.fill()
        guard let ctx = NSGraphicsContext.current else { return }
        ctx.saveGraphicsState()
        ctx.compositingOperation = .destinationOut
        NSColor.black.setStroke()
        for stroke in strokes { erase(stroke) }
        if let live { erase(live) }
        ctx.restoreGraphicsState()
    }

    private func erase(_ stroke: Stroke) {
        let path = NSBezierPath()
        path.lineWidth = stroke.width
        if stroke.shape == .circle {
            path.lineCapStyle = .round
            path.lineJoinStyle = .round
        } else {
            path.lineCapStyle = .square
            path.lineJoinStyle = .miter
        }
        guard let first = stroke.points.first else { return }
        path.move(to: first)
        if stroke.points.count == 1 {
            path.line(to: NSPoint(x: first.x + 0.1, y: first.y))
        } else {
            for point in stroke.points.dropFirst() {
                path.line(to: point)
            }
        }
        path.stroke()
    }
}

final class HoverView: NSView {
    var onInside: ((Bool) -> Void)?
    var onSettings: (() -> Void)?
    var onCopyInbox: (() -> Void)?
    var onRequestAccessibility: (() -> Void)?
    var onDragMoved: (() -> Void)?
    var onDragEnded: (() -> Void)?
    var onMarking: ((Bool) -> Void)?
    var onTextDrop: ((String) -> Void)?
    var onTextDragHover: ((Bool) -> Void)?
    var acceptsTextDrop = false {
        didSet {
            if acceptsTextDrop {
                registerForDraggedTypes([.string])
            } else {
                unregisterDraggedTypes()
            }
        }
    }
    var studyMode: StudyMode? {
        didSet { applyStudyChrome() }
    }
    var imageView = NSImageView()
    private let scribble = ScribbleOverlay()
    private let reveal = RevealOverlay()
    private let toolbar = PenToolbar()
    private let revealBar = RevealToolbar()
    private var nearest = false
    private var dragGrab: NSPoint?
    private var dragMonitor: Any?
    private var dragGlobalMonitor: Any?
    private var marking = false
    private var markOutside = false
    private var showsStudyBar: Bool { studyMode != nil }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        imageView.imageScaling = .scaleProportionallyUpOrDown
        imageView.wantsLayer = true
        addSubview(imageView)
        scribble.wantsLayer = false
        addSubview(scribble)
        addSubview(reveal)
        toolbar.isHidden = true
        revealBar.isHidden = true
        scribble.isHidden = true
        reveal.isHidden = true
        toolbar.onStyleChange = { [weak self] style in
            self?.scribble.style = style
        }
        toolbar.onUndo = { [weak self] in self?.undoStudy() }
        toolbar.onRedo = { [weak self] in self?.redoStudy() }
        toolbar.onClear = { [weak self] in self?.clearStudy() }
        scribble.style = toolbar.style
        scribble.onHistoryChange = { [weak self] in self?.syncHistory() }
        revealBar.onStyleChange = { [weak self] style in
            self?.reveal.style = style
        }
        revealBar.onUndo = { [weak self] in self?.undoStudy() }
        revealBar.onRedo = { [weak self] in self?.redoStudy() }
        revealBar.onReset = { [weak self] in self?.reveal.reset() }
        reveal.style = revealBar.style
        reveal.onHistoryChange = { [weak self] in self?.syncHistory() }
        addSubview(toolbar)
        addSubview(revealBar)
    }

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        guard acceptsTextDrop, dropText(from: sender) != nil else { return [] }
        onTextDragHover?(true)
        return .copy
    }

    override func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation {
        guard acceptsTextDrop, dropText(from: sender) != nil else { return [] }
        return .copy
    }

    override func draggingExited(_ sender: NSDraggingInfo?) {
        onTextDragHover?(false)
    }

    override func prepareForDragOperation(_ sender: NSDraggingInfo) -> Bool {
        acceptsTextDrop && dropText(from: sender) != nil
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        guard acceptsTextDrop, let text = dropText(from: sender) else { return false }
        onTextDragHover?(true)
        onTextDrop?(text)
        return true
    }

    override func concludeDragOperation(_ sender: NSDraggingInfo?) {
        // Keep suppress-card until the pointer leaves the pet.
    }

    private func dropText(from sender: NSDraggingInfo) -> String? {
        let board = sender.draggingPasteboard
        let raw: String?
        if let values = board.readObjects(forClasses: [NSString.self], options: nil) as? [String] {
            raw = values.first
        } else {
            raw = board.string(forType: .string)
        }
        let text = raw?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return text.isEmpty ? nil : text
    }

    func applyStudyChrome() {
        toolbar.isHidden = studyMode != .annotate
        revealBar.isHidden = studyMode != .reveal
        scribble.isHidden = studyMode != .annotate
        reveal.isHidden = studyMode != .reveal
        syncHistory()
        needsLayout = true
    }

    func setNearestScaling(_ enabled: Bool) {
        nearest = enabled
        applyScaling()
    }

    private func applyScaling() {
        imageView.layer?.magnificationFilter = nearest ? .nearest : .linear
        imageView.layer?.minificationFilter = nearest ? .nearest : .linear
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    override func layout() {
        super.layout()
        let bar = showsStudyBar ? PenToolbar.barHeight : 0
        let imageFrame = NSRect(
            x: 0,
            y: bar,
            width: bounds.width,
            height: max(0, bounds.height - bar)
        )
        imageView.frame = imageFrame
        scribble.frame = imageFrame
        reveal.frame = imageFrame
        toolbar.frame = NSRect(x: 0, y: 0, width: bounds.width, height: bar)
        revealBar.frame = NSRect(x: 0, y: 0, width: bounds.width, height: bar)
        applyScaling()
    }

    func clearStudy() {
        scribble.clear()
        reveal.reset()
    }

    func undoStudy() {
        if studyMode == .reveal { reveal.undo() } else { scribble.undo() }
    }

    func redoStudy() {
        if studyMode == .reveal { reveal.redo() } else { scribble.redo() }
    }

    private func syncHistory() {
        if studyMode == .reveal {
            revealBar.setHistoryEnabled(undo: reveal.canUndo, redo: reveal.canRedo)
        } else {
            toolbar.setHistoryEnabled(undo: scribble.canUndo, redo: scribble.canRedo)
        }
    }

    static func extraHeight(for _: StudyMode) -> CGFloat {
        PenToolbar.barHeight
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(
            NSTrackingArea(
                rect: bounds,
                options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                owner: self,
                userInfo: nil
            )
        )
    }

    override func mouseEntered(with event: NSEvent) { onInside?(true) }
    override func mouseExited(with event: NSEvent) { onInside?(false) }

    override func mouseDown(with event: NSEvent) {
        let local = convert(event.locationInWindow, from: nil)
        if showsStudyBar, local.y < PenToolbar.barHeight {
            beginWindowDrag()
            return
        }
        if studyMode != nil, !event.modifierFlags.contains(.option) {
            beginMark()
            return
        }
        beginWindowDrag()
    }

    override func mouseUp(with event: NSEvent) {
        if marking {
            finishMark()
        } else {
            finishDrag()
        }
    }

    private func beginWindowDrag() {
        guard let window else { return }
        let loc = NSEvent.mouseLocation
        dragGrab = NSPoint(x: loc.x - window.frame.minX, y: loc.y - window.frame.minY)
        startMonitors { [weak self] ev in
            self?.handleDrag(ev)
        }
    }

    private func beginMark() {
        marking = true
        markOutside = false
        onMarking?(true)
        if let point = pointInOverlay() {
            startStroke(at: point)
        } else {
            markOutside = true
        }
        startMonitors { [weak self] ev in
            self?.handleMark(ev)
        }
    }

    private func startMonitors(handler: @escaping (NSEvent) -> Void) {
        stopDragMonitors()
        dragMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDragged, .leftMouseUp]) { ev in
            handler(ev)
            return ev.type == .leftMouseUp ? ev : nil
        }
        dragGlobalMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDragged, .leftMouseUp]) { ev in
            handler(ev)
        }
    }

    private func handleDrag(_ event: NSEvent) {
        if event.type == .leftMouseDragged {
            guard let window, let grab = dragGrab else { return }
            let loc = NSEvent.mouseLocation
            let size = window.frame.size
            var origin = NSPoint(x: loc.x - grab.x, y: loc.y - grab.y)
            if let dest = screenAt(loc),
               bestScreen(for: NSRect(origin: origin, size: size)) !== dest {
                let visible = dest.visibleFrame
                origin.x = min(max(origin.x, visible.minX), max(visible.minX, visible.maxX - size.width))
                origin.y = min(max(origin.y, visible.minY), max(visible.minY, visible.maxY - size.height))
            }
            window.setFrame(NSRect(origin: origin, size: size), display: true)
            onDragMoved?()
            dragGrab = NSPoint(x: loc.x - window.frame.minX, y: loc.y - window.frame.minY)
        } else if event.type == .leftMouseUp {
            finishDrag()
        }
    }

    private func handleMark(_ event: NSEvent) {
        if event.type == .leftMouseDragged {
            if let point = pointInOverlay() {
                if markOutside {
                    markOutside = false
                    startStroke(at: point)
                } else {
                    extendStroke(to: point)
                }
            } else if !markOutside {
                markOutside = true
                endStroke()
            }
        } else if event.type == .leftMouseUp {
            finishMark()
        }
    }

    private func startStroke(at point: NSPoint) {
        if studyMode == .reveal {
            reveal.begin(at: point)
        } else {
            scribble.begin(at: point)
        }
    }

    private func extendStroke(to point: NSPoint) {
        if studyMode == .reveal {
            reveal.extend(to: point)
        } else {
            scribble.extend(to: point)
        }
    }

    private func endStroke() {
        if studyMode == .reveal {
            reveal.end()
        } else {
            scribble.end()
        }
    }

    private func finishMark() {
        guard marking else { return }
        endStroke()
        marking = false
        markOutside = false
        stopDragMonitors()
        onMarking?(false)
    }

    private func pointInOverlay() -> NSPoint? {
        guard let window else { return nil }
        let overlay: NSView = studyMode == .reveal ? reveal : scribble
        let win = window.convertPoint(fromScreen: NSEvent.mouseLocation)
        let point = overlay.convert(win, from: nil)
        guard overlay.bounds.contains(point) else { return nil }
        return point
    }

    private func finishDrag() {
        guard dragMonitor != nil || dragGlobalMonitor != nil || dragGrab != nil else { return }
        stopDragMonitors()
        dragGrab = nil
        onDragEnded?()
    }

    private func stopDragMonitors() {
        if let dragMonitor {
            NSEvent.removeMonitor(dragMonitor)
            self.dragMonitor = nil
        }
        if let dragGlobalMonitor {
            NSEvent.removeMonitor(dragGlobalMonitor)
            self.dragGlobalMonitor = nil
        }
    }

    override func rightMouseDown(with event: NSEvent) {
        let menu = NSMenu()
        if studyMode != nil {
            let undo = NSMenuItem(title: "撤销", action: #selector(undoStudyMenu), keyEquivalent: "z")
            undo.target = self
            undo.isEnabled = studyMode == .reveal ? reveal.canUndo : scribble.canUndo
            menu.addItem(undo)
            let redo = NSMenuItem(title: "重做", action: #selector(redoStudyMenu), keyEquivalent: "z")
            redo.keyEquivalentModifierMask = [.command, .shift]
            redo.target = self
            redo.isEnabled = studyMode == .reveal ? reveal.canRedo : scribble.canRedo
            menu.addItem(redo)
            menu.addItem(.separator())
        }
        if studyMode == .annotate {
            let clear = NSMenuItem(title: "清除标注", action: #selector(clearStudyMenu), keyEquivalent: "")
            clear.target = self
            menu.addItem(clear)
            menu.addItem(.separator())
        } else if studyMode == .reveal {
            let reset = NSMenuItem(title: "重置遮罩", action: #selector(clearStudyMenu), keyEquivalent: "")
            reset.target = self
            menu.addItem(reset)
            menu.addItem(.separator())
        }
        let settings = NSMenuItem(title: "设置…", action: #selector(openSettings), keyEquivalent: ",")
        settings.target = self
        menu.addItem(settings)
        let copyInbox = NSMenuItem(title: "复制收件箱地址", action: #selector(copyInboxURL), keyEquivalent: "")
        copyInbox.target = self
        menu.addItem(copyInbox)
        let ax = NSMenuItem(title: "授予辅助功能权限…", action: #selector(requestAccessibilityMenu), keyEquivalent: "")
        ax.target = self
        menu.addItem(ax)
        menu.addItem(.separator())
        menu.addItem(
            NSMenuItem(
                title: "退出",
                action: #selector(NSApplication.terminate(_:)),
                keyEquivalent: "q"
            )
        )
        NSMenu.popUpContextMenu(menu, with: event, for: self)
    }

    @objc private func openSettings() { onSettings?() }
    @objc private func copyInboxURL() { onCopyInbox?() }
    @objc private func requestAccessibilityMenu() { onRequestAccessibility?() }
    @objc private func undoStudyMenu() { undoStudy() }
    @objc private func redoStudyMenu() { redoStudy() }
    @objc private func clearStudyMenu() { clearStudy() }

    override func hitTest(_ point: NSPoint) -> NSView? {
        if showsStudyBar, point.y < PenToolbar.barHeight {
            return super.hitTest(point)
        }
        guard let hit = super.hitTest(point), let image = imageView.image else {
            return super.hitTest(point)
        }
        let frame = imageView.frame
        guard frame.width > 0, frame.height > 0, frame.contains(point) else { return hit }
        let local = NSPoint(x: point.x - frame.minX, y: point.y - frame.minY)
        var rect = CGRect(origin: .zero, size: image.size)
        guard let cg = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
            return hit
        }
        let px = min(max(Int(local.x / frame.width * CGFloat(cg.width)), 0), cg.width - 1)
        let py = min(max(Int((1 - local.y / frame.height) * CGFloat(cg.height)), 0), cg.height - 1)
        guard let provider = cg.dataProvider, let data = provider.data else { return hit }
        let ptr = CFDataGetBytePtr(data)
        let info = cg.alphaInfo
        let spp = max(cg.bitsPerPixel / 8, 1)
        let idx = (py * cg.bytesPerRow) + (px * spp)
        let alpha: UInt8
        switch info {
        case .premultipliedLast, .last:
            alpha = ptr?[idx + 3] ?? 255
        case .premultipliedFirst, .first:
            alpha = ptr?[idx] ?? 255
        default:
            return hit
        }
        return alpha < 16 ? nil : hit
    }
}

final class ClearPanel: NSPanel {
    override var canBecomeKey: Bool { true }

    override func constrainFrameRect(_ frameRect: NSRect, to screen: NSScreen?) -> NSRect {
        frameRect
    }
}

final class SettingsController: NSObject {
    let window: NSWindow
    private let zoomSlider: NSSlider
    private let zoomLabel: NSTextField
    private let minutesField: NSTextField
    var onPreviewZoom: ((Double) -> Void)?
    var onApply: ((Double, Int, Double, Int, Double, Double, StudyMode, String, Double, Double, Double) -> Void)?
    private let cardMaxField: NSTextField
    private let repeatCountField: NSTextField
    private let repeatWindowField: NSTextField
    private let hoverExitField: NSTextField
    private let studyPopup: NSPopUpButton
    private let promptField: NSTextField
    private let bubbleWidthField: NSTextField
    private let bubbleHeightField: NSTextField
    private let fontSizeField: NSTextField

    init(
        zoom: Double,
        cardMax: Int,
        minutes: Double,
        repeatAfter: Int,
        repeatWindow: Double,
        hoverExit: Double,
        studyMode: StudyMode,
        explainPrompt: String,
        bubbleWidth: Double,
        bubbleHeight: Double,
        fontSize: Double
    ) {
        zoomSlider = NSSlider(value: zoom, minValue: 0.5, maxValue: 2.5, target: nil, action: nil)
        zoomSlider.isContinuous = true
        zoomLabel = NSTextField(labelWithString: "")
        cardMaxField = NSTextField(string: "\(cardMax)")
        minutesField = NSTextField(string: String(format: "%g", minutes))
        repeatCountField = NSTextField(string: "\(repeatAfter)")
        repeatWindowField = NSTextField(string: String(format: "%g", repeatWindow))
        hoverExitField = NSTextField(string: String(format: "%g", hoverExit))
        studyPopup = NSPopUpButton(frame: .zero, pullsDown: false)
        promptField = NSTextField(string: explainPrompt)
        bubbleWidthField = NSTextField(string: String(format: "%g", bubbleWidth))
        bubbleHeightField = NSTextField(string: String(format: "%g", bubbleHeight))
        fontSizeField = NSTextField(string: String(format: "%g", fontSize))
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 380, height: 620),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        super.init()
        window.title = "DeskPet 设置"
        window.level = .floating
        window.isReleasedWhenClosed = false
        studyPopup.addItems(withTitles: ["标注（划重点）", "揭开（擦开遮罩）"])
        applyStudyMode(studyMode)

        let content = NSView(frame: NSRect(x: 0, y: 0, width: 380, height: 620))
        func label(_ text: String, y: CGFloat) -> NSTextField {
            let field = NSTextField(labelWithString: text)
            field.frame = NSRect(x: 20, y: y, width: 340, height: 18)
            return field
        }
        content.addSubview(label("缩放", y: 580))
        zoomSlider.frame = NSRect(x: 20, y: 552, width: 260, height: 24)
        zoomSlider.target = self
        zoomSlider.action = #selector(zoomChanged)
        zoomLabel.frame = NSRect(x: 290, y: 554, width: 70, height: 20)
        content.addSubview(zoomSlider)
        content.addSubview(zoomLabel)
        content.addSubview(label("卡片短边上限（像素）", y: 518))
        cardMaxField.frame = NSRect(x: 20, y: 490, width: 120, height: 24)
        cardMaxField.placeholderString = "600"
        content.addSubview(cardMaxField)
        content.addSubview(label("长时间无互动后切换表情（分钟，0 为关闭）", y: 456))
        minutesField.frame = NSRect(x: 20, y: 428, width: 120, height: 24)
        minutesField.placeholderString = "10"
        content.addSubview(minutesField)
        content.addSubview(label("短期内多次悬停（次数 / 统计窗口分钟，0 关闭）", y: 394))
        repeatCountField.frame = NSRect(x: 20, y: 366, width: 70, height: 24)
        repeatCountField.placeholderString = "5"
        repeatWindowField.frame = NSRect(x: 100, y: 366, width: 70, height: 24)
        repeatWindowField.placeholderString = "1"
        content.addSubview(repeatCountField)
        content.addSubview(repeatWindowField)
        content.addSubview(label("移开后多久才退出悬停（秒）", y: 332))
        hoverExitField.frame = NSRect(x: 20, y: 304, width: 120, height: 24)
        hoverExitField.placeholderString = "1"
        content.addSubview(hoverExitField)
        content.addSubview(label("学习方式", y: 270))
        studyPopup.frame = NSRect(x: 20, y: 242, width: 240, height: 26)
        content.addSubview(studyPopup)
        content.addSubview(label("解释提示词（{简写} 会被替换）", y: 208))
        promptField.frame = NSRect(x: 20, y: 180, width: 340, height: 24)
        promptField.placeholderString = "三段式：一句话解释 / 举例 / 总结（段间空行）"
        content.addSubview(promptField)
        content.addSubview(label("解释气泡（宽 / 高 / 字号）", y: 146))
        bubbleWidthField.frame = NSRect(x: 20, y: 118, width: 70, height: 24)
        bubbleWidthField.placeholderString = "320"
        bubbleHeightField.frame = NSRect(x: 100, y: 118, width: 70, height: 24)
        bubbleHeightField.placeholderString = "220"
        fontSizeField.frame = NSRect(x: 180, y: 118, width: 70, height: 24)
        fontSizeField.placeholderString = "13"
        content.addSubview(bubbleWidthField)
        content.addSubview(bubbleHeightField)
        content.addSubview(fontSizeField)
        let hint = NSTextField(labelWithString: "拖到屏幕边缘会贴边探头；API Key 仍在 local.env")
        hint.textColor = .secondaryLabelColor
        hint.frame = NSRect(x: 20, y: 84, width: 340, height: 18)
        content.addSubview(hint)
        let save = NSButton(title: "保存", target: self, action: #selector(saveTapped))
        save.bezelStyle = .rounded
        save.frame = NSRect(x: 270, y: 40, width: 90, height: 28)
        content.addSubview(save)
        window.contentView = content
        window.delegate = self
        refreshZoomLabel()
    }

    func show(
        zoom: Double,
        cardMax: Int,
        minutes: Double,
        repeatAfter: Int,
        repeatWindow: Double,
        hoverExit: Double,
        studyMode: StudyMode,
        explainPrompt: String,
        bubbleWidth: Double,
        bubbleHeight: Double,
        fontSize: Double,
        on screen: NSScreen?
    ) {
        zoomSlider.doubleValue = zoom
        cardMaxField.stringValue = "\(cardMax)"
        minutesField.stringValue = String(format: "%g", minutes)
        repeatCountField.stringValue = "\(repeatAfter)"
        repeatWindowField.stringValue = String(format: "%g", repeatWindow)
        hoverExitField.stringValue = String(format: "%g", hoverExit)
        applyStudyMode(studyMode)
        promptField.stringValue = explainPrompt
        bubbleWidthField.stringValue = String(format: "%g", bubbleWidth)
        bubbleHeightField.stringValue = String(format: "%g", bubbleHeight)
        fontSizeField.stringValue = String(format: "%g", fontSize)
        refreshZoomLabel()
        if let visible = screen?.visibleFrame ?? NSScreen.main?.visibleFrame {
            let size = window.frame.size
            window.setFrameOrigin(NSPoint(
                x: visible.midX - size.width / 2,
                y: visible.midY - size.height / 2
            ))
        } else {
            window.center()
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func zoomChanged() {
        refreshZoomLabel()
        onPreviewZoom?(zoomSlider.doubleValue)
    }

    @objc private func saveTapped() {
        persist()
        window.close()
    }

    private func persist() {
        onApply?(
            zoomSlider.doubleValue,
            parsedCardMax(),
            parsedMinutes(),
            parsedRepeatAfter(),
            parsedRepeatWindow(),
            parsedHoverExit(),
            parsedStudyMode(),
            parsedPrompt(),
            parsedBubbleWidth(),
            parsedBubbleHeight(),
            parsedFontSize()
        )
    }

    private func parsedCardMax() -> Int {
        max(1, Int(cardMaxField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 600)
    }

    private func parsedMinutes() -> Double {
        max(0, Double(minutesField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 10)
    }

    private func parsedRepeatAfter() -> Int {
        max(0, Int(repeatCountField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 5)
    }

    private func parsedRepeatWindow() -> Double {
        max(0, Double(repeatWindowField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 1)
    }

    private func parsedHoverExit() -> Double {
        max(0, Double(hoverExitField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 1)
    }

    private func parsedStudyMode() -> StudyMode {
        studyPopup.indexOfSelectedItem == 1 ? .reveal : .annotate
    }

    private func parsedPrompt() -> String {
        let text = promptField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? ExplainConfig.defaults.promptTemplate : text
    }

    private func parsedBubbleWidth() -> Double {
        max(180, Double(bubbleWidthField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 320)
    }

    private func parsedBubbleHeight() -> Double {
        max(120, Double(bubbleHeightField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 220)
    }

    private func parsedFontSize() -> Double {
        min(28, max(10, Double(fontSizeField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 13))
    }

    private func applyStudyMode(_ mode: StudyMode) {
        studyPopup.selectItem(at: mode == .reveal ? 1 : 0)
    }

    private func refreshZoomLabel() {
        zoomLabel.stringValue = String(format: "%.0f%%", zoomSlider.doubleValue * 100)
    }
}

extension SettingsController: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        persist()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var petPanel: ClearPanel!
    private var cardPanel: ClearPanel!
    private var bubblePanel: ClearPanel!
    private var petView: HoverView!
    private var cardView: HoverView!
    private var bubbleView: SpeechBubbleView!
    private var pack: CharacterPack!
    private var peekLeft: NSImage!
    private var peekHoverLeft: NSImage!
    private var peekAwayLeft: NSImage!
    private var peekInboxLeft: NSImage!
    private var peekRepeatHoverLeft: NSImage!
    private var peekRevealLeft: NSImage!
    private var inboxQueue: InboxQueue!
    private var repeatHoverClock = RepeatHoverClock()
    private var inboxServer: InboxServer?
    private var sessionInbox: URL?
    private var cards: [URL] = []
    private var lastCard: URL?
    private var petInside = false
    private var cardInside = false
    private var cardMarking = false
    private var hoverSessionInside = false
    private var hoverSessionLeaveWork: DispatchWorkItem?
    private let hoverSessionGap: TimeInterval = 0.18
    private var hideWork: DispatchWorkItem?
    private var showing = false
    private var awayClock = AwayClock()
    private var docked: DockedEdge = .none
    private var dragging = false
    private var tick: Timer?
    private var config: Config!
    private var configURL: URL!
    private var settings: SettingsController?
    private var cardImageSize = NSSize.zero
    private let explainClient = ExplainClient()
    private var explainTerm = ""
    private var bubbleVisible = false
    /// Text-drag / drop should explain only — never reveal the study card.
    private var suppressCardReveal = false
    private let selectionWatcher = SelectionWatcher()
    private let selectionChip = SelectionChipPanel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let root = deskpetRoot()
        configURL = root.appendingPathComponent("config.json")
        config = loadJSON(Config.self, from: configURL)
        let packDir = root.appendingPathComponent("characters").appendingPathComponent(config.character)
        let spec = loadJSON(CharacterSpec.self, from: packDir.appendingPathComponent("character.json"))
        let idle = requireImage(packDir.appendingPathComponent(spec.idle))
        let hover = requireImage(packDir.appendingPathComponent(spec.hover))
        let peek = spec.peek.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? idle
        let peekHover = spec.peekHover.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? hover
        pack = CharacterPack(
            id: spec.id ?? config.character,
            name: spec.name ?? config.character,
            idle: idle,
            hover: hover,
            peek: peek,
            peekHover: peekHover,
            peekAway: spec.peekAway.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? idle,
            inbox: spec.inbox.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? idle,
            peekInbox: spec.peekInbox.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? peek,
            repeatHover: spec.repeatHover.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? idle,
            peekRepeatHover: spec.peekRepeatHover.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? peek,
            reveal: spec.reveal.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? hover,
            peekReveal: spec.peekReveal.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? peekHover,
            away: spec.away.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? idle,
            size: CGFloat(spec.size ?? 200),
            nearest: spec.scale == "nearest",
            peekScale: CGFloat(spec.peekScale ?? 0.5)
        )
        peekLeft = flippedHorizontally(pack.peek)
        peekHoverLeft = flippedHorizontally(pack.peekHover)
        peekAwayLeft = flippedHorizontally(pack.peekAway)
        peekInboxLeft = flippedHorizontally(pack.peekInbox)
        peekRepeatHoverLeft = flippedHorizontally(pack.peekRepeatHover)
        peekRevealLeft = flippedHorizontally(pack.peekReveal)
        inboxQueue = InboxQueue(directory: root.appendingPathComponent("inbox", isDirectory: true))
        inboxQueue.loadFromDisk()
        startInboxServer()
        cards = listCanonicalCards(fromPatterns: config.cardsDir, relativeTo: root)
        if cards.isEmpty {
            fputs("DeskPet: no cards from cards_dir\n", stderr)
        }

        petView = HoverView(frame: .zero)
        petView.setNearestScaling(pack.nearest)
        petView.acceptsTextDrop = true
        petView.onInside = { [weak self] inside in
            self?.petInside = inside
            self?.syncHover()
        }
        petView.onSettings = { [weak self] in self?.openSettings() }
        petView.onCopyInbox = { [weak self] in self?.copyInboxURL() }
        petView.onRequestAccessibility = { [weak self] in self?.requestAccessibility() }
        petView.onDragMoved = { [weak self] in self?.updateDockWhileDragging() }
        petView.onDragEnded = { [weak self] in self?.endDrag() }
        petView.onTextDragHover = { [weak self] active in
            self?.handleTextDragHover(active)
        }
        petView.onTextDrop = { [weak self] text in self?.explainDroppedText(text) }

        cardView = HoverView(frame: .zero)
        cardView.studyMode = config.studyMode
        cardView.onInside = { [weak self] inside in
            self?.cardInside = inside
            self?.syncHover()
        }
        cardView.onMarking = { [weak self] marking in
            self?.cardMarking = marking
            self?.syncHover()
        }
        cardView.onSettings = { [weak self] in self?.openSettings() }
        cardView.onCopyInbox = { [weak self] in self?.copyInboxURL() }
        cardView.onRequestAccessibility = { [weak self] in self?.requestAccessibility() }

        bubbleView = SpeechBubbleView(frame: .zero)
        bubbleView.applyStyle(config.bubbleStyle)
        bubbleView.onDismiss = { [weak self] in self?.hideBubble() }

        petPanel = makePanel()
        petPanel.contentView = petView
        cardPanel = makePanel()
        cardPanel.contentView = cardView
        cardPanel.orderOut(nil)
        bubblePanel = makePanel()
        bubblePanel.contentView = bubbleView
        bubblePanel.hasShadow = true
        bubblePanel.orderOut(nil)

        applyPose()
        if let screen = NSScreen.main?.visibleFrame {
            let size = petPanel.frame.size
            petPanel.setFrameOrigin(NSPoint(
                x: screen.maxX - size.width - 24,
                y: screen.minY + 24
            ))
        }
        petPanel.orderFrontRegardless()
        tick = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            self?.checkClocks()
        }
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.snapIfNeeded()
        }
        startSelectionChip()
    }

    private func startSelectionChip() {
        selectionChip.onTap = { [weak self] text in
            self?.explainDroppedText(text)
        }
        selectionWatcher.shouldIgnorePoint = { [weak self] point in
            self?.isPointOverDeskPet(point) ?? false
        }
        selectionWatcher.onClickBegan = { [weak self] in
            self?.selectionChip.hide()
        }
        selectionWatcher.onSelection = { [weak self] text, point in
            self?.selectionChip.show(text: text, near: point)
        }
        selectionWatcher.start()
        if !AccessibilityAuth.isTrusted {
            fputs("DeskPet: Accessibility not granted — selection chip disabled. Right-click pet → 授予辅助功能权限…\n", stderr)
        }
    }

    private func isPointOverDeskPet(_ point: NSPoint) -> Bool {
        for window in NSApp.windows where window.isVisible {
            if window.frame.contains(point) { return true }
        }
        return false
    }

    private func requestAccessibility() {
        if AccessibilityAuth.isTrusted {
            fputs("DeskPet: Accessibility already granted\n", stderr)
            return
        }
        _ = AccessibilityAuth.promptIfNeeded()
        AccessibilityAuth.openSettings()
    }

    private func petScreen() -> NSScreen? {
        bestScreen(for: petPanel.frame) ?? screenAt(NSEvent.mouseLocation) ?? NSScreen.main
    }

    private func petVisibleFrame() -> NSRect? {
        petScreen()?.visibleFrame
    }

    private func makePanel() -> ClearPanel {
        let panel = ClearPanel(
            contentRect: NSRect(x: 0, y: 0, width: 100, height: 100),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.becomesKeyOnlyIfNeeded = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.hidesOnDeactivate = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.isMovableByWindowBackground = false
        return panel
    }

    private func isRepeatHoverNow() -> Bool {
        repeatHoverClock.isActive(
            afterHovers: config.repeatHoverAfter,
            windowMinutes: config.repeatHoverWindowMinutes
        )
    }

    private func poseImage() -> NSImage {
        let sidePeek = docked == .left || docked == .right
        let hasMail = !inboxQueue.isEmpty
        let repeating = isRepeatHoverNow()
        if sidePeek { return peekImage(hasMail: hasMail, repeating: repeating) }
        if showing {
            if config.studyMode == .reveal { return pack.reveal }
            if repeating { return pack.repeatHover }
            return pack.hover
        }
        if hasMail { return pack.inbox }
        if repeating { return pack.repeatHover }
        if awayClock.isAway { return pack.away }
        return pack.idle
    }

    private func peekImage(hasMail: Bool, repeating: Bool) -> NSImage {
        if showing {
            if config.studyMode == .reveal {
                return docked == .left ? peekRevealLeft : pack.peekReveal
            }
            if repeating {
                return docked == .left ? peekRepeatHoverLeft : pack.peekRepeatHover
            }
            return docked == .left ? peekHoverLeft : pack.peekHover
        }
        if hasMail {
            return docked == .left ? peekInboxLeft : pack.peekInbox
        }
        if repeating {
            return docked == .left ? peekRepeatHoverLeft : pack.peekRepeatHover
        }
        if awayClock.isAway {
            return docked == .left ? peekAwayLeft : pack.peekAway
        }
        return docked == .left ? peekLeft : pack.peek
    }

    private func startInboxServer() {
        let port = config.inboxPort
        guard port > 0 else { return }
        let server = InboxServer()
        server.enqueue = { [weak self] data in
            guard let self else { return .invalidImage }
            var result = InboxEnqueueResult.invalidImage
            DispatchQueue.main.sync {
                result = self.inboxQueue.enqueue(data)
                if case .accepted = result {
                    self.applyPose()
                }
            }
            return result
        }
        server.count = { [weak self] in
            guard let self else { return 0 }
            if Thread.isMainThread { return self.inboxQueue.count }
            var n = 0
            DispatchQueue.main.sync { n = self.inboxQueue.count }
            return n
        }
        server.start(port: port)
        inboxServer = server
    }

    private func displaySize(for image: NSImage, peeking: Bool) -> NSSize {
        let zoom = CGFloat(max(config.zoom, 0.3))
        var unit = pack.size * zoom / max(pack.idle.size.width, 1)
        if peeking {
            unit *= pack.peekScale
        }
        return NSSize(width: image.size.width * unit, height: image.size.height * unit)
    }

    private func applyPose() {
        let mouse = NSEvent.mouseLocation
        let old = petPanel.frame
        let relX = old.width > 1 ? (mouse.x - old.minX) / old.width : 0.5
        let relY = old.height > 1 ? (mouse.y - old.minY) / old.height : 0.5
        let image = poseImage()
        let peeking = docked == .left || docked == .right
        petView.imageView.image = image
        let newSize = displaySize(for: image, peeking: peeking)
        var frame = old
        if dragging {
            frame.size = newSize
            frame.origin = NSPoint(
                x: mouse.x - relX * newSize.width,
                y: mouse.y - relY * newSize.height
            )
        } else {
            switch docked {
            case .right:
                frame.origin.x += old.size.width - newSize.width
            case .top:
                frame.origin.y += old.size.height - newSize.height
            default:
                break
            }
            frame.size = newSize
        }
        petPanel.setFrame(frame, display: true)
        petView.frame = NSRect(origin: .zero, size: newSize)
        petPanel.invalidateShadow()
        if showing {
            positionCard()
        }
        if bubbleVisible {
            positionBubble()
        }
    }

    private func dockedEdge(for frame: NSRect, on screen: NSScreen) -> DockedEdge {
        let visible = screen.visibleFrame
        let pad: CGFloat = 56
        let candidates: [(DockedEdge, Bool)] = [
            (.right, frame.maxX > visible.maxX - pad),
            (.left, frame.minX < visible.minX + pad),
            (.top, frame.maxY > visible.maxY - pad),
            (.bottom, frame.minY < visible.minY + pad),
        ]
        for (edge, near) in candidates where near {
            if !isSharedEdge(edge, of: screen, along: frame) {
                return edge
            }
        }
        return .none
    }

    private func updateDockWhileDragging() {
        dragging = true
        guard let screen = petScreen() else { return }
        let next = dockedEdge(for: petPanel.frame, on: screen)
        if next != docked {
            docked = next
            applyPose()
        }
    }

    private func endDrag() {
        dragging = false
        snapIfNeeded()
    }

    private func snapIfNeeded() {
        guard let screen = petScreen() else { return }
        docked = dockedEdge(for: petPanel.frame, on: screen)
        applyPose()
        var origin = petPanel.frame.origin
        let size = petPanel.frame.size
        let visible = screen.visibleFrame
        switch docked {
        case .right: origin.x = visible.maxX - size.width
        case .left: origin.x = visible.minX
        case .top: origin.y = visible.maxY - size.height
        case .bottom: origin.y = visible.minY
        case .none: break
        }
        origin.x = min(max(origin.x, visible.minX), visible.maxX - size.width)
        origin.y = min(max(origin.y, visible.minY), visible.maxY - size.height)
        petPanel.setFrameOrigin(origin)
        if showing {
            positionCard()
        }
        if bubbleVisible {
            positionBubble()
        }
    }

    private func resetInteract() {
        let wasAway = awayClock.isAway
        awayClock.markInteracted()
        if wasAway, !showing { applyPose() }
    }

    private func checkClocks() {
        let wasAway = awayClock.isAway
        let wasRepeating = isRepeatHoverNow()
        awayClock.tick(
            afterMinutes: config.awayAfterMinutes,
            paused: petInside || showing
        )
        repeatHoverClock.tick(windowMinutes: config.repeatHoverWindowMinutes)
        if awayClock.isAway != wasAway || isRepeatHoverNow() != wasRepeating {
            applyPose()
        }
    }

    private func syncHover() {
        hideWork?.cancel()
        hoverSessionLeaveWork?.cancel()
        let inside = petInside || cardInside || cardMarking
        if inside {
            awayClock.hoverChanged(inside: true)
            let repeatingBefore = isRepeatHoverNow()
            if !hoverSessionInside {
                hoverSessionInside = true
                repeatHoverClock.hoverBegan()
            }
            if !showing {
                showing = true
                applyPose()
                if !suppressCardReveal {
                    showCard()
                }
            } else if isRepeatHoverNow() != repeatingBefore {
                applyPose()
            }
            return
        }
        let leaveSession = DispatchWorkItem { [weak self] in
            self?.hoverSessionInside = false
        }
        hoverSessionLeaveWork = leaveSession
        DispatchQueue.main.asyncAfter(deadline: .now() + hoverSessionGap, execute: leaveSession)
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.petInside, !self.cardInside, !self.cardMarking else { return }
            self.awayClock.hoverChanged(inside: false)
            self.showing = false
            self.hoverSessionInside = false
            self.suppressCardReveal = false
            self.cardView.clearStudy()
            self.cardPanel.orderOut(nil)
            if let url = self.sessionInbox {
                self.inboxQueue.dequeue(url)
                self.sessionInbox = nil
            }
            self.applyPose()
        }
        hideWork = work
        DispatchQueue.main.asyncAfter(
            deadline: .now() + max(0, config.hoverExitSeconds),
            execute: work
        )
    }

    private func showCard() {
        guard let image = inboxCard() ?? localCard() else { return }
        layoutCard(image)
    }

    private func layoutCard(_ image: NSImage) {
        let screen = petVisibleFrame()
        let extra = HoverView.extraHeight(for: config.studyMode)
        let reserved = petPanel.frame.width + 24
        let maxShort = CGFloat(max(config.cardMaxWidth, 1))
        let maxWidth = max((screen?.width ?? 1200) - reserved, 1)
        let maxHeight = max((screen?.height ?? 800) - extra - 16, 1)
        let size = fitted(image, maxShortSide: maxShort, maxWidth: maxWidth, maxHeight: maxHeight)
        cardImageSize = size
        let panelSize = NSSize(width: size.width, height: size.height + extra)
        cardView.clearStudy()
        cardView.imageView.image = image
        cardPanel.setContentSize(panelSize)
        cardView.frame = NSRect(origin: .zero, size: panelSize)
        positionCard()
        cardPanel.orderFrontRegardless()
    }

    private func positionCard() {
        let size = cardPanel.frame.size
        guard size.width > 0 else { return }
        let petFrame = petPanel.frame
        var origin = NSPoint(x: petFrame.minX - size.width - 12, y: petFrame.midY - size.height / 2)
        if let screen = petVisibleFrame() {
            if origin.x < screen.minX {
                origin.x = petFrame.maxX + 12
            }
            origin.y = min(max(origin.y, screen.minY + 8), screen.maxY - size.height - 8)
        }
        cardPanel.setFrameOrigin(origin)
    }

    private func handleTextDragHover(_ active: Bool) {
        if active {
            suppressCardReveal = true
            hideStudyCardOnly()
            return
        }
        // Drag left without a drop: restore normal card hover if no bubble is up.
        if !bubbleVisible {
            suppressCardReveal = false
            syncHover()
        }
    }

    private func hideStudyCardOnly() {
        cardView.clearStudy()
        cardPanel.orderOut(nil)
    }

    private func explainDroppedText(_ text: String) {
        let term = String(text.prefix(200))
        explainTerm = term
        suppressCardReveal = true
        hideStudyCardOnly()
        resetInteract()
        showBubble(term: term, body: "正在解释…", loading: true)
        explainClient.explain(term: term, config: config.explain) { [weak self] event in
            guard let self else { return }
            guard self.explainTerm == term else { return }
            switch event {
            case .partial(let reply):
                guard !reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
                self.updateBubble(term: term, body: reply, loading: false, streaming: true)
            case .success(let reply):
                self.updateBubble(term: term, body: reply, loading: false, streaming: false)
            case .failure(let error):
                let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                self.updateBubble(term: term, body: message, loading: false, streaming: false)
            }
        }
    }

    private func showBubble(term: String, body: String, loading: Bool) {
        let size = bubbleView.preferredSize
        bubbleView.frame = NSRect(origin: .zero, size: size)
        bubblePanel.setContentSize(size)
        bubbleView.show(term: term, body: body, loading: loading)
        bubbleVisible = true
        positionBubble()
        bubblePanel.orderFrontRegardless()
    }

    /// Replace the body of an already-visible bubble without moving the panel.
    private func updateBubble(term: String, body: String, loading: Bool, streaming: Bool) {
        guard bubbleVisible else { return }
        bubbleView.show(term: term, body: body, loading: loading, streaming: streaming)
    }

    private func hideBubble() {
        explainClient.cancel()
        explainTerm = ""
        bubbleVisible = false
        bubblePanel.orderOut(nil)
        // Explain flow sets suppressCardReveal; clear it so the next hover can show the card.
        let restoreCard = suppressCardReveal && (petInside || cardInside || cardMarking)
        suppressCardReveal = false
        if restoreCard {
            if showing {
                showCard()
            } else {
                syncHover()
            }
        }
    }

    private func positionBubble() {
        let size = bubblePanel.frame.size
        guard size.width > 0 else { return }
        let petFrame = petPanel.frame
        var origin = NSPoint(
            x: petFrame.midX - size.width / 2,
            y: petFrame.maxY + 10
        )
        if let screen = petVisibleFrame() {
            if origin.y + size.height > screen.maxY - 8 {
                origin.y = petFrame.minY - size.height - 10
            }
            origin.x = min(max(origin.x, screen.minX + 8), screen.maxX - size.width - 8)
            origin.y = min(max(origin.y, screen.minY + 8), screen.maxY - size.height - 8)
        }
        bubblePanel.setFrameOrigin(origin)
    }

    private func inboxCard() -> NSImage? {
        while let url = inboxQueue.head {
            if let image = NSImage(contentsOf: url) {
                sessionInbox = url
                return image
            }
            fputs("DeskPet: skip unreadable inbox file \(url.lastPathComponent)\n", stderr)
            inboxQueue.dequeue(url)
        }
        sessionInbox = nil
        return nil
    }

    private func localCard() -> NSImage? {
        sessionInbox = nil
        guard let cardURL = nextCard() else { return nil }
        return NSImage(contentsOf: cardURL)
    }

    private func nextCard() -> URL? {
        let pool = cards.filter { $0 != lastCard }
        let pick = (pool.isEmpty ? cards : pool).randomElement()
        lastCard = pick
        return pick
    }

    private func copyInboxURL() {
        let root = deskpetRoot()
        let urlFile = root.appendingPathComponent("inbox").appendingPathComponent("public-url.txt")
        let text: String
        if let stored = try? String(contentsOf: urlFile, encoding: .utf8) {
            let trimmed = stored.trimmingCharacters(in: .whitespacesAndNewlines)
            text = trimmed.isEmpty ? "" : trimmed
        } else {
            text = ""
        }
        if text.isEmpty {
            fputs("DeskPet: public inbox URL not ready yet\n", stderr)
            return
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    private func openSettings() {
        if settings == nil {
            let panel = SettingsController(
                zoom: config.zoom,
                cardMax: config.cardMaxWidth,
                minutes: config.awayAfterMinutes,
                repeatAfter: config.repeatHoverAfter,
                repeatWindow: config.repeatHoverWindowMinutes,
                hoverExit: config.hoverExitSeconds,
                studyMode: config.studyMode,
                explainPrompt: config.explainPrompt,
                bubbleWidth: config.explainBubbleWidth,
                bubbleHeight: config.explainBubbleHeight,
                fontSize: config.explainFontSize
            )
            panel.onPreviewZoom = { [weak self] zoom in
                self?.config.zoom = zoom
                self?.applyPose()
            }
            panel.onApply = { [weak self] zoom, cardMax, minutes, repeatAfter, repeatWindow, hoverExit, studyMode, prompt, bubbleW, bubbleH, fontSize in
                guard let self else { return }
                self.config.zoom = zoom
                self.config.cardMaxWidth = cardMax
                self.config.awayAfterMinutes = minutes
                self.config.repeatHoverAfter = repeatAfter
                self.config.repeatHoverWindowMinutes = repeatWindow
                self.config.hoverExitSeconds = hoverExit
                self.config.studyMode = studyMode
                self.config.explainPrompt = prompt
                self.config.explainBubbleWidth = bubbleW
                self.config.explainBubbleHeight = bubbleH
                self.config.explainFontSize = fontSize
                saveJSON(self.config, to: self.configURL)
                self.bubbleView.applyStyle(self.config.bubbleStyle)
                if self.showing, let image = self.cardView.imageView.image {
                    self.layoutCard(image)
                } else {
                    self.applyStudyLayout()
                }
                self.resetInteract()
                self.applyPose()
                self.snapIfNeeded()
            }
            settings = panel
        }
        settings?.show(
            zoom: config.zoom,
            cardMax: config.cardMaxWidth,
            minutes: config.awayAfterMinutes,
            repeatAfter: config.repeatHoverAfter,
            repeatWindow: config.repeatHoverWindowMinutes,
            hoverExit: config.hoverExitSeconds,
            studyMode: config.studyMode,
            explainPrompt: config.explainPrompt,
            bubbleWidth: config.explainBubbleWidth,
            bubbleHeight: config.explainBubbleHeight,
            fontSize: config.explainFontSize,
            on: petScreen()
        )
    }

    private func applyStudyLayout() {
        cardView.studyMode = config.studyMode
        cardView.clearStudy()
        guard showing, cardImageSize.width > 0 else { return }
        let extra = HoverView.extraHeight(for: config.studyMode)
        let panelSize = NSSize(width: cardImageSize.width, height: cardImageSize.height + extra)
        cardPanel.setContentSize(panelSize)
        cardView.frame = NSRect(origin: .zero, size: panelSize)
        positionCard()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
let menu = NSMenu()
let appMenu = NSMenu()
appMenu.addItem(
    withTitle: "Quit DeskPet",
    action: #selector(NSApplication.terminate(_:)),
    keyEquivalent: "q"
)
let appItem = NSMenuItem()
appItem.submenu = appMenu
menu.addItem(appItem)
app.mainMenu = menu
app.run()
