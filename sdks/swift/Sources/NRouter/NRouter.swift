import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// nRouter client — one API key for models across six provider clouds.
///
/// The gateway speaks the OpenAI wire format, so request and response bodies
/// are the shapes you already know. This client adds the two things a raw
/// `URLSession` call cannot: key validation before egress, and the `x-nr-*`
/// metadata (cost, tokens, cache outcome) handed back beside every body.
///
/// ```swift
/// let client = try NRouter()                 // reads NROUTER_API_KEY
/// let result = try await client.chatCompletions([
///     "model": "claude-sonnet-4-5",
///     "messages": [["role": "user", "content": "Hello!"]],
/// ])
/// if let cost = result.meta.cost {
///     print("cost $\(cost)")
/// } else {
///     print("unpriced")                       // unpriced is unknown, not free
/// }
/// ```
public struct NRouter: Sendable {
    /// The gateway's customer surface. A dynamic value: override it for stage.
    public static let defaultBaseURL = "https://api.nrouter.ai/v1"
    /// The one environment variable this SDK reads.
    public static let envKey = "NROUTER_API_KEY"
    /// Every customer key carries this prefix.
    public static let keyPrefix = "sk-nrouter-"

    /// True when a model family is served on /v1/messages rather than /v1/chat/completions.
    public static func usesMessagesWire(_ model: String, provider: String? = nil) -> Bool {
        let m = model.lowercased()
        if m.contains("claude") || m.contains("anthropic") || m.contains("haiku") || m.contains("sonnet") || m.contains("opus") {
            return true
        }
        if let p = provider?.lowercased(), p.contains("anthropic") {
            return true
        }
        return false
    }

    // MARK: - Transport deadlines
    //
    // This client used to be built on `URLSession.shared`, which carries
    // Foundation's defaults: a 60 s request timeout and a SEVEN DAY resource
    // timeout. Sixty seconds is BELOW what the gateway may honestly take, so a
    // long completion or an image job was aborted here for a request the
    // gateway went on to finish and BILL; seven days is not a bound at all.
    // Every number below is an explicit decision — name it, or you have chosen
    // infinity — sized against the gateway's own budget rather than picked for
    // feel.
    //
    // The gateway's worst HONEST case before a first byte is roughly 410 s: up
    // to three provider attempts, each with a 10 s connect timeout and a 120 s
    // between-bytes read timeout, plus at most 20 s of cumulative backoff. A
    // client deadline below that aborts a request the gateway is about to
    // answer — and the customer is billed anyway, because the provider tokens
    // were already spent.
    //
    // None of these ever RETRIES. Waiting is bounded here; re-sending is not
    // done at all. The gateway reserves credit ONCE per customer request and
    // owns retry and failover, so a client retry of a billed POST is a second
    // call and a second bill with nothing to dedupe on.

    /// Longest gap BETWEEN BYTES before a task is abandoned — 180 s.
    ///
    /// `URLSessionConfiguration.timeoutIntervalForRequest` is a between-bytes
    /// timeout, not a whole-request one, which is why it is safe on a stream.
    /// 180 s sits above the gateway's own 120 s between-bytes read timeout, so
    /// the gateway's honest error reaches the caller instead of a client-side
    /// abort racing it.
    public static let defaultRequestTimeout: TimeInterval = 180

    /// Whole-request ceiling for BUFFERED calls (JSON and multipart) — 600 s.
    ///
    /// Above the gateway's ~410 s worst honest case with margin, and the same
    /// order as the OpenAI and Anthropic clients' own 600 s defaults, so a
    /// caller migrating from either is not surprised.
    public static let defaultResourceTimeout: TimeInterval = 600

    /// Whole-request ceiling for STREAMING and BINARY calls — 24 hours.
    ///
    /// A leak-stopper, NOT a request bound. `timeoutIntervalForResource` covers
    /// the response body, so applying the 600 s ceiling here would sever an SSE
    /// stream mid-generation and truncate a long `GET /videos/{id}/content` —
    /// both of them already billed. The bound that actually protects these
    /// calls is ``defaultRequestTimeout``, which fires when the bytes STOP.
    public static let defaultStreamingResourceTimeout: TimeInterval = 86_400

    /// The session buffered JSON and multipart calls use when none is injected.
    public static func makeDefaultSession() -> URLSession {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = defaultRequestTimeout
        configuration.timeoutIntervalForResource = defaultResourceTimeout
        return URLSession(configuration: configuration)
    }

    /// The session SSE streaming and binary downloads use when none is injected.
    public static func makeDefaultStreamingSession() -> URLSession {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = defaultRequestTimeout
        configuration.timeoutIntervalForResource = defaultStreamingResourceTimeout
        return URLSession(configuration: configuration)
    }

    // Built once and shared by every client, so the connection POOL is shared
    // too — the one property `URLSession.shared` had that a per-instance
    // session would quietly lose inside a timeout fix.
    private static let sharedSession = makeDefaultSession()
    private static let sharedStreamingSession = makeDefaultStreamingSession()

    public let baseURL: String
    private let apiKey: String
    private let session: URLSession
    private let streamingSession: URLSession

    /// A body paired with the metadata the gateway reported for it.
    ///
    /// Deliberately NOT `Sendable`: the body is `[String: Any]`, which the
    /// compiler cannot check, and `@unchecked Sendable` here would silence a
    /// real question rather than answer it. `meta` IS `Sendable`, so the part
    /// worth passing between actors — cost, tokens, request id — crosses
    /// freely; decode `body` into your own `Sendable` type to send that too.
    public struct Response {
        public let body: [String: Any]
        public let meta: NRouterResponseMeta
        public let statusCode: Int

        public init(body: [String: Any], meta: NRouterResponseMeta, statusCode: Int) {
            self.body = body
            self.meta = meta
            self.statusCode = statusCode
        }
    }

    /// One provider-native SSE frame plus portable incremental text.
    public struct StreamChunk: Sendable {
        public let event: String?
        public let delta: String
        /// The untouched JSON bytes for usage, finish, and provider-specific fields.
        public let data: Data

        public init(event: String?, delta: String, data: Data) {
            self.event = event
            self.delta = delta
            self.data = data
        }
    }

    /// Response metadata is available before the first streamed token arrives.
    public struct StreamResponse: Sendable {
        public let meta: NRouterResponseMeta
        public let statusCode: Int
        public let chunks: AsyncThrowingStream<StreamChunk, Error>

        public init(
            meta: NRouterResponseMeta,
            statusCode: Int,
            chunks: AsyncThrowingStream<StreamChunk, Error>
        ) {
            self.meta = meta
            self.statusCode = statusCode
            self.chunks = chunks
        }
    }

    /// Build a client. The key is validated up front so a malformed one fails
    /// here rather than as a 401 that reads like a revoked credential.
    ///
    /// - Parameters:
    ///   - apiKey: Explicit key. Falls back to `NROUTER_API_KEY`.
    ///   - baseURL: Gateway base URL. Defaults to production.
    ///   - session: Inject your own to control proxy, timeout, or caching. It
    ///     replaces BOTH default sessions unless `streamingSession` is also
    ///     given, so one injected session bounds every call the same way.
    ///   - streamingSession: Inject one separately to give SSE and binary
    ///     downloads different deadlines from buffered calls.
    public init(
        apiKey: String? = nil,
        baseURL: String = NRouter.defaultBaseURL,
        session: URLSession? = nil,
        streamingSession: URLSession? = nil
    ) throws {
        self.apiKey = try NRouter.resolveAPIKey(apiKey)
        self.baseURL = try NRouter.validateGatewayBaseURL(baseURL)
        self.session = session ?? NRouter.sharedSession
        self.streamingSession = streamingSession ?? session ?? NRouter.sharedStreamingSession
    }

    /// Parse and enforce transport boundary on gateway base URL.
    public static func validateGatewayBaseURL(_ value: String) throws -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.contains("\r") || trimmed.contains("\n") || trimmed.contains("\t") {
            throw NRouterError.configuration("Base URL contains invalid control characters or whitespace")
        }
        guard let url = URL(string: trimmed), let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased() else {
            throw NRouterError.configuration("Invalid base URL '\(value)'")
        }
        if url.user != nil || url.password != nil {
            throw NRouterError.configuration("nRouter gateway URL must not contain credentials")
        }
        if scheme != "http" && scheme != "https" {
            throw NRouterError.configuration("Invalid base URL scheme '\(scheme)'")
        }
        let normalizedHost = host.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        let isLoopback = normalizedHost == "localhost" || normalizedHost == "127.0.0.1" || normalizedHost == "::1" || normalizedHost == "0.0.0.0" || normalizedHost.hasSuffix(".local")
        if scheme == "http" && !isLoopback {
            throw NRouterError.configuration("nRouter gateway URL must use HTTPS; HTTP is allowed only for loopback development")
        }
        return trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed
    }

    /// Resolve and validate a key: explicit argument first, then environment.
    public static func resolveAPIKey(_ explicit: String? = nil) throws -> String {
        let key = explicit?.isEmpty == false
            ? explicit!
            : ProcessInfo.processInfo.environment[envKey] ?? ""
        guard !key.isEmpty else {
            throw NRouterError.configuration(
                "No nRouter API key: pass one explicitly or set \(envKey)."
            )
        }
        guard key.hasPrefix(keyPrefix) else {
            throw NRouterError.configuration(
                "nRouter API keys start with '\(keyPrefix)'; got one that does not."
            )
        }
        return key
    }

    // MARK: - Endpoints

    /// `POST /chat/completions`
    public func chatCompletions(_ body: [String: Any]) async throws -> Response {
        try await post("/chat/completions", body)
    }

    /// `POST /completions` — the legacy text-completions wire.
    public func completions(_ body: [String: Any]) async throws -> Response {
        try await post("/completions", body)
    }

    /// `POST /embeddings`
    public func embeddings(_ body: [String: Any]) async throws -> Response {
        try await post("/embeddings", body)
    }

    /// Normalizes body for the Anthropic Messages wire: extracts system messages into top-level system,
    /// maps max_completion_tokens to max_tokens, and normalizes stop sequences.
    public static func normalizeAnthropicMessages(_ body: [String: Any]) -> [String: Any] {
        var out = body

        if let messages = out["messages"] as? [[String: Any]] {
            var cleaned: [[String: Any]] = []
            var systemChunks: [String] = []

            if let existingSys = out["system"] as? String, !existingSys.isEmpty {
                systemChunks.append(existingSys)
            }

            for turn in messages {
                let role = (turn["role"] as? String ?? "").lowercased()
                if role == "system" || role == "developer" {
                    if let contentStr = turn["content"] as? String, !contentStr.isEmpty {
                        systemChunks.append(contentStr)
                    } else if let parts = turn["content"] as? [[String: Any]] {
                        for part in parts {
                            if (part["type"] as? String) == "text", let text = part["text"] as? String, !text.isEmpty {
                                systemChunks.append(text)
                            }
                        }
                    }
                    continue
                }
                cleaned.append(turn)
            }

            out["messages"] = cleaned
            if !systemChunks.isEmpty {
                out["system"] = systemChunks.joined(separator: "\n\n")
            }
        }

        if let maxComp = out.removeValue(forKey: "max_completion_tokens") {
            if out["max_tokens"] == nil {
                out["max_tokens"] = maxComp
            }
        }
        if out["max_tokens"] == nil {
            out["max_tokens"] = 4096
        }

        if let stopVal = out.removeValue(forKey: "stop") {
            if out["stop_sequences"] == nil {
                if let s = stopVal as? String, !s.isEmpty {
                    out["stop_sequences"] = [s]
                } else if let arr = stopVal as? [String] {
                    let valid = arr.filter { !$0.isEmpty }
                    if !valid.isEmpty {
                        out["stop_sequences"] = valid
                    }
                }
            }
        }

        return out
    }

    /// `POST /messages` — the Anthropic wire format the gateway also serves.
    public func messages(_ body: [String: Any]) async throws -> Response {
        try await post("/messages", Self.normalizeAnthropicMessages(body))
    }

    /// `POST /responses`
    public func responses(_ body: [String: Any]) async throws -> Response {
        try await post("/responses", body)
    }

    /// Incremental `POST /chat/completions`; forces `stream: true` in a copy.
    public func chatCompletionsStream(_ body: [String: Any]) async throws -> StreamResponse {
        try await stream("/chat/completions", body)
    }

    /// Incremental legacy `POST /completions`.
    public func completionsStream(_ body: [String: Any]) async throws -> StreamResponse {
        try await stream("/completions", body)
    }

    /// Incremental native Anthropic `POST /messages`.
    public func messagesStream(_ body: [String: Any]) async throws -> StreamResponse {
        try await stream("/messages", Self.normalizeAnthropicMessages(body))
    }

    /// Incremental `POST /responses`.
    public func responsesStream(_ body: [String: Any]) async throws -> StreamResponse {
        try await stream("/responses", body)
    }

    /// `POST /images/generations`
    public func imagesGenerations(_ body: [String: Any]) async throws -> Response {
        try await post("/images/generations", body)
    }

    /// `POST /messages/count_tokens` — counts input without generating.
    public func countTokens(_ body: [String: Any]) async throws -> Response {
        try await post("/messages/count_tokens", body)
    }

    /// `POST /audio/transcriptions` — Whisper-style speech to text.
    ///
    /// multipart/form-data, not JSON: the gateway requires a binary `file` part
    /// here, so the JSON helpers cannot reach this endpoint at all.
    ///
    /// `fileName` must carry the real extension — the upstream providers pick
    /// their decoder from it, so `"audio"` is rejected where `"speech.mp3"` is
    /// not.
    public func audioTranscriptions(
        file: Data,
        fileName: String,
        fields: [String: String] = [:]
    ) async throws -> Response {
        try await multipart("/audio/transcriptions", file: file, fileName: fileName, fields: fields)
    }

    /// `POST /audio/translations` — speech in any language to English text.
    public func audioTranslations(
        file: Data,
        fileName: String,
        fields: [String: String] = [:]
    ) async throws -> Response {
        try await multipart("/audio/translations", file: file, fileName: fileName, fields: fields)
    }

    /// `POST /audio/speech` — generated audio plus response metadata.
    public func audioSpeech(_ body: [String: Any]) async throws -> (
        data: Data, meta: NRouterResponseMeta, statusCode: Int
    ) {
        try await bytes("/audio/speech", body)
    }

    /// Any multipart `POST` under the gateway's `/v1` root.
    ///
    /// The boundary is caller-injectable ONLY so a test can assert a fixed
    /// body; leaving it nil generates a fresh one per request, which is what a
    /// caller wants.
    public func multipart(
        _ path: String,
        file: Data,
        fileName: String,
        fields: [String: String] = [:],
        filePartName: String = "file",
        boundary: String? = nil
    ) async throws -> Response {
        let boundary = boundary ?? "nrouter-\(UUID().uuidString)"
        let boundaryPunctuation = CharacterSet(charactersIn: "'()+_,-./:=?")
        let validBoundaryCharacters = CharacterSet.alphanumerics.union(boundaryPunctuation)
        guard !boundary.isEmpty,
              boundary.utf8.count <= 70,
              boundary.unicodeScalars.allSatisfy({
                  $0.isASCII && validBoundaryCharacters.contains($0)
              }) else {
            throw NRouterError.configuration(
                "multipart boundary must be 1...70 safe ASCII characters"
            )
        }
        var body = Data()

        // A Unix filename may legally contain a quote, and CR/LF would end the
        // header line early — letting a chosen filename inject extra multipart
        // parts. Escape per RFC 2616 quoted-string and drop the line breaks
        // outright, since neither can appear in a header value at all.
        func quoted(_ value: String) -> String {
            value
                .replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "\"", with: "\\\"")
                .replacingOccurrences(of: "\r", with: "")
                .replacingOccurrences(of: "\n", with: "")
        }

        func append(_ text: String) {
            body.append(Data(text.utf8))
        }

        // Sorted so the body is deterministic; a dictionary's order is not.
        for key in fields.keys.sorted() {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(quoted(key))\"\r\n\r\n")
            append("\(fields[key]!)\r\n")
        }
        append("--\(boundary)\r\n")
        append(
            "Content-Disposition: form-data; name=\"\(quoted(filePartName))\"; "
                + "filename=\"\(quoted(fileName))\"\r\n"
        )
        append("Content-Type: application/octet-stream\r\n\r\n")
        body.append(file)
        append("\r\n--\(boundary)--\r\n")

        var request = URLRequest(url: try url(path))
        request.httpMethod = "POST"
        request.setValue(
            "multipart/form-data; boundary=\(boundary)",
            forHTTPHeaderField: "Content-Type"
        )
        request.httpBody = body
        return try await send(request)
    }

    /// `GET /models` — what this key is allowed to route to.
    public func models() async throws -> Response {
        try await get("/models")
    }

    /// `GET /models/{model_id}` — one model visible to this key.
    public func model(_ modelID: String) async throws -> Response {
        try await get("/models/\(modelPath(modelID))")
    }

    /// `POST /videos` — starts a video generation job.
    public func createVideo(_ body: [String: Any]) async throws -> Response {
        try await post("/videos", body)
    }

    /// `GET /videos/{id}` — polls one video generation job.
    public func retrieveVideo(_ videoID: String) async throws -> Response {
        try await get("/videos/\(pathSegment(videoID))")
    }

    /// `GET /videos/{id}/content` — generated video bytes.
    public func downloadVideoContent(_ videoID: String) async throws -> (
        data: Data, meta: NRouterResponseMeta, statusCode: Int
    ) {
        try await bytes("/videos/\(pathSegment(videoID))/content")
    }

    /// Any `POST` path under the gateway's `/v1` root.
    public func post(_ path: String, _ body: [String: Any]) async throws -> Response {
        var request = URLRequest(url: try url(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await send(request)
    }

    /// Stream any JSON `POST` under the gateway's `/v1` root as SSE.
    public func stream(_ path: String, _ body: [String: Any]) async throws -> StreamResponse {
        var streamed = body
        streamed["stream"] = true
        var request = URLRequest(url: try url(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: streamed)
        NRouter.applyDeadline(&request, from: streamingSession)

        let bytes: URLSession.AsyncBytes
        let response: URLResponse
        do {
            (bytes, response) = try await streamingSession.bytes(for: request)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw NRouterError.transport(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw NRouterError.transport("Response was not HTTP.")
        }
        let meta = NRouterResponseMeta(response: http)
        guard (200..<300).contains(http.statusCode) else {
            var data = Data()
            for try await byte in bytes.prefix(1 << 20) { data.append(byte) }
            let parsed = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
            throw NRouterError.fromCode(
                NRouter.errorBody(status: http.statusCode, payload: parsed, meta: meta)
            )
        }
        let contentType = (http.value(forHTTPHeaderField: "content-type") ?? "").lowercased()
        guard contentType.contains("text/event-stream") else {
            throw NRouterError.transport(
                "nRouter returned \(http.statusCode) with content-type '\(contentType)', " +
                    "which is not an SSE stream."
            )
        }

        let chunks = AsyncThrowingStream<StreamChunk, Error> { continuation in
            let reader = Task {
                do {
                    var event: String?
                    var dataLines: [String] = []
                    var lineData = Data()
                    func processLine(_ rawLine: String) throws -> Bool {
                        let line = rawLine.hasSuffix("\r") ? String(rawLine.dropLast()) : rawLine
                        try Task.checkCancellation()
                        if line.isEmpty {
                            if dataLines.isEmpty {
                                event = nil
                                return false
                            }
                            let result = try NRouter.parseStreamFrame(
                                event: event,
                                data: dataLines.joined(separator: "\n"),
                                meta: meta
                            )
                            event = nil
                            dataLines.removeAll(keepingCapacity: true)
                            switch result {
                            case .chunk(let chunk): continuation.yield(chunk)
                            case .done:
                                continuation.finish()
                                return true
                            case .skip: return false
                            }
                            return false
                        }
                        if line.hasPrefix(":") { return false }
                        let pieces = line.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
                        let name = String(pieces[0])
                        let value = pieces.count == 2
                            ? (pieces[1].hasPrefix(" ") ? pieces[1].dropFirst() : pieces[1])
                            : Substring()
                        if name == "event" { event = String(value) }
                        if name == "data" { dataLines.append(String(value)) }
                        return false
                    }
                    var lastWasCR = false
                    for try await byte in bytes {
                        if byte == 0x0A {
                            if lastWasCR {
                                lastWasCR = false
                                continue
                            }
                            let line = String(data: lineData, encoding: .utf8) ?? ""
                            lineData.removeAll(keepingCapacity: true)
                            if try processLine(line) { return }
                        } else if byte == 0x0D {
                            let line = String(data: lineData, encoding: .utf8) ?? ""
                            lineData.removeAll(keepingCapacity: true)
                            lastWasCR = true
                            if try processLine(line) { return }
                        } else {
                            lastWasCR = false
                            lineData.append(byte)
                        }
                    }
                    if !lineData.isEmpty {
                        let line = String(data: lineData, encoding: .utf8) ?? ""
                        if try processLine(line) { return }
                    }
                    if !dataLines.isEmpty {
                        let result = try NRouter.parseStreamFrame(
                            event: event,
                            data: dataLines.joined(separator: "\n"),
                            meta: meta
                        )
                        if case .chunk(let chunk) = result {
                            continuation.yield(chunk)
                        } else if case .done = result {
                            continuation.finish()
                            return
                        }
                    }
                    continuation.finish(
                        throwing: NRouterError.transport(
                            "the stream ended before its terminal event"
                        )
                    )
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { @Sendable _ in reader.cancel() }
        }
        return StreamResponse(meta: meta, statusCode: http.statusCode, chunks: chunks)
    }

    /// Any `GET` path under the gateway's `/v1` root.
    public func get(_ path: String) async throws -> Response {
        var request = URLRequest(url: try url(path))
        request.httpMethod = "GET"
        return try await send(request)
    }

    /// Raw bytes plus metadata, for the endpoints that do not return JSON.
    ///
    /// `/v1/audio/speech` returns audio, `/v1/videos/{id}/content` returns a
    /// video, and `stream: true` returns SSE. The JSON helpers refuse those
    /// rather than handing back an empty body for a request you were billed
    /// for; this is the method that returns them.
    ///
    /// Runs on the STREAMING session: a download of generated video may
    /// legitimately outlast ``defaultResourceTimeout``, and cutting it off
    /// truncates a response that has already been billed.
    public func bytes(_ path: String, _ body: [String: Any]? = nil) async throws -> (
        data: Data, meta: NRouterResponseMeta, statusCode: Int
    ) {
        var request = URLRequest(url: try url(path))
        request.httpMethod = body == nil ? "GET" : "POST"
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        NRouter.applyDeadline(&request, from: streamingSession)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await streamingSession.data(for: request)
        } catch {
            throw NRouterError.transport(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw NRouterError.transport("Response was not HTTP.")
        }

        let meta = NRouterResponseMeta(response: http)
        if (200..<300).contains(http.statusCode) {
            return (data, meta, http.statusCode)
        }
        let parsed = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        throw NRouterError.fromCode(
            NRouter.errorBody(status: http.statusCode, payload: parsed, meta: meta)
        )
    }

    // MARK: - Internals

    /// Copy a session's between-bytes bound onto the request about to use it.
    ///
    /// `URLRequest(url:)` starts at Foundation's 60 s `timeoutInterval`, and a
    /// request-level timeout takes precedence over the session
    /// configuration's `timeoutIntervalForRequest`. Leaving it alone therefore
    /// keeps the very 60 s default this SDK moved off — the session's number
    /// would be set and silently unused, which is a control that reads as
    /// present and is not. Copying it also means an INJECTED session's bound
    /// is the one that applies, with no second number to keep in step.
    private static func applyDeadline(_ request: inout URLRequest, from session: URLSession) {
        request.timeoutInterval = session.configuration.timeoutIntervalForRequest
    }

    private func url(_ path: String) throws -> URL {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        guard let url = URL(string: "\(baseURL)/\(trimmed)") else {
            throw NRouterError.transport("Could not build a URL for \(baseURL)/\(trimmed).")
        }
        return url
    }

    private func pathSegment(_ value: String) throws -> String {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        guard let encoded = value.addingPercentEncoding(withAllowedCharacters: allowed) else {
            throw NRouterError.configuration("Path id could not be percent-encoded.")
        }
        return encoded
    }

    // The gateway's model lookup is a wildcard route because provider model
    // IDs contain `/`. Preserve those separators and escape each component.
    private func modelPath(_ value: String) throws -> String {
        try value.split(separator: "/", omittingEmptySubsequences: false)
            .map { try pathSegment(String($0)) }
            .joined(separator: "/")
    }

    private func send(_ request: URLRequest) async throws -> Response {
        var request = request
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        NRouter.applyDeadline(&request, from: session)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw NRouterError.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw NRouterError.transport("Response was not HTTP.")
        }

        let meta = NRouterResponseMeta(response: http)

        if (200..<300).contains(http.statusCode) {
            // A 2xx that is not JSON is a REAL RESPONSE you were billed for —
            // /v1/audio/speech returns audio, video content returns bytes,
            // stream:true returns SSE. Parsing those as JSON yields an empty
            // object, so the caller pays and receives nothing while the call
            // reports success. Refuse loudly instead.
            let contentType = (http.value(forHTTPHeaderField: "content-type") ?? "").lowercased()
            guard contentType.contains("json") else {
                throw NRouterError.transport(
                    "nRouter returned \(http.statusCode) with content-type "
                        + "'\(contentType)', which is not JSON. Use bytes(_:_:) for binary "
                        + "or streaming endpoints (/v1/audio/speech, "
                        + "/v1/videos/{id}/content, or stream: true); the JSON helpers "
                        + "would report success with an empty body."
                )
            }
            // A 2xx whose JSON does not parse is NOT an empty response — it is
            // a truncated or corrupted one, for a request that was billed.
            // Returning [:] here reports success with nothing in it.
            guard let body = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            else {
                throw NRouterError.transport(
                    "nRouter returned \(http.statusCode) with unparseable JSON; the request "
                        + "was billed but the body did not arrive intact."
                )
            }
            return Response(body: body, meta: meta, statusCode: http.statusCode)
        }
        let parsed = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        throw NRouterError.fromCode(
            NRouter.errorBody(status: http.statusCode, payload: parsed, meta: meta)
        )
    }

    /// `sk-nrouter-...abcd` — enough to identify, never enough to use.
    var redactedKey: String {
        "\(NRouter.keyPrefix)...\(apiKey.suffix(4))"
    }

    /// Pull the gateway's stable `code` and message out of an error payload.
    ///
    /// The gateway nests them under `error`; a bare object is accepted too, so
    /// a proxy that reshapes the envelope cannot downgrade a typed error into
    /// a generic one.
    static func errorBody(
        status: Int,
        payload: [String: Any],
        meta: NRouterResponseMeta
    ) -> NRouterErrorBody {
        let node = (payload["error"] as? [String: Any]) ?? payload
        return NRouterErrorBody(
            message: node["message"] as? String ?? "nRouter request failed",
            code: node["code"] as? String,
            status: status,
            requestID: meta.requestID,
            limitSource: meta.limitSource,
            authReason: meta.authReason
        )
    }

    private enum ParsedStreamFrame {
        case chunk(StreamChunk)
        case done
        case skip
    }

    private static func parseStreamFrame(
        event: String?,
        data: String,
        meta: NRouterResponseMeta
    ) throws -> ParsedStreamFrame {
        let trimmed = data.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return .skip }
        if trimmed == "[DONE]" { return .done }
        guard
            let encoded = trimmed.data(using: .utf8),
            let raw = try? JSONSerialization.jsonObject(with: encoded) as? [String: Any]
        else {
            if event == "error" {
                throw NRouterError.fromCode(
                    NRouterErrorBody(
                        message: trimmed,
                        code: knownStreamErrorCodes.contains(trimmed) ? trimmed : nil,
                        status: 200,
                        requestID: meta.requestID,
                        limitSource: meta.limitSource,
                        authReason: meta.authReason
                    )
                )
            }
            return .skip
        }
        if event == "error" || raw["error"] != nil {
            let node = (raw["error"] as? [String: Any]) ?? raw
            let explicitCode = node["code"] as? String
            let type = node["type"] as? String
            let code = explicitCode ?? (knownStreamErrorCodes.contains(type ?? "") ? type : nil)
            throw NRouterError.fromCode(
                NRouterErrorBody(
                    message: node["message"] as? String ?? trimmed,
                    code: code,
                    status: 200,
                    requestID: meta.requestID,
                    limitSource: meta.limitSource,
                    authReason: meta.authReason
                )
            )
        }
        if let type = raw["type"] as? String,
           type == "message_stop" || type == "response.completed"
        {
            return .done
        }
        return .chunk(
            StreamChunk(event: event, delta: streamDelta(raw), data: encoded)
        )
    }

    private static func streamDelta(_ raw: [String: Any]) -> String {
        if let value = raw["delta"] as? String { return value }
        if let delta = raw["delta"] as? [String: Any], let text = delta["text"] as? String {
            return text
        }
        guard let choice = (raw["choices"] as? [[String: Any]])?.first else { return "" }
        if let text = choice["text"] as? String { return text }
        return (choice["delta"] as? [String: Any])?["content"] as? String ?? ""
    }

    private static let knownStreamErrorCodes: Set<String> = [
        "invalid_request", "guardrail_blocked", "invalid_api_key", "insufficient_credits",
        "model_not_found", "rate_limit_exceeded", "tpm_limit_exceeded",
        "credit_check_failed", "service_unavailable",
    ]
}

// A struct reflects its stored properties by default, so `String(describing:)`,
// `print()`, `dump()` and a debugger quicklook all print `apiKey` verbatim —
// a credential that spends real credits, leaked by an ordinary log line
// (Rule #5). All three protocols are needed: the first two cover printing and
// `debugPrint`, and `CustomReflectable` is what `dump()` and the debugger read.
extension NRouter: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public var description: String {
        "NRouter(baseURL: \(baseURL), apiKey: \(redactedKey))"
    }

    public var debugDescription: String { description }

    public var customMirror: Mirror {
        Mirror(
            self,
            children: ["baseURL": baseURL, "apiKey": redactedKey],
            displayStyle: .struct
        )
    }
}
