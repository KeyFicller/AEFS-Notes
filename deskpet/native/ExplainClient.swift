import Foundation

enum ExplainEvent {
    /// Text received so far. May be incomplete markdown.
    case partial(String)
    case success(String)
    case failure(Error)
}

enum ExplainError: LocalizedError {
    case missingAPIKey
    case badURL
    case httpStatus(Int, String)
    case emptyReply
    case decode
    case streamFailed(String)

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "未设置 DEEPSEEK_API_KEY（环境变量或 deskpet/local.env），无法解释。"
        case .badURL:
            return "解释接口地址无效。"
        case .httpStatus(let code, let body):
            let snippet = body.trimmingCharacters(in: .whitespacesAndNewlines)
            if snippet.isEmpty { return "接口返回 \(code)。" }
            return "接口返回 \(code)：\(snippet.prefix(160))"
        case .emptyReply:
            return "模型没有返回内容。"
        case .decode:
            return "无法解析模型回复。"
        case .streamFailed(let message):
            return message
        }
    }
}

struct ExplainConfig {
    var apiBase: String
    var model: String
    var promptTemplate: String

    static let defaults = ExplainConfig(
        apiBase: "https://api.deepseek.com",
        model: "deepseek-flash",
        promptTemplate: """
        你是AI领域专家，通俗地为学生解释「{简写}」。
        必须严格按下面三段输出，段与段之间空一行，不要合并成一段：

        一句话解释：
        （一句话说明它是什么）

        举例：
        （1～2个具体例子）

        总结：
        （一句收束，点明为什么要记住它）
        """
    )
}

enum LocalEnv {
    static func load(root: URL = deskpetRoot()) -> [String: String] {
        var values: [String: String] = [:]
        let file = root.appendingPathComponent("local.env")
        guard let raw = try? String(contentsOf: file, encoding: .utf8) else { return values }
        for line in raw.split(whereSeparator: \.isNewline) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty || trimmed.hasPrefix("#") { continue }
            guard let eq = trimmed.firstIndex(of: "=") else { continue }
            let key = trimmed[..<eq].trimmingCharacters(in: .whitespaces)
            var value = trimmed[trimmed.index(after: eq)...].trimmingCharacters(in: .whitespaces)
            if (value.hasPrefix("\"") && value.hasSuffix("\""))
                || (value.hasPrefix("'") && value.hasSuffix("'"))
            {
                value = String(value.dropFirst().dropLast())
            }
            if !key.isEmpty {
                values[key] = value
            }
        }
        return values
    }

    static func value(_ key: String, root: URL = deskpetRoot()) -> String? {
        if let env = ProcessInfo.processInfo.environment[key]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !env.isEmpty
        {
            return env
        }
        let fromFile = load(root: root)[key]?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let fromFile, !fromFile.isEmpty else { return nil }
        return fromFile
    }
}

struct ChatTurn {
    var role: String
    var content: String
}

final class ExplainClient {
    private let session: URLSession
    private let lock = NSLock()
    private var generation = 0
    private var streamTask: Task<Void, Never>?
    private var urlTask: URLSessionTask?

    init(session: URLSession = .shared) {
        self.session = session
    }

    func cancel() {
        let (old, url) = retire()
        old?.cancel()
        url?.cancel()
    }

    /// Bumps the generation so in-flight callbacks are ignored, and returns the previous tasks.
    private func retire() -> (Task<Void, Never>?, URLSessionTask?) {
        lock.lock()
        generation += 1
        let old = streamTask
        let url = urlTask
        streamTask = nil
        urlTask = nil
        lock.unlock()
        return (old, url)
    }

    private func trackURLTask(_ task: URLSessionTask, generation id: Int) {
        lock.lock()
        if generation == id {
            urlTask = task
            lock.unlock()
        } else {
            lock.unlock()
            task.cancel()
        }
    }

    private func generationMatches(_ id: Int) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return generation == id
    }

    static func resolveAPIKey(root: URL = deskpetRoot()) -> String? {
        LocalEnv.value("DEEPSEEK_API_KEY", root: root)
    }

    func complete(
        messages: [ChatTurn],
        config: ExplainConfig,
        onEvent: @escaping (ExplainEvent) -> Void
    ) {
        let (previous, previousURL) = retire()
        previous?.cancel()
        previousURL?.cancel()

        guard !messages.isEmpty else {
            onEvent(.failure(ExplainError.emptyReply))
            return
        }

        guard let apiKey = Self.resolveAPIKey(), !apiKey.isEmpty else {
            onEvent(.failure(ExplainError.missingAPIKey))
            return
        }

        let base = config.apiBase.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: base + "/chat/completions") else {
            onEvent(.failure(ExplainError.badURL))
            return
        }

        let body: [String: Any] = [
            "model": config.model,
            "messages": messages.map { ["role": $0.role, "content": $0.content] },
            "stream": true,
        ]
        guard let payload = try? JSONSerialization.data(withJSONObject: body) else {
            onEvent(.failure(ExplainError.decode))
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.httpBody = payload
        request.timeoutInterval = 60

        lock.lock()
        let id = generation
        lock.unlock()

        let task = Task { [weak self] in
            guard let self else { return }
            await self.stream(request: request, generation: id, onEvent: onEvent)
        }
        lock.lock()
        if generation == id {
            streamTask = task
        } else {
            task.cancel()
        }
        lock.unlock()
    }

    private func stream(
        request: URLRequest,
        generation id: Int,
        onEvent: @escaping (ExplainEvent) -> Void
    ) async {
        do {
            let (bytes, response) = try await session.bytes(for: request)
            trackURLTask(bytes.task, generation: id)
            if Task.isCancelled || !generationMatches(id) { return }

            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            if !(200..<300).contains(code) {
                var raw = ""
                for try await line in bytes.lines {
                    if Task.isCancelled || !generationMatches(id) { return }
                    if !raw.isEmpty { raw += "\n" }
                    raw += line
                    if raw.count > 2000 { break }
                }
                emit(.failure(ExplainError.httpStatus(code, raw)), generation: id, onEvent: onEvent)
                return
            }

            var accumulated = ""
            var rawFallback = ""
            var sawSSE = false
            var lastPartial = Date.distantPast
            lineLoop: for try await line in bytes.lines {
                if Task.isCancelled || !generationMatches(id) { return }
                switch Self.parseSSELine(line) {
                case .ignore:
                    if !sawSSE {
                        if !rawFallback.isEmpty { rawFallback += "\n" }
                        rawFallback += line
                    }
                case .done:
                    sawSSE = true
                    break lineLoop
                case .failure(let message):
                    emit(.failure(ExplainError.streamFailed(message)), generation: id, onEvent: onEvent)
                    return
                case .text(let piece):
                    sawSSE = true
                    accumulated += piece
                    let now = Date()
                    if now.timeIntervalSince(lastPartial) >= 0.04 {
                        lastPartial = now
                        emit(.partial(accumulated), generation: id, onEvent: onEvent)
                    }
                }
            }

            if !sawSSE {
                guard let text = Self.completionText(from: rawFallback) else {
                    emit(.failure(ExplainError.decode), generation: id, onEvent: onEvent)
                    return
                }
                accumulated = text
            }

            let text = accumulated.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else {
                emit(.failure(ExplainError.emptyReply), generation: id, onEvent: onEvent)
                return
            }
            emit(.success(text), generation: id, onEvent: onEvent)
        } catch {
            if Task.isCancelled || !generationMatches(id) { return }
            if error is CancellationError { return }
            if let urlError = error as? URLError, urlError.code == .cancelled { return }
            emit(.failure(error), generation: id, onEvent: onEvent)
        }
    }

    private func emit(
        _ event: ExplainEvent,
        generation id: Int,
        onEvent: @escaping (ExplainEvent) -> Void
    ) {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.generationMatches(id) else { return }
            onEvent(event)
        }
    }

    private enum SSELine {
        case ignore
        case done
        case text(String)
        case failure(String)
    }

    private static func parseSSELine(_ line: String) -> SSELine {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("data:") else { return .ignore }
        let payload = trimmed.dropFirst(5).trimmingCharacters(in: .whitespaces)
        if payload == "[DONE]" { return .done }
        guard let data = payload.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return .ignore }
        if let error = json["error"] as? [String: Any] {
            let message = (error["message"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
            return .failure(message?.isEmpty == false ? message! : "流式接口返回错误。")
        }
        guard let choices = json["choices"] as? [[String: Any]] else { return .ignore }
        let choice = choices.first
        if let delta = choice?["delta"] as? [String: Any],
           let content = delta["content"] as? String,
           !content.isEmpty
        {
            return .text(content)
        }
        if let message = choice?["message"] as? [String: Any],
           let content = message["content"] as? String,
           !content.isEmpty
        {
            return .text(content)
        }
        return .ignore
    }

    private static func completionText(from raw: String) -> String? {
        guard let data = raw.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let choices = json["choices"] as? [[String: Any]],
              let message = choices.first?["message"] as? [String: Any],
              let content = message["content"] as? String
        else { return nil }
        let text = content.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }
}
