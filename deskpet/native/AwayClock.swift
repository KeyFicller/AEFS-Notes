import Foundation

struct AwayClock {
    private var lastIdleAt: Date
    private var hovering = false
    private(set) var isAway = false

    init(now: Date = Date()) {
        lastIdleAt = now
    }

    mutating func markInteracted(at now: Date = Date()) {
        lastIdleAt = now
        isAway = false
    }

    mutating func hoverChanged(inside: Bool, at now: Date = Date()) {
        if inside {
            hovering = true
            isAway = false
        } else if hovering {
            hovering = false
            lastIdleAt = now
        }
    }

    mutating func tick(at now: Date = Date(), afterMinutes: Double, paused: Bool = false) {
        if paused || hovering || afterMinutes <= 0 || isAway { return }
        if now.timeIntervalSince(lastIdleAt) >= afterMinutes * 60 {
            isAway = true
        }
    }
}
