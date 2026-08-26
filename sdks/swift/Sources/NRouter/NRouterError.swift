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
    /// `insufficient_credits` (402)
    case credit(NRouterErrorBody)
    /// `model_not_found` (404)
    case notFound(NRouterErrorBody)
    /// `rate_limit_exceeded` / `tpm_limit_exceeded` (429)
    case rateLimit(NRouterErrorBody)
    /// `credit_check_failed` / `service_unavailable` (503)
    case service(NRouterErrorBody)
    /// A code this SDK version does not know. Deliberately not re-classified.
    case other(NRouterErrorBody)
    /// The request never reached the gateway, or the key was refused locally.
    case transport(String)

    /// Build the case the gateway's `code` names.
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
            case 400: return .request(body)
            case 401: return .authentication(body)
            case 402: return .credit(body)
            case 404: return .notFound(body)
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
             let .credit(b), let .notFound(b), let .rateLimit(b),
             let .service(b), let .other(b):
            return b
        case .transport:
            return nil
        }
    }

    /// Whether retrying the identical request could plausibly succeed.
    ///
    /// False for every permanent 4xx: retrying there burns quota and cannot
    /// change the answer.
    public var isRetryable: Bool {
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
    public var status: Int?
    public var requestID: String?
    /// On a 429: which limit measured the refusal. Never guessed — absent means
    /// the gateway did not say, and a guess sends a customer to raise the
    /// wrong limit.
    public var limitSource: String?
    /// On a 401: the gateway's stable reason, e.g. `key_route_not_allowed`.
    public var authReason: String?

    public init(
        message: String,
        code: String? = nil,
        status: Int? = nil,
        requestID: String? = nil,
        limitSource: String? = nil,
        authReason: String? = nil
    ) {
        self.message = message
        self.code = code
        self.status = status
        self.requestID = requestID
        self.limitSource = limitSource
        self.authReason = authReason
    }
}

extension NRouterError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case let .transport(message):
            return "nRouter transport error: \(message)"
        default:
            guard let body else { return "nRouter request failed" }
            guard let code = body.code else { return body.message }
            return "\(body.message) (\(code))"
        }
    }
}
