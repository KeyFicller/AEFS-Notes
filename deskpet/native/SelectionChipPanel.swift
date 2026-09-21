import AppKit

/// Tiny floating chip shown near the cursor after a text selection.
final class SelectionChipPanel {
    var onTap: ((String) -> Void)?

    private let panel: NSPanel
    private let button: NSButton
    private var cachedText = ""
    private var hideWork: DispatchWorkItem?
    private let timeout: TimeInterval = 5
    private let chipSize = NSSize(width: 28, height: 28)

    init() {
        panel = NSPanel(
            contentRect: NSRect(origin: .zero, size: chipSize),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.hidesOnDeactivate = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.ignoresMouseEvents = false
        panel.becomesKeyOnlyIfNeeded = true

        button = NSButton(frame: NSRect(origin: .zero, size: chipSize))
        button.title = ""
        button.bezelStyle = .inline
        button.isBordered = false
        button.wantsLayer = true
        button.layer?.backgroundColor = NSColor.windowBackgroundColor.withAlphaComponent(0.95).cgColor
        button.layer?.cornerRadius = 14
        button.layer?.borderWidth = 1
        button.layer?.borderColor = NSColor.separatorColor.cgColor
        if let image = NSImage(systemSymbolName: "text.magnifyingglass", accessibilityDescription: "解释") {
            let config = NSImage.SymbolConfiguration(pointSize: 13, weight: .medium)
            button.image = image.withSymbolConfiguration(config)
        } else {
            button.title = "?"
            button.font = .systemFont(ofSize: 14, weight: .semibold)
        }
        button.imagePosition = .imageOnly
        button.target = self
        button.action = #selector(tapped)
        panel.contentView = button
    }

    var isVisible: Bool { panel.isVisible }

    func show(text: String, near point: NSPoint) {
        cachedText = text
        var origin = NSPoint(x: point.x + 12, y: point.y + 12)
        if let screen = NSScreen.screens.first(where: { $0.frame.contains(point) })?.visibleFrame
            ?? NSScreen.main?.visibleFrame
        {
            origin.x = min(max(origin.x, screen.minX + 4), screen.maxX - chipSize.width - 4)
            origin.y = min(max(origin.y, screen.minY + 4), screen.maxY - chipSize.height - 4)
        }
        panel.setFrame(NSRect(origin: origin, size: chipSize), display: true)
        panel.orderFrontRegardless()
        scheduleHide()
    }

    func hide() {
        hideWork?.cancel()
        hideWork = nil
        cachedText = ""
        panel.orderOut(nil)
    }

    private func scheduleHide() {
        hideWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.hide()
        }
        hideWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + timeout, execute: work)
    }

    @objc private func tapped() {
        let text = cachedText
        hide()
        guard !text.isEmpty else { return }
        onTap?(text)
    }
}
