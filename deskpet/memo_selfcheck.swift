import AppKit
import Foundation

// Self-check for the memo retrieval plumbing (spawn helper → query → parse hits).
// Run from the repo root:
//   swiftc -O -o /tmp/memo_selfcheck -framework AppKit deskpet/memo_selfcheck.swift \
//     deskpet/native/MemoSearch.swift && /tmp/memo_selfcheck
@main
struct MemoSelfCheck {
    static func main() {
        let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        guard FileManager.default.fileExists(
            atPath: root.appendingPathComponent("notes/rag_retrieve.py").path
        ) else {
            print("run from the repo root")
            exit(2)
        }

        let client = MemoClient(root: root)
        var done = false

        client.onReady = { print("READY") }
        client.onFailure = { message in
            print("FAIL \(message)")
            done = true
        }
        client.onResults = { query, hits in
            print("QUERY \(query) hits=\(hits.count)")
            for hit in hits {
                let exists = FileManager.default.fileExists(atPath: hit.url.path)
                print("  \(exists ? "OK " : "MISSING ") \(hit.phase) | \(hit.title)")
            }
            done = hits.count > 0
        }

        client.query("langfuse 观测")

        let deadline = Date().addingTimeInterval(120)
        while !done && Date() < deadline {
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        }
        client.stop()
        print(done ? "DONE" : "TIMEOUT")
        exit(done ? 0 : 1)
    }
}
