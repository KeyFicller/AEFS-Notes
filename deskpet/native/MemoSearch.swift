import AppKit

/// One retrieval hit, decoded from rag_retrieve.py --serve.
struct MemoHit {
    let url: URL
    let title: String
    let phase: String
    let summary: String
}

/// Long-lived `rag_retrieve.py --serve` child process.
///
/// Loading the vision and text models costs ~6s, so the process is spawned once and
/// fed one query per line; it answers with one JSON line per query.
final class MemoClient {
    private var process: Process?
    private var input: Pipe?
    private var buffer = Data()
    private let root: URL
    private var pendingQuery: String?

    var onReady: (() -> Void)?
    var onResults: ((String, [MemoHit]) -> Void)?
    var onFailure: ((String) -> Void)?

    init(root: URL) {
        self.root = root
    }

    /// Spawns the helper on first use. Returns immediately; readiness arrives via onReady.
    func start() {
        guard process == nil else { return }
        let script = root.appendingPathComponent("notes").appendingPathComponent("rag_retrieve.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            onFailure?("找不到 notes/rag_retrieve.py")
            return
        }
        let venvPython = root.appendingPathComponent(".venv/bin/python")
        let python = FileManager.default.isExecutableFile(atPath: venvPython.path)
            ? venvPython.path
            : "/usr/bin/env"
        var arguments = [script.path, "--serve"]
        if python == "/usr/bin/env" {
            arguments.insert("python3", at: 0)
        }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = arguments
        proc.currentDirectoryURL = root
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        proc.environment = environment

        let inPipe = Pipe()
        let out = Pipe()
        proc.standardInput = inPipe
        proc.standardOutput = out
        // Keep stderr away from the pipe: model-loading noise would corrupt the JSON stream.
        proc.standardError = Pipe()

        out.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty else { return }
            self?.consume(chunk)
        }
        do {
            try proc.run()
        } catch {
            onFailure?("检索进程启动失败：\(error.localizedDescription)")
            return
        }
        process = proc
        input = inPipe
    }

    func query(_ text: String) {
        start()
        guard let input else { return }
        pendingQuery = text
        let line = text.replacingOccurrences(of: "\n", with: " ") + "\n"
        input.fileHandleForWriting.write(Data(line.utf8))
    }

    func stop() {
        process?.terminate()
        process = nil
        input = nil
    }

    private func consume(_ chunk: Data) {
        buffer.append(chunk)
        while let breakIndex = buffer.firstIndex(of: 0x0A) {
            let lineData = buffer[buffer.startIndex..<breakIndex]
            buffer.removeSubrange(buffer.startIndex...breakIndex)
            guard !lineData.isEmpty,
                  let object = try? JSONSerialization.jsonObject(with: Data(lineData)) as? [String: Any]
            else { continue }
            if object["ready"] != nil {
                DispatchQueue.main.async { [weak self] in self?.onReady?() }
            } else if let results = object["results"] as? [[String: Any]] {
                let queryText = object["query"] as? String ?? pendingQuery ?? ""
                let hits = results.compactMap { [root] item -> MemoHit? in
                    guard let path = item["path"] as? String else { return nil }
                    return MemoHit(
                        url: root.appendingPathComponent(path),
                        title: item["title"] as? String ?? "",
                        phase: item["phase"] as? String ?? "",
                        summary: item["summary"] as? String ?? ""
                    )
                }
                DispatchQueue.main.async { [weak self] in
                    self?.onResults?(queryText, hits)
                }
            } else if let message = object["error"] as? String {
                DispatchQueue.main.async { [weak self] in self?.onFailure?(message) }
            }
        }
    }
}

/// One result row: 3:4 thumbnail, title, phase, one-line summary.
final class MemoRow: NSView {
    var onClick: (() -> Void)?
    private let thumbnail = NSImageView()
    private let titleLabel = NSTextField(labelWithString: "")
    private let phaseLabel = NSTextField(labelWithString: "")
    private let summaryLabel = NSTextField(labelWithString: "")
    private var tracking: NSTrackingArea?

    init(hit: MemoHit) {
        super.init(frame: .zero)
        wantsLayer = true
        layer?.cornerRadius = 8

        thumbnail.image = NSImage(contentsOf: hit.url)
        thumbnail.imageScaling = .scaleProportionallyUpOrDown
        thumbnail.wantsLayer = true
        thumbnail.layer?.cornerRadius = 4
        thumbnail.layer?.borderWidth = 1
        thumbnail.layer?.borderColor = NSColor.separatorColor.cgColor

        titleLabel.stringValue = hit.title
        titleLabel.font = .systemFont(ofSize: 14, weight: .semibold)
        titleLabel.lineBreakMode = .byTruncatingTail

        phaseLabel.stringValue = hit.phase
        phaseLabel.font = .systemFont(ofSize: 11)
        phaseLabel.textColor = .secondaryLabelColor

        summaryLabel.stringValue = hit.summary
        summaryLabel.font = .systemFont(ofSize: 11)
        summaryLabel.textColor = .tertiaryLabelColor
        summaryLabel.lineBreakMode = .byTruncatingTail
        summaryLabel.maximumNumberOfLines = 2

        for view in [thumbnail, titleLabel, phaseLabel, summaryLabel] {
            view.translatesAutoresizingMaskIntoConstraints = false
            addSubview(view)
        }
        NSLayoutConstraint.activate([
            thumbnail.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 10),
            thumbnail.centerYAnchor.constraint(equalTo: centerYAnchor),
            thumbnail.widthAnchor.constraint(equalToConstant: 66),
            thumbnail.heightAnchor.constraint(equalToConstant: 88),

            titleLabel.leadingAnchor.constraint(equalTo: thumbnail.trailingAnchor, constant: 12),
            titleLabel.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -10),
            titleLabel.topAnchor.constraint(equalTo: topAnchor, constant: 14),

            phaseLabel.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            phaseLabel.trailingAnchor.constraint(equalTo: titleLabel.trailingAnchor),
            phaseLabel.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 2),

            summaryLabel.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            summaryLabel.trailingAnchor.constraint(equalTo: titleLabel.trailingAnchor),
            summaryLabel.topAnchor.constraint(equalTo: phaseLabel.bottomAnchor, constant: 4),
            summaryLabel.bottomAnchor.constraint(lessThanOrEqualTo: bottomAnchor, constant: -12),
        ])
    }

    required init?(coder: NSCoder) { fatalError() }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking { removeTrackingArea(tracking) }
        let area = NSTrackingArea(
            rect: bounds,
            options: [.mouseEnteredAndExited, .activeAlways],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(area)
        tracking = area
    }

    override func mouseEntered(with event: NSEvent) {
        layer?.backgroundColor = NSColor.controlAccentColor.withAlphaComponent(0.12).cgColor
    }

    override func mouseExited(with event: NSEvent) {
        layer?.backgroundColor = NSColor.clear.cgColor
    }

    override func mouseDown(with event: NSEvent) {
        onClick?()
    }
}

/// Deterministic row list for the scroll view's document view.
///
/// NSStackView inside a scroll view has no definite width to distribute against, so each
/// row sized itself from its own intrinsic content and the rows landed at staggered x
/// offsets. Rows here are a fixed height, so plain frames are both shorter and exact.
final class MemoResultsView: NSView {
    static let rowHeight: CGFloat = 104
    private static let gap: CGFloat = 8
    private static let inset: CGFloat = 8

    private var rows: [MemoRow] = []

    override var isFlipped: Bool { true }

    func show(rows newRows: [MemoRow]) {
        rows.forEach { $0.removeFromSuperview() }
        rows = newRows
        rows.forEach(addSubview)
        needsLayout = true
    }

    override func layout() {
        super.layout()
        // The clip view is the authority on visible width; taking bounds.width from self
        // keeps a stale width if layout ran before the window was sized.
        let width = max(superview?.bounds.width ?? bounds.width, 1)
        var y = Self.inset
        for row in rows {
            row.frame = NSRect(x: Self.inset, y: y, width: max(width - Self.inset * 2, 1),
                               height: Self.rowHeight)
            y += Self.rowHeight + Self.gap
        }
        let height = rows.isEmpty ? 1 : y - Self.gap + Self.inset
        if abs(frame.width - width) > 0.5 || abs(frame.height - height) > 0.5 {
            setFrameSize(NSSize(width: width, height: height))
        }
    }
}

/// Search box + result list. Type a query, press Return, click a row to enlarge.
final class MemoSearchPanel: NSObject {
    let window: NSWindow
    var onOpen: ((URL) -> Void)?

    private let field = NSSearchField()
    private let status = NSTextField(labelWithString: "")
    private let results = MemoResultsView()
    private let scroll = NSScrollView()
    private var client: MemoClient?

    init(root: URL) {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 660),
            styleMask: [.titled, .closable, .resizable],
            backing: .buffered,
            defer: false
        )
        super.init()
        window.title = "检索备忘"
        window.level = .floating
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 420, height: 360)

        let container = NSView()
        window.contentView = container

        field.placeholderString = "输入检索语句，回车（例如：长任务怎么调度）"
        field.target = self
        field.action = #selector(submit)
        field.translatesAutoresizingMaskIntoConstraints = false

        status.stringValue = "准备中…"
        status.font = .systemFont(ofSize: 11)
        status.textColor = .secondaryLabelColor
        status.translatesAutoresizingMaskIntoConstraints = false

        results.frame = NSRect(x: 0, y: 0, width: 480, height: 1)
        results.autoresizingMask = [.width]

        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.documentView = results

        container.addSubview(field)
        container.addSubview(status)
        container.addSubview(scroll)

        NSLayoutConstraint.activate([
            field.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 16),
            field.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -16),
            field.topAnchor.constraint(equalTo: container.topAnchor, constant: 16),

            status.leadingAnchor.constraint(equalTo: field.leadingAnchor),
            status.trailingAnchor.constraint(equalTo: field.trailingAnchor),
            status.topAnchor.constraint(equalTo: field.bottomAnchor, constant: 8),

            scroll.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: status.bottomAnchor, constant: 8),
            scroll.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])

        let memo = MemoClient(root: root)
        memo.onReady = { [weak self] in
            self?.status.stringValue = "就绪"
        }
        memo.onResults = { [weak self] queryText, hits in
            self?.render(query: queryText, hits: hits)
        }
        memo.onFailure = { [weak self] message in
            self?.status.stringValue = message
        }
        client = memo
        memo.start()
    }

    func show(near petFrame: NSRect) {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        window.makeFirstResponder(field)
        if let screen = window.screen?.visibleFrame ?? NSScreen.main?.visibleFrame {
            var origin = NSPoint(x: petFrame.minX - window.frame.width - 12,
                                 y: petFrame.midY - window.frame.height / 2)
            origin.x = max(origin.x, screen.minX + 8)
            origin.y = min(max(origin.y, screen.minY + 8), screen.maxY - window.frame.height - 8)
            window.setFrameOrigin(origin)
        }
    }

    func stop() {
        client?.stop()
        client = nil
    }

    @objc private func submit() {
        let text = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        status.stringValue = "检索中…"
        client?.query(text)
    }

    private func render(query: String, hits: [MemoHit]) {
        guard !hits.isEmpty else {
            results.show(rows: [])
            status.stringValue = "没有命中「\(query)」"
            return
        }
        status.stringValue = "「\(query)」命中 \(hits.count) 张"
        results.show(rows: hits.map { hit in
            let row = MemoRow(hit: hit)
            row.onClick = { [weak self] in self?.onOpen?(hit.url) }
            return row
        })
        results.layoutSubtreeIfNeeded()
        scroll.contentView.scroll(to: .zero)
        scroll.reflectScrolledClipView(scroll.contentView)
    }
}

/// Full-size card, click anywhere or press Esc to close.
final class MemoPreviewPanel: NSObject {
    let window: PreviewWindow
    private let view = MemoPreviewView()

    override init() {
        window = PreviewWindow(
            contentRect: NSRect(x: 0, y: 0, width: 600, height: 800),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        super.init()
        window.level = .floating
        window.isReleasedWhenClosed = false
        window.backgroundColor = .clear
        view.imageScaling = .scaleProportionallyUpOrDown
        view.wantsLayer = true
        view.layer?.cornerRadius = 10
        view.onClose = { [weak self] in self?.hide() }
        window.contentView = view
    }

    func show(url: URL) {
        guard let image = NSImage(contentsOf: url) else { return }
        view.image = image
        let visible = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1200, height: 800)
        let ratio = min(visible.width * 0.8 / image.size.width,
                        visible.height * 0.88 / image.size.height,
                        2)
        let size = NSSize(width: image.size.width * ratio, height: image.size.height * ratio)
        window.setContentSize(size)
        window.setFrameOrigin(NSPoint(x: visible.midX - size.width / 2,
                                      y: visible.midY - size.height / 2))
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(view)
        NSApp.activate(ignoringOtherApps: true)
    }

    func hide() {
        window.orderOut(nil)
    }
}

final class PreviewWindow: NSWindow {
    override var canBecomeKey: Bool { true }
}

/// Click-to-dismiss image view: any click closes, Esc closes.
final class MemoPreviewView: NSImageView {
    var onClose: (() -> Void)?

    override func mouseDown(with event: NSEvent) {
        onClose?()
    }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 {  // Esc
            onClose?()
        } else {
            super.keyDown(with: event)
        }
    }

    override var acceptsFirstResponder: Bool { true }
}
