import AppKit
import Foundation

struct Config: Codable {
    var character: String
    var cardsDir: String
    var cardMaxWidth: Int
    var zoom: Double
    var disdainAfterMinutes: Double

    enum CodingKeys: String, CodingKey {
        case character
        case cardsDir = "cards_dir"
        case cardMaxWidth = "card_max_width"
        case zoom
        case disdainAfterMinutes = "disdain_after_minutes"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        character = try box.decode(String.self, forKey: .character)
        cardsDir = try box.decodeIfPresent(String.self, forKey: .cardsDir) ?? "../notes/cards"
        cardMaxWidth = try box.decodeIfPresent(Int.self, forKey: .cardMaxWidth) ?? 460
        zoom = try box.decodeIfPresent(Double.self, forKey: .zoom) ?? 1.0
        disdainAfterMinutes = try box.decodeIfPresent(Double.self, forKey: .disdainAfterMinutes) ?? 10
    }

    func encode(to encoder: Encoder) throws {
        var box = encoder.container(keyedBy: CodingKeys.self)
        try box.encode(character, forKey: .character)
        try box.encode(cardsDir, forKey: .cardsDir)
        try box.encode(cardMaxWidth, forKey: .cardMaxWidth)
        try box.encode(zoom, forKey: .zoom)
        try box.encode(disdainAfterMinutes, forKey: .disdainAfterMinutes)
    }
}

struct CharacterSpec: Decodable {
    let id: String?
    let name: String?
    let idle: String
    let hover: String
    let peek: String?
    let peekHover: String?
    let peekDisdain: String?
    let disdain: String?
    let size: Int?
    let scale: String?
    let peekScale: Double?

    enum CodingKeys: String, CodingKey {
        case id, name, idle, hover, peek, disdain, size, scale
        case peekHover = "peek_hover"
        case peekDisdain = "peek_disdain"
        case peekScale = "peek_scale"
    }
}

struct CharacterPack {
    let id: String
    let name: String
    let idle: NSImage
    let hover: NSImage
    let peek: NSImage
    let peekHover: NSImage
    let peekDisdain: NSImage
    let disdain: NSImage
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

func fitted(_ image: NSImage, maxWidth: CGFloat, maxHeight: CGFloat) -> NSSize {
    let size = image.size
    let scale = min(maxWidth / max(size.width, 1), maxHeight / max(size.height, 1), 1)
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

final class HoverView: NSView {
    var onInside: ((Bool) -> Void)?
    var onSettings: (() -> Void)?
    var onDragMoved: (() -> Void)?
    var onDragEnded: (() -> Void)?
    var imageView = NSImageView()
    private var nearest = false
    private var dragGrab: NSPoint?
    private var dragMonitor: Any?
    private var dragGlobalMonitor: Any?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        imageView.imageScaling = .scaleProportionallyUpOrDown
        imageView.wantsLayer = true
        addSubview(imageView)
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
        imageView.frame = bounds
        applyScaling()
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
        guard let window else { return }
        let loc = NSEvent.mouseLocation
        dragGrab = NSPoint(x: loc.x - window.frame.minX, y: loc.y - window.frame.minY)
        stopDragMonitors()
        dragMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDragged, .leftMouseUp]) { [weak self] ev in
            self?.handleDrag(ev)
            return ev.type == .leftMouseUp ? ev : nil
        }
        dragGlobalMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDragged, .leftMouseUp]) { [weak self] ev in
            self?.handleDrag(ev)
        }
    }

    override func mouseUp(with event: NSEvent) {
        finishDrag()
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
        let settings = NSMenuItem(title: "设置…", action: #selector(openSettings), keyEquivalent: ",")
        settings.target = self
        menu.addItem(settings)
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

    override func hitTest(_ point: NSPoint) -> NSView? {
        guard let hit = super.hitTest(point), let image = imageView.image else {
            return super.hitTest(point)
        }
        let size = bounds.size
        guard size.width > 0, size.height > 0 else { return hit }
        var rect = CGRect(origin: .zero, size: image.size)
        guard let cg = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
            return hit
        }
        let px = min(max(Int(point.x / size.width * CGFloat(cg.width)), 0), cg.width - 1)
        let py = min(max(Int((1 - point.y / size.height) * CGFloat(cg.height)), 0), cg.height - 1)
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
    var onApply: ((Double, Double) -> Void)?

    init(zoom: Double, minutes: Double) {
        zoomSlider = NSSlider(value: zoom, minValue: 0.5, maxValue: 2.5, target: nil, action: nil)
        zoomSlider.isContinuous = true
        zoomLabel = NSTextField(labelWithString: "")
        minutesField = NSTextField(string: String(format: "%g", minutes))
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 360, height: 210),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        super.init()
        window.title = "DeskPet 设置"
        window.level = .floating
        window.isReleasedWhenClosed = false

        let content = NSView(frame: NSRect(x: 0, y: 0, width: 360, height: 210))
        func label(_ text: String, y: CGFloat) -> NSTextField {
            let field = NSTextField(labelWithString: text)
            field.frame = NSRect(x: 20, y: y, width: 320, height: 18)
            return field
        }
        content.addSubview(label("缩放", y: 168))
        zoomSlider.frame = NSRect(x: 20, y: 140, width: 240, height: 24)
        zoomSlider.target = self
        zoomSlider.action = #selector(zoomChanged)
        zoomLabel.frame = NSRect(x: 270, y: 142, width: 70, height: 20)
        content.addSubview(zoomSlider)
        content.addSubview(zoomLabel)
        content.addSubview(label("多久露出鄙视眼神（分钟，0 为关闭）", y: 108))
        minutesField.frame = NSRect(x: 20, y: 80, width: 120, height: 24)
        minutesField.placeholderString = "10"
        content.addSubview(minutesField)
        let hint = NSTextField(labelWithString: "拖到屏幕边缘会贴边探头")
        hint.textColor = .secondaryLabelColor
        hint.frame = NSRect(x: 20, y: 48, width: 320, height: 18)
        content.addSubview(hint)
        let save = NSButton(title: "保存", target: self, action: #selector(saveTapped))
        save.bezelStyle = .rounded
        save.frame = NSRect(x: 250, y: 16, width: 90, height: 28)
        content.addSubview(save)
        window.contentView = content
        window.delegate = self
        refreshZoomLabel()
    }

    func show(zoom: Double, minutes: Double, on screen: NSScreen?) {
        zoomSlider.doubleValue = zoom
        minutesField.stringValue = String(format: "%g", minutes)
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
        onApply?(zoomSlider.doubleValue, parsedMinutes())
    }

    private func parsedMinutes() -> Double {
        let value = Double(minutesField.stringValue.trimmingCharacters(in: .whitespaces)) ?? 10
        return max(0, value)
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
    private var petView: HoverView!
    private var cardView: HoverView!
    private var pack: CharacterPack!
    private var peekLeft: NSImage!
    private var peekHoverLeft: NSImage!
    private var peekDisdainLeft: NSImage!
    private var cards: [URL] = []
    private var lastCard: URL?
    private var petInside = false
    private var cardInside = false
    private var hideWork: DispatchWorkItem?
    private var showing = false
    private var disdainClock = DisdainClock()
    private var docked: DockedEdge = .none
    private var dragging = false
    private var tick: Timer?
    private var config: Config!
    private var configURL: URL!
    private var settings: SettingsController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let root = deskpetRoot()
        configURL = root.appendingPathComponent("config.json")
        config = loadJSON(Config.self, from: configURL)
        let packDir = root.appendingPathComponent("characters").appendingPathComponent(config.character)
        let spec = loadJSON(CharacterSpec.self, from: packDir.appendingPathComponent("character.json"))
        let idle = requireImage(packDir.appendingPathComponent(spec.idle))
        let hover = requireImage(packDir.appendingPathComponent(spec.hover))
        pack = CharacterPack(
            id: spec.id ?? config.character,
            name: spec.name ?? config.character,
            idle: idle,
            hover: hover,
            peek: spec.peek.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? idle,
            peekHover: spec.peekHover.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? hover,
            peekDisdain: spec.peekDisdain.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? idle,
            disdain: spec.disdain.flatMap { loadImage(packDir.appendingPathComponent($0)) } ?? idle,
            size: CGFloat(spec.size ?? 200),
            nearest: spec.scale == "nearest",
            peekScale: CGFloat(spec.peekScale ?? 0.5)
        )
        peekLeft = flippedHorizontally(pack.peek)
        peekHoverLeft = flippedHorizontally(pack.peekHover)
        peekDisdainLeft = flippedHorizontally(pack.peekDisdain)
        let cardsRoot = URL(fileURLWithPath: config.cardsDir, isDirectory: true, relativeTo: root)
            .absoluteURL
            .standardizedFileURL
        cards = listCanonicalCards(root: cardsRoot)
        if cards.isEmpty {
            fputs("DeskPet: no cards under \(cardsRoot.path)\n", stderr)
        }

        petView = HoverView(frame: .zero)
        petView.setNearestScaling(pack.nearest)
        petView.onInside = { [weak self] inside in
            self?.petInside = inside
            self?.syncHover()
        }
        petView.onSettings = { [weak self] in self?.openSettings() }
        petView.onDragMoved = { [weak self] in self?.updateDockWhileDragging() }
        petView.onDragEnded = { [weak self] in self?.endDrag() }

        cardView = HoverView(frame: .zero)
        cardView.onInside = { [weak self] inside in
            self?.cardInside = inside
            self?.syncHover()
        }

        petPanel = makePanel()
        petPanel.contentView = petView
        cardPanel = makePanel()
        cardPanel.contentView = cardView
        cardPanel.orderOut(nil)

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
            self?.checkDisdain()
        }
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.snapIfNeeded()
        }
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

    private func poseImage() -> NSImage {
        let sidePeek = docked == .left || docked == .right
        if sidePeek { return peekImage() }
        if showing { return pack.hover }
        if disdainClock.isDisdain { return pack.disdain }
        return pack.idle
    }

    private func peekImage() -> NSImage {
        if showing {
            return docked == .left ? peekHoverLeft : pack.peekHover
        }
        if disdainClock.isDisdain {
            return docked == .left ? peekDisdainLeft : pack.peekDisdain
        }
        return docked == .left ? peekLeft : pack.peek
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
    }

    private func resetInteract() {
        let wasDisdain = disdainClock.isDisdain
        disdainClock.markInteracted()
        if wasDisdain, !showing { applyPose() }
    }

    private func checkDisdain() {
        let wasDisdain = disdainClock.isDisdain
        disdainClock.tick(
            afterMinutes: config.disdainAfterMinutes,
            paused: petInside || showing
        )
        if disdainClock.isDisdain, !wasDisdain {
            applyPose()
        }
    }

    private func syncHover() {
        hideWork?.cancel()
        if petInside || cardInside {
            disdainClock.hoverChanged(inside: true)
            if !showing {
                showing = true
                applyPose()
                showCard()
            }
            return
        }
        disdainClock.hoverChanged(inside: false)
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.petInside, !self.cardInside else { return }
            self.showing = false
            self.cardPanel.orderOut(nil)
            self.applyPose()
        }
        hideWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18, execute: work)
    }

    private func showCard() {
        guard let cardURL = nextCard(), let image = NSImage(contentsOf: cardURL) else { return }
        let screen = petVisibleFrame()
        let maxHeight = (screen?.height ?? 800) * 0.72
        let size = fitted(image, maxWidth: CGFloat(config.cardMaxWidth), maxHeight: maxHeight)
        cardView.imageView.image = image
        cardPanel.setContentSize(size)
        cardView.frame = NSRect(origin: .zero, size: size)
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

    private func nextCard() -> URL? {
        let pool = cards.filter { $0 != lastCard }
        let pick = (pool.isEmpty ? cards : pool).randomElement()
        lastCard = pick
        return pick
    }

    private func openSettings() {
        if settings == nil {
            let panel = SettingsController(zoom: config.zoom, minutes: config.disdainAfterMinutes)
            panel.onPreviewZoom = { [weak self] zoom in
                self?.config.zoom = zoom
                self?.applyPose()
            }
            panel.onApply = { [weak self] zoom, minutes in
                guard let self else { return }
                self.config.zoom = zoom
                self.config.disdainAfterMinutes = minutes
                saveJSON(self.config, to: self.configURL)
                self.resetInteract()
                self.applyPose()
                self.snapIfNeeded()
            }
            settings = panel
        }
        settings?.show(zoom: config.zoom, minutes: config.disdainAfterMinutes, on: petScreen())
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
