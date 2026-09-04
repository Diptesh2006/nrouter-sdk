import Foundation

/// Per-request metadata carried on the `x-nr-*` response headers.
///
/// Every property is optional on purpose. The gateway omits a header rather
/// than sending a placeholder, and the two omissions that matter most are
/// `x-nr-request-cost` — ABSENT when the model is unpriced, never `0` — and
/// `x-nr-limit-source`, absent when nothing measured a refusal.
public struct NRouterResponseMeta: Equatable, Sendable {
    /// Present on every response; the join key for a spend row or a log line.
    public var requestID: String?
    /// Exact USD cost. `nil` when unpriced — rendering that as `0` would report
    /// a free request, which no enabled model is.
    public var cost: Double?
    /// `exact` or `unpriced`.
    public var costStatus: String?
    public var model: String?
    public var inputTokens: Int?
    public var outputTokens: Int?
    public var totalTokens: Int?
    public var cacheReadTokens: Int?
    public var cacheWriteTokens: Int?
    /// On a 429, which limit measured the refusal.
    public var limitSource: String?
    /// Set when this request crossed a soft budget you configured; it still
    /// served. `<scope> soft_budget <spend>/<ceiling>`, e.g.
    /// `org soft_budget 80.00/100.00`.
    public var budgetWarning: String?
    /// Posture of the PRE-CALL guardrail chain: `none`, `monitor`, `pass`,
    /// `partial` or `blocked`, matched exactly and case-sensitively.
    ///
    /// `nil` means the gateway made NO guardrail claim about this response —
    /// never "no guardrail applied", which is the explicit `none`. Posture only
    /// by design: policy name, policy id, detector family, rule count and (for
    /// `partial`) which channel went uninspected are deliberately withheld.
    public var guardrails: String?
    /// On a 401, the gateway's stable reason.
    public var authReason: String?
    /// `hit` or `miss`; absent when the response cache did not participate.
    public var responseCache: String?
    /// Age in seconds of a response-cache hit.
    public var responseCacheAge: Int?

    /// Every header this SDK reads, exactly as the spec names them.
    public static let headerNames: [String] = [
        "x-nr-request-id",
        "x-nr-request-cost",
        "x-nr-cost-status",
        "x-nr-model",
        "x-nr-input-tokens",
        "x-nr-output-tokens",
        "x-nr-total-tokens",
        "x-nr-cache-read-tokens",
        "x-nr-cache-write-tokens",
        "x-nr-limit-source",
        "x-nr-budget-warning",
        "x-nr-guardrails",
        "x-nr-auth-reason",
        "x-nr-response-cache",
        "x-nr-response-cache-age",
    ]

    public init() {}

    /// Parse from anything that looks a header up by lowercase name.
    ///
    /// An unparseable numeric header stays `nil` rather than defaulting: a zero
    /// here would be indistinguishable from a real zero.
    public init(lookup: (String) -> String?) {
        func int(_ name: String) -> Int? { lookup(name).flatMap(Int.init) }
        requestID = lookup("x-nr-request-id")
        cost = lookup("x-nr-request-cost").flatMap(Double.init)
        costStatus = lookup("x-nr-cost-status")
        model = lookup("x-nr-model")
        inputTokens = int("x-nr-input-tokens")
        outputTokens = int("x-nr-output-tokens")
        totalTokens = int("x-nr-total-tokens")
        cacheReadTokens = int("x-nr-cache-read-tokens")
        cacheWriteTokens = int("x-nr-cache-write-tokens")
        limitSource = lookup("x-nr-limit-source")
        budgetWarning = lookup("x-nr-budget-warning")
        guardrails = lookup("x-nr-guardrails")
        authReason = lookup("x-nr-auth-reason")
        responseCache = lookup("x-nr-response-cache")
        responseCacheAge = int("x-nr-response-cache-age")
    }

    /// Parse from an `HTTPURLResponse`.
    public init(response: HTTPURLResponse) {
        self.init { name in
            // Header names are case-insensitive on the wire; ask the way
            // Foundation prefers, then fall back to a manual scan for the
            // platforms where the case-insensitive lookup is unavailable.
            if #available(macOS 13.0, iOS 16.0, tvOS 16.0, watchOS 9.0, *) {
                if let v = response.value(forHTTPHeaderField: name) { return v }
            }
            for (key, value) in response.allHeaderFields {
                if let key = key as? String, key.lowercased() == name {
                    return value as? String
                }
            }
            return nil
        }
    }

    /// True when the gateway priced this request exactly.
    public var isPriced: Bool { costStatus == "exact" && cost != nil }
}
