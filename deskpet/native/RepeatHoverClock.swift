import Foundation

struct RepeatHoverClock {
    private var stamps: [Date] = []

    mutating func hoverBegan(at now: Date = Date()) {
        stamps.append(now)
    }

    mutating func tick(at now: Date = Date(), windowMinutes: Double) {
        prune(now: now, windowMinutes: windowMinutes)
    }

    func isActive(at now: Date = Date(), afterHovers: Int, windowMinutes: Double) -> Bool {
        if afterHovers <= 0 || windowMinutes <= 0 { return false }
        return stamps.filter { now.timeIntervalSince($0) <= windowMinutes * 60 }.count >= afterHovers
    }

    private mutating func prune(now: Date, windowMinutes: Double) {
        let window = max(windowMinutes, 0) * 60
        stamps.removeAll { now.timeIntervalSince($0) > window }
    }
}
