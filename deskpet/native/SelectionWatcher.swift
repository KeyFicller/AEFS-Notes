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

    static func currentSelection() -> String? {
        if let text = axSelection() { return text }
        if let text = browserJavaScriptSelection() { return text }
        return nil
    }

    /// Prefer the frontmost app's focused element; fall back to system-wide focus.
    private static func axSelection() -> String? {
        if let pid = NSWorkspace.shared.frontmostApplication?.processIdentifier {
            let app = AXUIElementCreateApplication(pid)
            if let text = selectedText(fromFocusedOf: app) { return text }
            if let text = selectedTextAttribute(of: app) { return text }
        }
        let system = AXUIElementCreateSystemWide()
        return selectedText(fromFocusedOf: system)
    }

    private static func selectedText(fromFocusedOf element: AXUIElement) -> String? {
        var focusedRef: CFTypeRef?
        let status = AXUIElementCopyAttributeValue(
            element,
            kAXFocusedUIElementAttribute as CFString,
            &focusedRef
        )
        guard status == .success, let focusedRef else { return nil }
        return selectedTextAttribute(of: focusedRef as! AXUIElement)
    }

    private static func selectedTextAttribute(of element: AXUIElement) -> String? {
        var selectedRef: CFTypeRef?
        let status = AXUIElementCopyAttributeValue(
            element,
            kAXSelectedTextAttribute as CFString,
            &selectedRef
        )
        guard status == .success, let selectedRef else { return nil }
        let raw = (selectedRef as? String) ?? String(describing: selectedRef)
        return sanitize(raw)
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

    private static func sanitize(_ raw: String) -> String? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, text.count <= maxChars else { return nil }
        return text
    }
}

/// Watches mouse-up and reports short selections near the cursor.
final class SelectionWatcher {
    var onSelection: ((String, NSPoint) -> Void)?
    /// Return true when the point lies over DeskPet UI (skip).
    var shouldIgnorePoint: ((NSPoint) -> Bool)?

    private var localMonitor: Any?
    private var globalMonitor: Any?
    private var pending: DispatchWorkItem?
    private let debounce: TimeInterval = 0.18

    func start() {
        stop()
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseUp) { [weak self] event in
            self?.scheduleCheck()
            return event
        }
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .leftMouseUp) { [weak self] _ in
            self?.scheduleCheck()
        }
    }

    func stop() {
        pending?.cancel()
        pending = nil
        if let localMonitor {
            NSEvent.removeMonitor(localMonitor)
            self.localMonitor = nil
        }
        if let globalMonitor {
            NSEvent.removeMonitor(globalMonitor)
            self.globalMonitor = nil
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
        let point = NSEvent.mouseLocation
        if shouldIgnorePoint?(point) == true { return }
        guard AccessibilityAuth.isTrusted else { return }
        // Browser JS may block briefly on Automation prompt — keep off the hot path.
        DispatchQueue.global(qos: .userInitiated).async {
            let text = SelectedTextReader.currentSelection()
            DispatchQueue.main.async {
                guard let text else { return }
                self.onSelection?(text, point)
            }
        }
    }
}
