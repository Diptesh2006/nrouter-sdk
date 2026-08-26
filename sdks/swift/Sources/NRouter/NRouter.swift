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

    public let baseURL: String
    private let apiKey: String
    private let session: URLSession

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

    /// Build a client. The key is validated up front so a malformed one fails
    /// here rather than as a 401 that reads like a revoked credential.
    ///
    /// - Parameters:
    ///   - apiKey: Explicit key. Falls back to `NROUTER_API_KEY`.
    ///   - baseURL: Gateway base URL. Defaults to production.
    ///   - session: Inject your own to control proxy, timeout, or caching.
    public init(
        apiKey: String? = nil,
        baseURL: String = NRouter.defaultBaseURL,
        session: URLSession = .shared
    ) throws {
        self.apiKey = try NRouter.resolveAPIKey(apiKey)
        self.baseURL = baseURL.hasSuffix("/") ? String(baseURL.dropLast()) : baseURL
        self.session = session
    }

    /// Resolve and validate a key: explicit argument first, then environment.
    public static func resolveAPIKey(_ explicit: String? = nil) throws -> String {
        let key = explicit?.isEmpty == false
            ? explicit!
            : ProcessInfo.processInfo.environment[envKey] ?? ""
        guard !key.isEmpty else {
            throw NRouterError.transport(
                "No nRouter API key: pass one explicitly or set \(envKey)."
            )
        }
        guard key.hasPrefix(keyPrefix) else {
            throw NRouterError.transport(
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

    /// `POST /embeddings`
    public func embeddings(_ body: [String: Any]) async throws -> Response {
        try await post("/embeddings", body)
    }

    /// `POST /messages` — the Anthropic wire format the gateway also serves.
    public func messages(_ body: [String: Any]) async throws -> Response {
        try await post("/messages", body)
    }

    /// `POST /responses`
    public func responses(_ body: [String: Any]) async throws -> Response {
        try await post("/responses", body)
    }

    /// `GET /models` — what this key is allowed to route to.
    public func models() async throws -> Response {
        try await get("/models")
    }

    /// Any `POST` path under the gateway's `/v1` root.
    public func post(_ path: String, _ body: [String: Any]) async throws -> Response {
        var request = URLRequest(url: try url(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await send(request)
    }

    /// Any `GET` path under the gateway's `/v1` root.
    public func get(_ path: String) async throws -> Response {
        var request = URLRequest(url: try url(path))
        request.httpMethod = "GET"
        return try await send(request)
    }

    // MARK: - Internals

    private func url(_ path: String) throws -> URL {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        guard let url = URL(string: "\(baseURL)/\(trimmed)") else {
            throw NRouterError.transport("Could not build a URL for \(baseURL)/\(trimmed).")
        }
        return url
    }

    private func send(_ request: URLRequest) async throws -> Response {
        var request = request
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")

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
        let parsed = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]

        if (200..<300).contains(http.statusCode) {
            return Response(body: parsed, meta: meta, statusCode: http.statusCode)
        }
        throw NRouterError.fromCode(
            NRouter.errorBody(status: http.statusCode, payload: parsed, meta: meta)
        )
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
}
