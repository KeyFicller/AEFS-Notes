import ApplicationServices
import AppKit
import Foundation

enum AccessibilityAuth {
    static var isTrusted: Bool {
        AXIsProcessTrusted()
    }

    /// Opens the system prompt / settings path for Accessibility.
    @discardableResult
    static func promptIfNeeded() -> Bool {
        let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        return AXIsProcessTrustedWithOptions(opts)
    }

    static func openSettings() {
        let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
        NSWorkspace.shared.open(url)
    }
}

enum SelectedTextReader {
    static let maxChars = 200

    struct AccessibilityProbe {
        var text: String?
        /// Hit-tested element looks like a text surface, so a copy fallback is reasonable.
        var looksTextual: Bool
    }

    /// Focused-element AX only. Used on mouseDown; keep it cheap (no AppleScript, no copy).
    static func axSelectionSnapshot() -> String? {
        guard let element = frontmostFocusedElement() else { return nil }
        return readSelection(from: element)
    }

    /// Call on the main thread. Browsers expose the selection as a text-marker range,
    /// not `AXSelectedText`, which is why a Safari-only JavaScript path used to be the
    /// only thing that worked.
    static func accessibilityProbe(near cocoaPoint: NSPoint) -> AccessibilityProbe {
        var text: String?
        var looksTextual = false
        var secure = false
        var seen: [AXUIElement] = []

        func consider(_ element: AXUIElement) {
            if seen.contains(where: { CFEqual($0, element) }) { return }
            seen.append(element)
            AXUIElementSetMessagingTimeout(element, 0.2)
            if isSecure(element) {
                secure = true
                return
            }
            if isTextual(element) { looksTextual = true }
            if text == nil {
                text = readSelection(from: element)
            }
        }

        var current = element(at: cocoaPoint)
        var depth = 0
        while let element = current, depth < 8, text == nil, !secure {
            let role = role(of: element)
            if role == "AXApplication" { break }
            consider(element)
            if role == "AXWindow" { break }
            current = parent(of: element)
            depth += 1
        }
        if text == nil, !secure, let focused = frontmostFocusedElement() {
            consider(focused)
        }
        if secure {
            return AccessibilityProbe(text: nil, looksTextual: false)
        }
        return AccessibilityProbe(text: text, looksTextual: looksTextual)
    }

    /// AppleScript, then a simulated Copy. Call off the main thread.
    static func fallbackSelection(allowCopy: Bool) -> String? {
        if let text = browserJavaScriptSelection() { return text }
        guard allowCopy else { return nil }
        return selectionByCopy()
    }

    private static func frontmostFocusedElement() -> AXUIElement? {
        guard let pid = NSWorkspace.shared.frontmostApplication?.processIdentifier else {
            return nil
        }
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, 0.2)
        return focusedElement(of: app)
    }

    private static func focusedElement(of element: AXUIElement) -> AXUIElement? {
        var focusedRef: CFTypeRef?
        let status = AXUIElementCopyAttributeValue(
            element,
            kAXFocusedUIElementAttribute as CFString,
            &focusedRef
        )
        guard status == .success, let focusedRef, CFGetTypeID(focusedRef) == AXUIElementGetTypeID() else {
            return nil
        }
        return (focusedRef as! AXUIElement)
    }

    /// Cocoa points grow upward from the primary display; AX points grow downward from its top.
    private static func axPoint(from cocoa: NSPoint) -> CGPoint {
        let primaryHeight = NSScreen.screens.first { $0.frame.origin == .zero }?.frame.height
            ?? NSScreen.main?.frame.height
            ?? 0
        return CGPoint(x: cocoa.x, y: primaryHeight - cocoa.y)
    }

    private static func element(at cocoaPoint: NSPoint) -> AXUIElement? {
        let system = AXUIElementCreateSystemWide()
        AXUIElementSetMessagingTimeout(system, 0.2)
        let point = axPoint(from: cocoaPoint)
        var element: AXUIElement?
        let status = AXUIElementCopyElementAtPosition(system, Float(point.x), Float(point.y), &element)
        guard status == .success else { return nil }
        return element
    }

    private static func parent(of element: AXUIElement) -> AXUIElement? {
        var parentRef: CFTypeRef?
        let status = AXUIElementCopyAttributeValue(element, kAXParentAttribute as CFString, &parentRef)
        guard status == .success, let parentRef, CFGetTypeID(parentRef) == AXUIElementGetTypeID() else {
            return nil
        }
        return (parentRef as! AXUIElement)
    }

    private static func role(of element: AXUIElement) -> String? {
        var roleRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, kAXRoleAttribute as CFString, &roleRef) == .success else {
            return nil
        }
        return roleRef as? String
    }

    private static func isSecure(_ element: AXUIElement) -> Bool {
        var subroleRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, kAXSubroleAttribute as CFString, &subroleRef) == .success else {
            return false
        }
        return (subroleRef as? String) == "AXSecureTextField"
    }

    private static let textualRoles: Set<String> = [
        "AXTextArea", "AXTextField", "AXStaticText", "AXComboBox", "AXWebArea",
    ]
    /// Not exported as Swift constants; WebKit/Blink/Gecko publish selection this way.
    private static let selectedTextMarkerRange = "AXSelectedTextMarkerRange"
    private static let stringForTextMarkerRange = "AXStringForTextMarkerRange"

    private static func isTextual(_ element: AXUIElement) -> Bool {
        if let role = role(of: element), textualRoles.contains(role) { return true }
        var names: CFArray?
        guard AXUIElementCopyAttributeNames(element, &names) == .success,
              let list = names as? [String] else { return false }
        return list.contains(kAXSelectedTextAttribute)
            || list.contains(kAXSelectedTextRangeAttribute)
            || list.contains(selectedTextMarkerRange)
    }

    private static func readSelection(from element: AXUIElement) -> String? {
        if let text = plainSelectedText(of: element) { return text }
        if let text = stringForSelectedRange(of: element) { return text }
        return stringForTextMarkerRange(of: element)
    }

    private static func plainSelectedText(of element: AXUIElement) -> String? {
        var selectedRef: CFTypeRef?
        let status = AXUIElementCopyAttributeValue(
            element,
            kAXSelectedTextAttribute as CFString,
            &selectedRef
        )
        guard status == .success, let selectedRef else { return nil }
        return sanitize(string(from: selectedRef) ?? "")
    }

    /// Cocoa text views sometimes publish a range instead of `AXSelectedText`.
    private static func stringForSelectedRange(of element: AXUIElement) -> String? {
        var rangeRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            element,
            kAXSelectedTextRangeAttribute as CFString,
            &rangeRef
        ) == .success, let rangeRef else { return nil }
        var value: CFTypeRef?
        guard AXUIElementCopyParameterizedAttributeValue(
            element,
            kAXStringForRangeParameterizedAttribute as CFString,
            rangeRef,
            &value
        ) == .success, let value else { return nil }
        return sanitize(string(from: value) ?? "")
    }

    /// WebKit, Blink, and Gecko leave `AXSelectedText` empty and publish a marker range.
    private static func stringForTextMarkerRange(of element: AXUIElement) -> String? {
        var markerRange: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            element,
            selectedTextMarkerRange as CFString,
            &markerRange
        ) == .success, let markerRange, CFGetTypeID(markerRange) == AXTextMarkerRangeGetTypeID() else {
            return nil
        }
        var value: CFTypeRef?
        guard AXUIElementCopyParameterizedAttributeValue(
            element,
            stringForTextMarkerRange as CFString,
            markerRange,
            &value
        ) == .success, let value else { return nil }
        return sanitize(string(from: value) ?? "")
    }

    private static func string(from value: CFTypeRef) -> String? {
        if let text = value as? String { return text }
        if let attributed = value as? NSAttributedString { return attributed.string }
        return nil
    }

    /// Safari / Chromium often leave AX selected-text empty; JS selection works with Automation permission.
    private static func browserJavaScriptSelection() -> String? {
        guard let bundleID = NSWorkspace.shared.frontmostApplication?.bundleIdentifier else {
            return nil
        }
        let script: String?
        switch bundleID {
        case "com.apple.Safari":
            script = """
            tell application "Safari"
              if (count of windows) is 0 then return ""
              try
                do JavaScript "window.getSelection().toString()" in current tab of front window
              on error
                return ""
              end try
            end tell
            """
        case "com.google.Chrome", "com.google.Chrome.canary":
            script = """
            tell application "Google Chrome"
              if (count of windows) is 0 then return ""
              try
                execute active tab of front window javascript "window.getSelection().toString()"
              on error
                return ""
              end try
            end tell
            """
        case "company.thebrowser.Browser", "com.brave.Browser", "com.microsoft.edgemac":
            // Best-effort Chromium forks via Chrome AppleScript suite when available.
            script = """
            tell application id "\(bundleID)"
              try
                execute active tab of front window javascript "window.getSelection().toString()"
              on error
                return ""
              end try
            end tell
            """
        default:
            script = nil
        }
        guard let script else { return nil }
        return runAppleScript(script)
    }

    private static func runAppleScript(_ source: String) -> String? {
        var error: NSDictionary?
        guard let appleScript = NSAppleScript(source: source) else { return nil }
        let result = appleScript.executeAndReturnError(&error)
        if let error {
            // First Safari use usually needs Automation permission; keep quiet after that.
            let message = error[NSAppleScript.errorMessage] as? String ?? "\(error)"
            fputs("DeskPet: browser selection AppleScript failed: \(message)\n", stderr)
            return nil
        }
        return sanitize(result.stringValue ?? "")
    }

    /// Last resort for apps that never publish a selection (Electron, WeChat, Firefox, …).
    /// The previous clipboard is restored after the read.
    private static func selectionByCopy() -> String? {
        let pasteboard = NSPasteboard.general
        let hadItems = !(pasteboard.pasteboardItems ?? []).isEmpty
        let backup = backupPasteboard(pasteboard)
        // Promised items sometimes can't be snapshotted. Don't clear the clipboard then.
        if hadItems && backup.isEmpty { return nil }
        pasteboard.clearContents()
        let cleared = pasteboard.changeCount
        postCommandC()
        let deadline = Date().addingTimeInterval(0.45)
        while pasteboard.changeCount == cleared && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.02)
        }
        let copied: String?
        if pasteboard.changeCount != cleared {
            copied = sanitize(pasteboard.string(forType: .string) ?? "")
        } else {
            copied = nil
        }
        restorePasteboard(pasteboard, backup)
        return copied
    }

    private static func postCommandC() {
        guard let source = CGEventSource(stateID: .hidSystemState) else { return }
        let commandKey: CGKeyCode = 0x37
        let cKey: CGKeyCode = 0x08
        let commandDown = CGEvent(keyboardEventSource: source, virtualKey: commandKey, keyDown: true)
        let cDown = CGEvent(keyboardEventSource: source, virtualKey: cKey, keyDown: true)
        cDown?.flags = .maskCommand
        let cUp = CGEvent(keyboardEventSource: source, virtualKey: cKey, keyDown: false)
        cUp?.flags = .maskCommand
        let commandUp = CGEvent(keyboardEventSource: source, virtualKey: commandKey, keyDown: false)
        commandDown?.post(tap: .cghidEventTap)
        cDown?.post(tap: .cghidEventTap)
        cUp?.post(tap: .cghidEventTap)
        commandUp?.post(tap: .cghidEventTap)
    }

    private static func backupPasteboard(_ pasteboard: NSPasteboard) -> [NSPasteboardItem] {
        (pasteboard.pasteboardItems ?? []).compactMap { item in
            let copy = NSPasteboardItem()
            for type in item.types {
                guard let data = item.data(forType: type) else { continue }
                copy.setData(data, forType: type)
            }
            return copy.types.isEmpty ? nil : copy
        }
    }

    private static func restorePasteboard(_ pasteboard: NSPasteboard, _ items: [NSPasteboardItem]) {
        pasteboard.clearContents()
        if !items.isEmpty {
            pasteboard.writeObjects(items)
        }
    }

    private static func sanitize(_ raw: String) -> String? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, text.count <= maxChars else { return nil }
        return text
    }
}

/// Watches drag-select (划词) and reports short selections near the cursor.
/// Plain clicks — even when leftover AX selected text exists — do not show the chip.
final class SelectionWatcher {
    var onSelection: ((String, NSPoint) -> Void)?
    /// Fired on left-mouse-down outside DeskPet so the chip can dismiss.
    var onClickBegan: (() -> Void)?
    /// Return true when the point lies over DeskPet UI (skip).
    var shouldIgnorePoint: ((NSPoint) -> Bool)?

    private var localMonitor: Any?
    private var globalMonitor: Any?
    private var pending: DispatchWorkItem?
    private let debounce: TimeInterval = 0.18
    /// Minimum drag distance (points) to treat mouse-up as a text selection gesture.
    private let minDragDistance: CGFloat = 10
    private var mouseDownPoint: NSPoint?
    private var mouseUpPoint: NSPoint?
    private var selectionAtMouseDown: String?
    private var didDrag = false

    func start() {
        stop()
        let mask: NSEvent.EventTypeMask = [.leftMouseDown, .leftMouseUp, .leftMouseDragged]
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: mask) { [weak self] event in
            self?.handle(event)
            return event
        }
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: mask) { [weak self] event in
            self?.handle(event)
        }
    }

    func stop() {
        pending?.cancel()
        pending = nil
        mouseDownPoint = nil
        mouseUpPoint = nil
        selectionAtMouseDown = nil
        didDrag = false
        if let localMonitor {
            NSEvent.removeMonitor(localMonitor)
            self.localMonitor = nil
        }
        if let globalMonitor {
            NSEvent.removeMonitor(globalMonitor)
            self.globalMonitor = nil
        }
    }

    private func handle(_ event: NSEvent) {
        switch event.type {
        case .leftMouseDown:
            let point = NSEvent.mouseLocation
            mouseDownPoint = point
            mouseUpPoint = nil
            didDrag = false
            pending?.cancel()
            pending = nil
            // Snapshot current selection so leftover text after a plain click is ignored.
            // AX-only: avoid AppleScript on every mouseDown.
            selectionAtMouseDown = AccessibilityAuth.isTrusted
                ? SelectedTextReader.axSelectionSnapshot()
                : nil
            if shouldIgnorePoint?(point) != true {
                onClickBegan?()
            }
        case .leftMouseDragged:
            guard let down = mouseDownPoint else { return }
            let point = NSEvent.mouseLocation
            if hypot(point.x - down.x, point.y - down.y) >= minDragDistance {
                didDrag = true
            }
        case .leftMouseUp:
            mouseUpPoint = NSEvent.mouseLocation
            scheduleCheck()
        default:
            break
        }
    }

    private func scheduleCheck() {
        pending?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.checkSelection()
        }
        pending = work
        DispatchQueue.main.asyncAfter(deadline: .now() + debounce, execute: work)
    }

    private func checkSelection() {
        let point = mouseUpPoint ?? NSEvent.mouseLocation
        let dragged = didDrag
        let previous = selectionAtMouseDown
        mouseDownPoint = nil
        mouseUpPoint = nil
        selectionAtMouseDown = nil
        didDrag = false

        if shouldIgnorePoint?(point) == true { return }
        // Require a real drag-select. Plain clicks on cards/tags must not open the chip
        // even if AX still reports previously selected text.
        guard dragged else { return }
        guard AccessibilityAuth.isTrusted else { return }

        let probe = SelectedTextReader.accessibilityProbe(near: point)
        if let text = probe.text {
            // Ignore unchanged leftover selection after a drag that didn't re-select.
            guard text != previous else { return }
            onSelection?(text, point)
            return
        }

        // Browser JS and simulated Copy can block — keep them off the main thread.
        let allowCopy = probe.looksTextual
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let text = SelectedTextReader.fallbackSelection(allowCopy: allowCopy)
            DispatchQueue.main.async {
                guard let text, text != previous else { return }
                self?.onSelection?(text, point)
            }
        }
    }
}
