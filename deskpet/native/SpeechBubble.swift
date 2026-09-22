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

private final class FollowUpField: NSTextField {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with event: NSEvent) {
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKey()
        super.mouseDown(with: event)
    }
}

/// Rounded tray behind the follow-up field. Clicks in the padding focus the field.
private final class FollowUpChrome: NSView {
    var onClick: (() -> Void)?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.cornerRadius = 8
        layer?.backgroundColor = NSColor(calibratedRed: 1, green: 0.985, blue: 0.95, alpha: 1).cgColor
        layer?.borderWidth = 1
        layer?.borderColor = NSColor(calibratedWhite: 0.45, alpha: 0.35).cgColor
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with event: NSEvent) {
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKey()
        onClick?()
    }
}

private final class FirstMouseButton: NSButton {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

final class SpeechBubbleView: NSView, NSTextFieldDelegate {
    var onDismiss: (() -> Void)?
    /// Return true when the question is accepted and the field should clear.
    var onFollowUp: ((String) -> Bool)?

    private let paper = PaperBackgroundView()
    private let scroll = NSScrollView()
    private let textView = NSTextView()
    private let titleLabel = NSTextField(labelWithString: "")
    private let closeButton = NSButton()
    private let followChrome = FollowUpChrome(frame: .zero)
    private let followField = FollowUpField(string: "")
    private let sendButton = FirstMouseButton()
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
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude
        )
        textView.textContainer?.widthTracksTextView = true
        textView.linkTextAttributes = [
            .foregroundColor: MemoType.link,
            .underlineStyle: NSUnderlineStyle.single.rawValue,
        ]
        paper.addSubview(scroll)

        followField.placeholderString = "追问…"
        followField.font = MemoType.font(ofSize: style.fontSize)
        followField.textColor = MemoType.ink
        followField.drawsBackground = false
        followField.isBezeled = false
        followField.isBordered = false
        followField.focusRingType = .none
        followField.cell?.usesSingleLineMode = true
        followField.cell?.wraps = false
        followField.cell?.isScrollable = true
        followField.lineBreakMode = .byTruncatingTail
        followField.delegate = self
        followField.isEnabled = false
        followChrome.onClick = { [weak self] in
            guard let self, self.followField.isEnabled else { return }
            self.window?.makeFirstResponder(self.followField)
        }
        followChrome.addSubview(followField)
        paper.addSubview(followChrome)

        sendButton.bezelStyle = .rounded
        sendButton.title = "问"
        sendButton.font = MemoType.font(ofSize: 13, weight: .medium)
        sendButton.target = self
        sendButton.action = #selector(sendFollowUp)
        sendButton.isEnabled = false
        paper.addSubview(sendButton)

        applyStyle(style)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    func applyStyle(_ style: BubbleStyle) {
        self.style = style
        textView.font = MemoType.font(ofSize: style.fontSize)
        titleLabel.font = MemoType.font(ofSize: titleFontSize, weight: .semibold)
        closeButton.font = MemoType.font(ofSize: max(titleFontSize - 1, 11), weight: .medium)
        followField.font = MemoType.font(ofSize: style.fontSize)
        sendButton.font = MemoType.font(ofSize: max(style.fontSize - 2, 12), weight: .medium)
        textView.textContainer?.containerSize = NSSize(
            width: max(style.width - 28, 40),
            height: CGFloat.greatestFiniteMagnitude
        )
        needsLayout = true
        paper.needsDisplay = true
    }

    var preferredSize: NSSize { style.size }

    private var titleFontSize: CGFloat { max(style.fontSize, 12) }

    private var inputHeight: CGFloat { max(28, style.fontSize + 14) }

    private var sendWidth: CGFloat { max(36, style.fontSize + 22) }

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
        let inputY: CGFloat = 10
        let gap: CGFloat = 6
        sendButton.frame = NSRect(
            x: bounds.width - 12 - sendWidth,
            y: inputY,
            width: sendWidth,
            height: inputHeight
        )
        let chrome = NSRect(
            x: 12,
            y: inputY,
            width: max(40, bounds.width - 12 - gap - sendWidth - 12),
            height: inputHeight
        )
        followChrome.frame = chrome
        placeFollowField(in: chrome)
        let scrollBottom = inputY + inputHeight + 8
        scroll.frame = NSRect(
            x: 12,
            y: scrollBottom,
            width: bounds.width - 24,
            height: max(0, bounds.height - bar - scrollBottom)
        )
        resizeTextDocument()
        paper.needsDisplay = true
    }

    /// Handwriting faces leave the descender empty, so a line-box-centered
    /// field looks high. Drop it by half the descender to center the ink.
    private func placeFollowField(in chrome: NSRect) {
        let font = followField.font ?? MemoType.font(ofSize: style.fontSize)
        let line = ceil(font.ascender - font.descender)
        let textH = min(max(line, font.pointSize), chrome.height)
        let drop = min(-font.descender / 2, max(0, (chrome.height - textH) / 2))
        let textY = (chrome.height - textH) / 2 - drop
        followField.frame = NSRect(
            x: 8,
            y: max(0, textY),
            width: max(20, chrome.width - 16),
            height: textH
        )
    }

    func show(
        term: String,
        body: String,
        loading: Bool,
        streaming: Bool = false,
        pinToEnd: Bool = false
    ) {
        if loading || streaming {
            setFollowUpEnabled(false)
        }
        let stick = pinToEnd || (!loading && isNearBottom())
        let savedOrigin = scroll.contentView.bounds.origin
        let trimmed = term.trimmingCharacters(in: .whitespacesAndNewlines)
        titleLabel.stringValue = trimmed.isEmpty ? "解释" : "解释：\(trimmed)"
        let rendered = loading
            ? plainBody(body, loading: true)
            : renderMarkdown(body, trimEdges: !streaming)
        textView.textStorage?.setAttributedString(rendered)
        needsLayout = true
        layoutSubtreeIfNeeded()
        if stick {
            scrollToEnd()
        } else if !loading {
            scroll.contentView.scroll(to: savedOrigin)
            scroll.reflectScrolledClipView(scroll.contentView)
        }
    }

    /// Grow the text view with its content so the bubble can scroll past the visible area.
    private func resizeTextDocument() {
        let width = scroll.contentSize.width
        textView.textContainer?.containerSize = NSSize(
            width: max(width - 8, 40),
            height: CGFloat.greatestFiniteMagnitude
        )
        guard let container = textView.textContainer else { return }
        textView.layoutManager?.ensureLayout(for: container)
        let used = textView.layoutManager?.usedRect(for: container).height ?? 0
        let height = max(
            scroll.contentSize.height,
            ceil(used + textView.textContainerInset.height * 2)
        )
        let next = NSRect(x: 0, y: 0, width: width, height: height)
        if textView.frame != next {
            textView.frame = next
        }
    }

    private func isNearBottom(slack: CGFloat = 36) -> Bool {
        let visible = scroll.contentView.bounds
        let docHeight = max(textView.frame.height, scroll.documentView?.bounds.height ?? 0)
        if docHeight <= visible.height + 1 { return true }
        return visible.maxY >= docHeight - slack
    }

    private func scrollToEnd() {
        let length = (textView.string as NSString).length
        guard length > 0 else { return }
        textView.scrollRangeToVisible(NSRange(location: length, length: 0))
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

    private func renderMarkdown(_ source: String, trimEdges: Bool = true) -> NSAttributedString {
        let cleaned = Self.normalizeMarkdown(source, trimEdges: trimEdges)
        // `.full` stores paragraphs as PresentationIntent and drops `\n` when
        // bridging to NSAttributedString — sections visually merge. Inline mode
        // keeps blank lines from normalizeMarkdown while still parsing **bold**/`code`.
        let options = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace,
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
        let intentKey = NSAttributedString.Key("NSInlinePresentationIntent")

        // Base ink + paragraph on everything first.
        mutable.addAttributes([
            .foregroundColor: MemoType.ink,
            .paragraphStyle: paragraph,
        ], range: full)

        // Apply memo fonts per run. Emphasis arrives as InlinePresentationIntent, not NSFont.
        mutable.enumerateAttributes(in: full, options: []) { attrs, range, _ in
            let existing = attrs[.font] as? NSFont
            let traits = existing.map { NSFontManager.shared.traits(of: $0) } ?? []
            let intent: UInt
            if let v = attrs[intentKey] as? UInt {
                intent = v
            } else if let v = attrs[intentKey] as? Int {
                intent = UInt(v)
            } else {
                intent = 0
            }
            let isMono = (intent & 4) != 0
                || existing?.fontName.lowercased().contains("mono") == true
                || existing?.fontName.lowercased().contains("menlo") == true
                || existing?.fontName.lowercased().contains("courier") == true
            let isBold = (intent & 2) != 0 || traits.contains(.boldFontMask)
            let isItalic = (intent & 1) != 0 || traits.contains(.italicFontMask)

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

    /// Soft cleanup + force three-section breaks so Markdown keeps paragraphs.
    private static func normalizeMarkdown(_ source: String, trimEdges: Bool = true) -> String {
        var text = source
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .replacingOccurrences(of: "＊", with: "*")
            .replacingOccurrences(of: "｀", with: "`")

        // Models often jam sections into one paragraph ("。举例：…。总结：").
        // Insert a blank line before each section label so Markdown makes new paragraphs.
        let labels = ["一句话解释：", "举例：", "总结："]
        for label in labels {
            let escaped = NSRegularExpression.escapedPattern(for: label)
            // Any non-newline char (or spaces) immediately before the label → blank line.
            if let regex = try? NSRegularExpression(
                pattern: #"([^\n])[ \t]*"# + escaped,
                options: []
            ) {
                let range = NSRange(text.startIndex..<text.endIndex, in: text)
                text = regex.stringByReplacingMatches(
                    in: text,
                    options: [],
                    range: range,
                    withTemplate: "$1\n\n" + label
                )
            }
            // Single newline before label → blank line.
            if let regex = try? NSRegularExpression(
                pattern: #"\n[ \t]*"# + escaped,
                options: []
            ) {
                let range = NSRange(text.startIndex..<text.endIndex, in: text)
                text = regex.stringByReplacingMatches(
                    in: text,
                    options: [],
                    range: range,
                    withTemplate: "\n\n" + label
                )
            }
        }

        while text.contains("\n\n\n") {
            text = text.replacingOccurrences(of: "\n\n\n", with: "\n\n")
        }
        if trimEdges {
            return text.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return text
    }

    func setFollowUpEnabled(_ enabled: Bool) {
        followField.isEnabled = enabled
        sendButton.isEnabled = enabled
        followChrome.alphaValue = enabled ? 1 : 0.55
        sendButton.alphaValue = enabled ? 1 : 0.55
    }

    func clearFollowUp() {
        followField.stringValue = ""
        if let editor = followField.currentEditor() as? NSTextView {
            editor.string = ""
        }
        setFollowUpEnabled(false)
    }

    func control(
        _ control: NSControl,
        textView: NSTextView,
        doCommandBy commandSelector: Selector
    ) -> Bool {
        if commandSelector == #selector(NSResponder.insertNewline(_:)) {
            submitFollowUp()
            return true
        }
        return false
    }

    @objc private func sendFollowUp() {
        submitFollowUp()
    }

    private func submitFollowUp() {
        let raw = currentFollowUpText().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty else { return }
        let question = String(raw.prefix(1000))
        guard onFollowUp?(question) == true else { return }
        followField.stringValue = ""
        if let editor = followField.currentEditor() as? NSTextView {
            editor.string = ""
        }
    }

    private func currentFollowUpText() -> String {
        if let editor = followField.currentEditor() as? NSTextView {
            return editor.string
        }
        return followField.stringValue
    }

    @objc private func dismissTapped() {
        onDismiss?()
    }

    override func mouseDown(with event: NSEvent) {
        // Keep clicks inside the bubble from falling through.
    }
}
