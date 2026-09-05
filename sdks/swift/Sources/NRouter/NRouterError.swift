import Foundation

/// Why the gateway refused a request.
///
/// Cases map one-to-one to the `errors` block of `spec/nrouter-sdk-spec.json`.
/// The gateway's stable `code` decides the case — not the HTTP status, which
/// cannot separate `invalid_request` from `guardrail_blocked` (both 400) nor
/// `rate_limit_exceeded` from `tpm_limit_exceeded` (both 429).
public enum NRouterError: Error, Equatable {
    /// `invalid_request` (400)
    case request(NRouterErrorBody)
    /// `guardrail_blocked` (400)
    case guardrailBlocked(NRouterErrorBody)
    /// `invalid_api_key` (401)
    case authentication(NRouterErrorBody)
    /// `insufficient_credits` (402) — the credit reserve failed. Top up.
    case credit(NRouterErrorBody)
    /// A BUDGET ceiling (402), not a shortfall.
    ///
    /// Three conditions share 402 and two are budget ceilings, whose fix is the
    /// OPPOSITE of a shortfall's: raise the budget, not top up. Telling a
    /// customer whose budget is exhausted to add money is a wrong answer
    /// delivered confidently.
    case budgetExceeded(NRouterErrorBody)
    /// `model_not_found` (404)
    case notFound(NRouterErrorBody)
    /// `rate_limit_exceeded` / `tpm_limit_exceeded` (429)
    case rateLimit(NRouterErrorBody)
    /// `credit_check_failed` / `service_unavailable` (503)
    case service(NRouterErrorBody)
    /// A code this SDK version does not know. Deliberately not re-classified.
    case other(NRouterErrorBody)
    /// The request left this process and got no answer — DNS, TLS, a dropped
    /// connection, a timeout. Retryable.
    case transport(String)
    /// The SDK refused before sending anything: no key, or a key that is not
    /// shaped like an nRouter key.
    ///
    /// Separate from `.transport` on purpose. Both are raised locally, but this
    /// one is PERMANENT — a caller retrying on `isRetryable` would spin forever
    /// without ever making a request.
    case configuration(String)

    /// Classify a gateway refusal.
    ///
    /// Three signals, in order, because no single one is sufficient:
    ///
    /// 1. `code`, when present — the only thing separating
    ///    `rate_limit_exceeded` from `tpm_limit_exceeded`. The gateway's WAF
    ///    and its upstream passthrough send one.
    /// 2. status, otherwise. The gateway's main error path emits
    ///    `{"error":{"type","message"}}` with **no code at all**, so this is the
    ///    ordinary case, not the fallback it looks like.
    /// 3. the message, to split the two 400s. With no code the message is the
    ///    only signal present; calling every 400 a request error makes
    ///    `.guardrailBlocked` unreachable and tells a caller to fix a body that
    ///    was never the problem.
    public static func fromCode(_ body: NRouterErrorBody) -> NRouterError {
        switch body.code {
        case "invalid_request": return .request(body)
        case "guardrail_blocked": return .guardrailBlocked(body)
        case "invalid_api_key": return .authentication(body)
        case "insufficient_credits": return .credit(body)
        case "model_not_found": return .notFound(body)
        case "rate_limit_exceeded", "tpm_limit_exceeded": return .rateLimit(body)
        case "credit_check_failed", "service_unavailable": return .service(body)
        case .some: return .other(body)
        case nil:
            switch body.status {
            case 400:
                return body.message.lowercased().contains("guardrail")
                    ? .guardrailBlocked(body)
                    : .request(body)
            case 401: return .authentication(body)
            case 402:
                // The gateway's own wording is the only discriminator, and it
                // is stable: GatewayError::{BudgetExceeded,
                // ScopedBudgetExceeded} both start their Display with "budget".
                return body.message.trimmingCharacters(in: .whitespaces)
                    .lowercased().hasPrefix("budget")
                    ? .budgetExceeded(body)
                    : .credit(body)
            case 404:
                // Scoped to MODELS. A 404 is also a missing video job, an
                // unknown MCP server or an unknown agent run; calling those
                // `model_not_found` is a wrong answer with a confident code.
                return body.message.lowercased().contains("model")
                    ? .notFound(body)
                    : .other(body)
            case 429: return .rateLimit(body)
            case 503: return .service(body)
            default: return .other(body)
            }
        }
    }

    /// The gateway payload, when the request actually reached the gateway.
    public var body: NRouterErrorBody? {
        switch self {
        case let .request(b), let .guardrailBlocked(b), let .authentication(b),
             let .credit(b), let .budgetExceeded(b), let .notFound(b),
             let .rateLimit(b), let .service(b), let .other(b):
            return b
        case .transport, .configuration:
            return nil
        }
    }

    /// Whether retrying the identical request could plausibly succeed.
    ///
    /// False for every permanent 4xx: retrying there burns quota and cannot
    /// change the answer.
    public var isRetryable: Bool {
        if let status = body?.status, status == 408 || status == 425 {
            return true
        }
        switch self {
        case .rateLimit, .service, .transport: return true
        default: return false
        }
    }
}

/// The parsed gateway error payload plus the metadata worth acting on.
public struct NRouterErrorBody: Equatable, Sendable {
    public var message: String
    public var code: String?
    public var param: String?
    public var type: String?
    public var status: Int?
    public var requestID: String?
    /// On a 429: which limit measured the refusal. Never guessed — absent means
    /// the gateway did not say, and a guess sends a customer to raise the
    /// wrong limit.
    public var limitSource: String?
    /// On a 401: the gateway's stable reason, e.g. `key_route_not_allowed`.
    public var authReason: String?
    /// On a 429: wait duration in seconds from Retry-After header.
    public var retryAfter: UInt64?

    public init(
        message: String,
        code: String? = nil,
        param: String? = nil,
        type: String? = nil,
        status: Int? = nil,
        requestID: String? = nil,
        limitSource: String? = nil,
        authReason: String? = nil,
        retryAfter: UInt64? = nil
    ) {
        self.message = message
        self.code = code
        self.param = param
        self.type = type
        self.status = status
        self.requestID = requestID
        self.limitSource = limitSource
        self.authReason = authReason
        self.retryAfter = retryAfter
    }
}

/// Max Retry-After ceiling (24 hours).
public let maxRetryAfterSeconds: UInt64 = 86400

/// Parses an RFC 9110 Retry-After header value (delta-seconds or IMF-fixdate HTTP-date).
public func parseRetryAfter(_ raw: String?, now: Date = Date()) -> UInt64? {
    guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
        return nil
    }
    if let seconds = UInt64(raw) {
        return min(seconds, maxRetryAfterSeconds)
    }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss 'GMT'"
    if let date = formatter.date(from: raw) {
        let delta = date.timeIntervalSince(now)
        if delta <= 0 {
            return 0
        }
        let seconds = UInt64(delta.rounded())
        return min(seconds, maxRetryAfterSeconds)
    }
    return nil
}

/// Computes a bounded jittered exponential backoff duration in seconds.
///
/// Honors `retryAfterSeconds` when present and > 0, bounded by `maxDelay`.
/// Clamps `attempt` to 30 to avoid floating point overflow.
/// Jitter factor spreads backoff between (1 - jitterFactor) and 1.0 of the computed delay.
public func computeJitteredBackoff(
    attempt: UInt32,
    baseDelay: TimeInterval = 0.5,
    maxDelay: TimeInterval = 30.0,
    retryAfterSeconds: UInt64? = nil,
    jitterFactor: Double = 0.5
) -> TimeInterval {
    let safeAttempt = min(attempt, 30)
    let safeJitter = max(0.0, min(jitterFactor, 1.0))

    if let ra = retryAfterSeconds, ra > 0 {
        let retryDelay = min(Double(ra), maxDelay)
        let multiplier = (1.0 - safeJitter) + Double.random(in: 0.0...1.0) * safeJitter
        return max(0.0, retryDelay * multiplier)
    }

    let exponentialMultiplier = Double(1 << safeAttempt)
    let rawDelay = min(maxDelay, baseDelay * exponentialMultiplier)
    let multiplier = (1.0 - safeJitter) + Double.random(in: 0.0...1.0) * safeJitter
    return max(0.0, rawDelay * multiplier)
}

extension NRouterError: LocalizedError, CustomStringConvertible {
    public var errorDescription: String? {
        switch self {
        case let .transport(message):
            return "nRouter transport error: \(redactKeys(message))"
        case let .configuration(message):
            return "nRouter configuration error: \(redactKeys(message))"
        default:
            guard let body else { return "nRouter request failed" }
            let msg = redactKeys(body.message)
            guard let code = body.code else { return msg }
            return "\(msg) (\(code))"
        }
    }

    public var description: String {
        errorDescription ?? "nRouter error"
    }
}

/// Redacts nRouter and provider API keys from arbitrary strings.
public func redactKeys(_ string: String) -> String {
    guard let nrouterRegex = try? NSRegularExpression(pattern: "sk-nrouter-[A-Za-z0-9._-]{4,}") else {
        return string
    }
    let range = NSRange(string.startIndex..<string.endIndex, in: string)
    var masked = nrouterRegex.stringByReplacingMatches(in: string, range: range, withTemplate: "sk-nrouter-***")

    guard let genericRegex = try? NSRegularExpression(pattern: "\\bsk-[A-Za-z0-9._-]{6,}\\b") else {
        return masked
    }
    let genericRange = NSRange(masked.startIndex..<masked.endIndex, in: masked)
    let matches = genericRegex.matches(in: masked, range: genericRange)
    for match in matches.reversed() {
        if let r = Range(match.range, in: masked) {
            let token = String(masked[r])
            if !token.starts(with: "sk-nrouter") {
                masked.replaceSubrange(r, with: "sk-***")
            }
        }
    }
    return masked
}

/// Structured gateway error envelope.
public struct NRouterErrorEnvelope: Equatable, Sendable {
    public var code: String?
    public var message: String?
    public var param: String?
    public var type: String?

    public init(code: String? = nil, message: String? = nil, param: String? = nil, type: String? = nil) {
        self.code = code
        self.message = message
        self.param = param
        self.type = type
    }
}

/// Parses a gateway error JSON payload into a structured NRouterErrorEnvelope.
public func parseGatewayErrorEnvelope(data: Data) -> NRouterErrorEnvelope {
    guard let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
        let text = String(data: data, encoding: .utf8)
        return NRouterErrorEnvelope(message: text.map(redactKeys))
    }
    let node = (json["error"] as? [String: Any]) ?? json
    let msg = (node["message"] as? String) ?? (json["message"] as? String)
    let code = (node["code"] as? String) ?? (json["code"] as? String)
    let param = (node["param"] as? String) ?? (json["param"] as? String)
    let type = (node["type"] as? String) ?? (json["type"] as? String)
    return NRouterErrorEnvelope(
        code: code,
        message: msg.map(redactKeys),
        param: param,
        type: type
    )
}

/// Formats an NRouterError into a human-readable, log-safe diagnostic string,
/// masking all API keys.
public func formatError(_ error: NRouterError) -> String {
    var parts: [String] = []
    switch error {
    case .request: parts.append("[request]")
    case .guardrailBlocked: parts.append("[guardrail_blocked]")
    case .authentication: parts.append("[authentication]")
    case .credit: parts.append("[credit]")
    case .budgetExceeded: parts.append("[budget_exceeded]")
    case .notFound: parts.append("[not_found]")
    case .rateLimit: parts.append("[rate_limit]")
    case .service: parts.append("[service]")
    case .other: parts.append("[other]")
    case .transport: parts.append("[transport]")
    case .configuration: parts.append("[configuration]")
    }

    if let b = error.body {
        if let status = b.status { parts.append("HTTP \(status)") }
        if let code = b.code { parts.append("code=\(code)") }
        if let param = b.param { parts.append("param=\(param)") }
        if let reqId = b.requestID { parts.append("requestId=\(reqId)") }
        if let src = b.limitSource { parts.append("limitSource=\(src)") }
        if let ra = b.retryAfter { parts.append("retryAfter=\(ra)s") }
        parts.append(": \(redactKeys(b.message))")
    } else {
        parts.append(": \(redactKeys(error.localizedDescription))")
    }
    return parts.joined(separator: " ")
}

