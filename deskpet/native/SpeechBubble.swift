import AppKit

struct BubbleStyle {
    var width: CGFloat
    var height: CGFloat
    var fontSize: CGFloat

    static let defaults = BubbleStyle(width: 320, height: 220, fontSize: 14)

    var size: NSSize { NSSize(width: width, height: height) }

    var codeFontSize: CGFloat { max(fontSize - 1, 11) }
}

/// Cream paper + faint graph-paper grid, matching AEFS memo cards.
private final class PaperBackgroundView: NSView {
    var paperColor = NSColor(calibratedRed: 0.973, green: 0.945, blue: 0.890, alpha: 0.98)
    var gridColor = NSColor(calibratedRed: 0.55, green: 0.50, blue: 0.42, alpha: 0.18)
    var inkBorder = NSColor(calibratedRed: 0.28, green: 0.22, blue: 0.16, alpha: 0.55)
    var corner: CGFloat = 12
    var gridStep: CGFloat = 14

    override var isOpaque: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }
        let bounds = self.bounds
        let path = NSBezierPath(roundedRect: bounds.insetBy(dx: 0.5, dy: 0.5), xRadius: corner, yRadius: corner)
        paperColor.setFill()
        path.fill()

        ctx.saveGState()
        path.addClip()
        gridColor.setStroke()
        let line = NSBezierPath()
        line.lineWidth = 1
        var x = bounds.minX
        while x <= bounds.maxX {
            line.move(to: NSPoint(x: x + 0.5, y: bounds.minY))
            line.line(to: NSPoint(x: x + 0.5, y: bounds.maxY))
            x += gridStep
        }
        var y = bounds.minY
        while y <= bounds.maxY {
            line.move(to: NSPoint(x: bounds.minX, y: y + 0.5))
            line.line(to: NSPoint(x: bounds.maxX, y: y + 0.5))
            y += gridStep
        }
        line.stroke()
        ctx.restoreGState()

        inkBorder.setStroke()
        path.lineWidth = 1.5
        path.stroke()
    }
}

enum MemoType {
    /// Prefer hand-note faces used by AEFS-style cards on macOS.
    static func font(ofSize size: CGFloat, weight: NSFont.Weight = .regular) -> NSFont {
        let preferred = [
            "Hannotate SC",
            "HannotateTC-Regular",
            "HanziPen SC",
            "Kaiti SC",
            "STKaiti",
            "PingFang SC",
        ]
        for name in preferred {
            if let font = NSFont(name: name, size: size) {
                if weight == .regular { return font }
                let traits: NSFontTraitMask = weight >= .semibold ? .boldFontMask : []
                return NSFontManager.shared.convert(font, toHaveTrait: traits)
            }
        }
        return .systemFont(ofSize: size, weight: weight)
    }

    static func mono(ofSize size: CGFloat) -> NSFont {
        if let font = NSFont(name: "SF Mono", size: size)
            ?? NSFont(name: "Menlo", size: size)
        {
            return font
        }
        return .monospacedSystemFont(ofSize: size, weight: .regular)
    }

    static let ink = NSColor(calibratedRed: 0.20, green: 0.15, blue: 0.10, alpha: 1)
    static let mutedInk = NSColor(calibratedRed: 0.42, green: 0.35, blue: 0.28, alpha: 1)
    static let codeWash = NSColor(calibratedRed: 0.90, green: 0.84, blue: 0.72, alpha: 0.65)
    static let link = NSColor(calibratedRed: 0.22, green: 0.40, blue: 0.55, alpha: 1)
}

final class SpeechBubbleView: NSView {
    var onDismiss: (() -> Void)?

    private let paper = PaperBackgroundView()
    private let scroll = NSScrollView()
    private let textView = NSTextView()
    private let titleLabel = NSTextField(labelWithString: "")
    private let closeButton = NSButton()
    private var style = BubbleStyle.defaults

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        layer?.masksToBounds = false

        paper.wantsLayer = true
        addSubview(paper)

        titleLabel.font = MemoType.font(ofSize: 13, weight: .semibold)
        titleLabel.textColor = MemoType.ink
        titleLabel.lineBreakMode = .byTruncatingTail
        titleLabel.backgroundColor = .clear
        titleLabel.drawsBackground = false
        paper.addSubview(titleLabel)

        closeButton.bezelStyle = .inline
        closeButton.isBordered = false
        closeButton.title = "✕"
        closeButton.font = MemoType.font(ofSize: 13, weight: .medium)
        closeButton.contentTintColor = MemoType.mutedInk
        closeButton.target = self
        closeButton.action = #selector(dismissTapped)
        paper.addSubview(closeButton)

        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = false
        scroll.autohidesScrollers = true
        scroll.borderType = .noBorder
        scroll.drawsBackground = false
        scroll.backgroundColor = .clear
        scroll.documentView = textView

        textView.isEditable = false
        textView.isSelectable = true
        textView.isRichText = true
        textView.drawsBackground = false
        textView.backgroundColor = .clear
        textView.font = MemoType.font(ofSize: style.fontSize)
        textView.textColor = MemoType.ink
        textView.textContainerInset = NSSize(width: 2, height: 2)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.textContainer?.widthTracksTextView = true
        textView.linkTextAttributes = [
            .foregroundColor: MemoType.link,
            .underlineStyle: NSUnderlineStyle.single.rawValue,
        ]
        paper.addSubview(scroll)
        applyStyle(style)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    func applyStyle(_ style: BubbleStyle) {
        self.style = style
        textView.font = MemoType.font(ofSize: style.fontSize)
        titleLabel.font = MemoType.font(ofSize: titleFontSize, weight: .semibold)
        closeButton.font = MemoType.font(ofSize: max(titleFontSize - 1, 11), weight: .medium)
        textView.textContainer?.containerSize = NSSize(
            width: max(style.width - 28, 40),
            height: CGFloat.greatestFiniteMagnitude
        )
        needsLayout = true
        paper.needsDisplay = true
    }

    var preferredSize: NSSize { style.size }

    private var titleFontSize: CGFloat { max(style.fontSize, 12) }

    /// Title row height scales with font; keep padding above/below the label.
    private var titleBarHeight: CGFloat {
        max(28, titleFontSize + 14)
    }

    override func layout() {
        super.layout()
        paper.frame = bounds
        let bar = titleBarHeight
        let titleH = titleFontSize + 4
        let closeSize = max(22, titleFontSize + 8)
        titleLabel.frame = NSRect(
            x: 14,
            y: bounds.height - bar + (bar - titleH) / 2,
            width: bounds.width - 14 - closeSize - 8,
            height: titleH
        )
        closeButton.frame = NSRect(
            x: bounds.width - closeSize - 8,
            y: bounds.height - bar + (bar - closeSize) / 2,
            width: closeSize,
            height: closeSize
        )
        let bottomPad: CGFloat = 10
        scroll.frame = NSRect(
            x: 12,
            y: bottomPad,
            width: bounds.width - 24,
            height: max(0, bounds.height - bar - bottomPad)
        )
        textView.frame = NSRect(origin: .zero, size: scroll.contentSize)
        textView.textContainer?.containerSize = NSSize(
            width: max(scroll.contentSize.width - 8, 40),
            height: CGFloat.greatestFiniteMagnitude
        )
        paper.needsDisplay = true
    }

    func show(term: String, body: String, loading: Bool) {
        let trimmed = term.trimmingCharacters(in: .whitespacesAndNewlines)
        titleLabel.stringValue = trimmed.isEmpty ? "解释" : "解释：\(trimmed)"
        let rendered = loading
            ? plainBody(body, loading: true)
            : renderMarkdown(body)
        textView.textStorage?.setAttributedString(rendered)
        needsLayout = true
    }

    private func plainBody(_ text: String, loading: Bool) -> NSAttributedString {
        let paragraph = baseParagraphStyle()
        return NSAttributedString(string: text, attributes: [
            .font: MemoType.font(ofSize: style.fontSize),
            .foregroundColor: loading ? MemoType.mutedInk : MemoType.ink,
            .paragraphStyle: paragraph,
        ])
    }

    private func baseParagraphStyle() -> NSMutableParagraphStyle {
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = 3
        paragraph.paragraphSpacing = 6
        paragraph.lineBreakMode = .byWordWrapping
        return paragraph
    }

    private func renderMarkdown(_ source: String) -> NSAttributedString {
        let cleaned = Self.normalizeMarkdown(source)
        let options = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .full,
            failurePolicy: .returnPartiallyParsedIfPossible
        )
        guard let parsed = try? AttributedString(markdown: cleaned, options: options) else {
            return plainBody(cleaned, loading: false)
        }

        let mutable = NSMutableAttributedString(attributedString: NSAttributedString(parsed))
        let full = NSRange(location: 0, length: mutable.length)
        guard full.length > 0 else { return plainBody(cleaned, loading: false) }

        let bodySize = style.fontSize
        let bodyFont = MemoType.font(ofSize: bodySize)
        let boldFont = MemoType.font(ofSize: bodySize, weight: .semibold)
        let italicBase = MemoType.font(ofSize: bodySize)
        let italicFont = NSFontManager.shared.convert(italicBase, toHaveTrait: .italicFontMask)
        let monoFont = MemoType.mono(ofSize: style.codeFontSize)
        let paragraph = baseParagraphStyle()

        // Base ink + paragraph on everything first.
        mutable.addAttributes([
            .foregroundColor: MemoType.ink,
            .paragraphStyle: paragraph,
        ], range: full)

        // Apply memo fonts per run without wiping markdown emphasis.
        mutable.enumerateAttributes(in: full, options: []) { attrs, range, _ in
            let existing = attrs[.font] as? NSFont
            let traits = existing.map { NSFontManager.shared.traits(of: $0) } ?? []
            let isMono = existing?.fontName.lowercased().contains("mono") == true
                || existing?.fontName.lowercased().contains("menlo") == true
                || existing?.fontName.lowercased().contains("courier") == true
            let isBold = traits.contains(.boldFontMask)
            let isItalic = traits.contains(.italicFontMask)

            let font: NSFont
            if isMono {
                font = monoFont
                mutable.addAttribute(.backgroundColor, value: MemoType.codeWash, range: range)
            } else if isBold && isItalic {
                font = NSFontManager.shared.convert(boldFont, toHaveTrait: .italicFontMask)
            } else if isBold {
                font = boldFont
            } else if isItalic {
                font = italicFont
            } else {
                font = bodyFont
            }
            mutable.addAttribute(.font, value: font, range: range)
        }

        return mutable
    }

    /// Soft cleanup so Apple's markdown parser is less likely to leave raw markers.
    private static func normalizeMarkdown(_ source: String) -> String {
        var text = source
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
        // Normalize full-width asterisks / backticks some models emit.
        text = text
            .replacingOccurrences(of: "＊", with: "*")
            .replacingOccurrences(of: "｀", with: "`")
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    @objc private func dismissTapped() {
        onDismiss?()
    }

    override func mouseDown(with event: NSEvent) {
        // Keep clicks inside the bubble from falling through.
    }
}
