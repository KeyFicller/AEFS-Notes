import Foundation

struct DisdainClock {
    private var lastIdleAt: Date
    private var hovering = false
    private(set) var isDisdain = false

    init(now: Date = Date()) {
        lastIdleAt = now
    }

    mutating func markInteracted(at now: Date = Date()) {
        lastIdleAt = now
        isDisdain = false
    }

    mutating func hoverChanged(inside: Bool, at now: Date = Date()) {
        if inside {
            hovering = true
            isDisdain = false
        } else if hovering {
            hovering = false
            lastIdleAt = now
        }
    }

    mutating func tick(at now: Date = Date(), afterMinutes: Double, paused: Bool = false) {
        if paused || hovering || afterMinutes <= 0 || isDisdain { return }
        if now.timeIntervalSince(lastIdleAt) >= afterMinutes * 60 {
            isDisdain = true
        }
    }
}
