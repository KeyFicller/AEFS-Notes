import Foundation
import Network

enum InboxHTTPStatus: Int {
    case ok = 200
    case accepted = 202
    case badRequest = 400
    case notFound = 404
    case payloadTooLarge = 413
    case tooMany = 429
    case serverError = 500

    var reason: String {
        switch self {
        case .ok: return "OK"
        case .accepted: return "Accepted"
        case .badRequest: return "Bad Request"
        case .notFound: return "Not Found"
        case .payloadTooLarge: return "Payload Too Large"
        case .tooMany: return "Too Many Requests"
        case .serverError: return "Internal Server Error"
        }
    }
}

final class InboxServer {
    static let maxBody = 8 * 1024 * 1024
    private static let maxHeader = 64 * 1024

    private var listener: NWListener?
    var enqueue: ((Data) -> InboxEnqueueResult)?
    var count: (() -> Int)?

    func start(port: Int) {
        guard port > 0, port <= 65535 else { return }
        guard let nwPort = NWEndpoint.Port(rawValue: UInt16(port)) else { return }
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        params.requiredLocalEndpoint = NWEndpoint.hostPort(
            host: .ipv4(.loopback),
            port: nwPort
        )
        do {
            // Port is already on params.requiredLocalEndpoint; passing `on:` again
            // makes NWListener throw POSIX EINVAL.
            let listener = try NWListener(using: params)
            self.listener = listener
            listener.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    fputs("DeskPet: inbox listening on 127.0.0.1:\(port)\n", stderr)
                case .failed(let error):
                    fputs("DeskPet: inbox listen failed: \(error)\n", stderr)
                default:
                    break
                }
            }
            listener.newConnectionHandler = { [weak self] connection in
                self?.handle(connection)
            }
            listener.start(queue: .global(qos: .utility))
        } catch {
            fputs("DeskPet: inbox port \(port) unavailable: \(error)\n", stderr)
        }
    }

    private func handle(_ connection: NWConnection) {
        connection.start(queue: .global(qos: .utility))
        receive(connection, buffer: Data())
    }

    private func receive(_ connection: NWConnection, buffer: Data) {
        let remaining = Self.maxBody + Self.maxHeader - buffer.count
        guard remaining > 0 else {
            reply(connection, .payloadTooLarge, "0\n")
            return
        }
        connection.receive(minimumIncompleteLength: 1, maximumLength: remaining) { [weak self] chunk, _, isComplete, error in
            guard let self else { return }
            if error != nil {
                connection.cancel()
                return
            }
            var next = buffer
            if let chunk, !chunk.isEmpty {
                next.append(chunk)
            }
            if let headerEnd = Self.headerEnd(in: next) {
                self.finishRequest(connection, raw: next, headerEnd: headerEnd)
                return
            }
            if isComplete {
                self.reply(connection, .badRequest, "0\n")
                return
            }
            self.receive(connection, buffer: next)
        }
    }

    private func finishRequest(_ connection: NWConnection, raw: Data, headerEnd: Int) {
        guard let headerText = String(data: raw.prefix(headerEnd), encoding: .utf8) else {
            reply(connection, .badRequest, "0\n")
            return
        }
        let lines = headerText.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        guard let request = lines.first else {
            reply(connection, .badRequest, "0\n")
            return
        }
        let parts = request.split(separator: " ")
        guard parts.count >= 2 else {
            reply(connection, .badRequest, "0\n")
            return
        }
        let method = String(parts[0])
        let path = String(parts[1])
        var headers: [String: String] = [:]
        for line in lines.dropFirst() where line.contains(":") {
            let pair = line.split(separator: ":", maxSplits: 1)
            guard pair.count == 2 else { continue }
            headers[pair[0].trimmingCharacters(in: .whitespaces).lowercased()] =
                pair[1].trimmingCharacters(in: .whitespaces)
        }

        guard path == "/inbox" else {
            reply(connection, .notFound, "0\n")
            return
        }

        if method == "GET" {
            let n = count?() ?? 0
            reply(connection, .ok, "\(n)\n")
            return
        }
        if method != "POST" {
            reply(connection, .notFound, "0\n")
            return
        }

        let length = Int(headers["content-length"] ?? "") ?? -1
        guard length >= 0 else {
            reply(connection, .badRequest, "0\n")
            return
        }
        if length > Self.maxBody {
            reply(connection, .payloadTooLarge, "0\n")
            return
        }

        let bodyStart = headerEnd + 4
        let have = raw.count - bodyStart
        if have < length {
            readBody(connection, raw: raw, needed: bodyStart + length, headers: headers)
            return
        }
        let body = raw.subdata(in: bodyStart..<(bodyStart + length))
        accept(connection, body: body, contentType: headers["content-type"] ?? "")
    }

    private func readBody(_ connection: NWConnection, raw: Data, needed: Int, headers: [String: String]) {
        let missing = needed - raw.count
        guard missing > 0 else {
            let headerEnd = Self.headerEnd(in: raw) ?? 0
            let bodyStart = headerEnd + 4
            let length = needed - bodyStart
            let body = raw.subdata(in: bodyStart..<(bodyStart + length))
            accept(connection, body: body, contentType: headers["content-type"] ?? "")
            return
        }
        if needed > Self.maxBody + Self.maxHeader {
            reply(connection, .payloadTooLarge, "0\n")
            return
        }
        connection.receive(minimumIncompleteLength: missing, maximumLength: missing) { [weak self] chunk, _, _, error in
            guard let self else { return }
            if error != nil {
                connection.cancel()
                return
            }
            var next = raw
            if let chunk { next.append(chunk) }
            self.readBody(connection, raw: next, needed: needed, headers: headers)
        }
    }

    private func accept(_ connection: NWConnection, body: Data, contentType: String) {
        guard let image = Self.extractImage(from: body, contentType: contentType) else {
            reply(connection, .badRequest, "0\n")
            return
        }
        if image.count > Self.maxBody {
            reply(connection, .payloadTooLarge, "0\n")
            return
        }
        guard let enqueue else {
            reply(connection, .serverError, "0\n")
            return
        }
        switch enqueue(image) {
        case .accepted(let n):
            reply(connection, .accepted, "\(n)\n")
        case .full:
            reply(connection, .tooMany, "0\n")
        case .invalidImage:
            reply(connection, .badRequest, "0\n")
        }
    }

    private func reply(_ connection: NWConnection, _ status: InboxHTTPStatus, _ body: String) {
        let data = Data(body.utf8)
        let head = """
        HTTP/1.1 \(status.rawValue) \(status.reason)\r
        Content-Type: text/plain; charset=utf-8\r
        Content-Length: \(data.count)\r
        Connection: close\r
        \r

        """
        var packet = Data(head.utf8)
        packet.append(data)
        connection.send(content: packet, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }

    private static func headerEnd(in data: Data) -> Int? {
        let needle = Data([13, 10, 13, 10])
        guard let range = data.range(of: needle) else { return nil }
        return range.lowerBound
    }

    static func extractImage(from body: Data, contentType: String) -> Data? {
        if contentType.lowercased().hasPrefix("multipart/") {
            return firstMultipartFile(body, contentType: contentType)
        }
        return InboxQueue.isImage(body) ? body : nil
    }

    private static func firstMultipartFile(_ body: Data, contentType: String) -> Data? {
        guard let boundary = multipartBoundary(contentType) else { return nil }
        let marker = Data("--\(boundary)".utf8)
        var search = body.startIndex
        while let start = body.range(of: marker, in: search..<body.endIndex) {
            var partStart = start.upperBound
            if partStart + 1 < body.endIndex, body[partStart] == 13, body[partStart + 1] == 10 {
                partStart += 2
            }
            let closer = Data("\r\n--\(boundary)".utf8)
            let partEnd = body.range(of: closer, in: partStart..<body.endIndex)?.lowerBound ?? body.endIndex
            let part = body.subdata(in: partStart..<partEnd)
            search = partEnd
            if part.starts(with: Data("--".utf8)) { break }
            guard let split = part.range(of: Data([13, 10, 13, 10])) else { continue }
            let headers = String(data: part.prefix(upTo: split.lowerBound), encoding: .utf8) ?? ""
            let payload = part.suffix(from: split.upperBound)
            let named = headers.lowercased().contains("filename=")
            if named || InboxQueue.isImage(Data(payload)) {
                return InboxQueue.isImage(Data(payload)) ? Data(payload) : nil
            }
        }
        return nil
    }

    private static func multipartBoundary(_ contentType: String) -> String? {
        let pieces = contentType.split(separator: ";")
        for piece in pieces {
            let trimmed = piece.trimmingCharacters(in: .whitespaces)
            if trimmed.lowercased().hasPrefix("boundary=") {
                var value = String(trimmed.dropFirst("boundary=".count))
                if value.hasPrefix("\"") && value.hasSuffix("\"") && value.count >= 2 {
                    value = String(value.dropFirst().dropLast())
                }
                return value
            }
        }
        return nil
    }
}
