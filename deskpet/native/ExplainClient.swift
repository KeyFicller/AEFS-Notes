import Foundation

enum ExplainError: LocalizedError {
    case missingAPIKey
    case badURL
    case httpStatus(Int, String)
    case emptyReply
    case decode

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
        promptTemplate: "你是AI领域专家，通俗的为学生解释{简写}"
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

final class ExplainClient {
    private let session: URLSession
    private var task: URLSessionDataTask?

    init(session: URLSession = .shared) {
        self.session = session
    }

    func cancel() {
        task?.cancel()
        task = nil
    }

    static func resolveAPIKey(root: URL = deskpetRoot()) -> String? {
        LocalEnv.value("DEEPSEEK_API_KEY", root: root)
    }

    func explain(
        term: String,
        config: ExplainConfig,
        completion: @escaping (Result<String, Error>) -> Void
    ) {
        cancel()
        guard let apiKey = Self.resolveAPIKey(), !apiKey.isEmpty else {
            completion(.failure(ExplainError.missingAPIKey))
            return
        }

        let base = config.apiBase.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: base + "/chat/completions") else {
            completion(.failure(ExplainError.badURL))
            return
        }

        let prompt = config.promptTemplate.replacingOccurrences(of: "{简写}", with: term)
        let body: [String: Any] = [
            "model": config.model,
            "messages": [
                ["role": "user", "content": prompt],
            ],
            "stream": false,
        ]
        guard let payload = try? JSONSerialization.data(withJSONObject: body) else {
            completion(.failure(ExplainError.decode))
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.httpBody = payload
        request.timeoutInterval = 60

        let work = session.dataTask(with: request) { [weak self] data, response, error in
            defer { self?.task = nil }
            if let error = error as NSError?, error.code == NSURLErrorCancelled {
                return
            }
            if let error {
                DispatchQueue.main.async { completion(.failure(error)) }
                return
            }
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            let raw = data.flatMap { String(data: $0, encoding: .utf8) } ?? ""
            guard (200..<300).contains(code) else {
                DispatchQueue.main.async {
                    completion(.failure(ExplainError.httpStatus(code, raw)))
                }
                return
            }
            guard let data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let choices = json["choices"] as? [[String: Any]],
                  let message = choices.first?["message"] as? [String: Any],
                  let content = message["content"] as? String
            else {
                DispatchQueue.main.async { completion(.failure(ExplainError.decode)) }
                return
            }
            let text = content.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else {
                DispatchQueue.main.async { completion(.failure(ExplainError.emptyReply)) }
                return
            }
            DispatchQueue.main.async { completion(.success(text)) }
        }
        task = work
        work.resume()
    }
}
