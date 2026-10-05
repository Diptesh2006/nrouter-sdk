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
    /// Milliseconds the gateway measured from edge arrival to response headers
    /// ready.
    ///
    /// TIME TO HEADERS, not time to the last byte: on a streamed response the
    /// headers are ready before the first token, so this is never a
    /// total-generation figure.
    public var latencyMs: Int?
    /// The gateway's OpenTelemetry trace id, `nil` when no valid trace exists.
    ///
    /// A caller may SEND `x-nr-trace-id` (and `x-nr-session-id`) to correlate
    /// its own spans; the gateway overwrites the response value with its own,
    /// so join on this rather than assuming it echoes what was sent.
    public var traceID: String?
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
    /// Posture of the PRE-CALL guardrail chain: `none`, `monitor`, `redacted`,
    /// `pass`, `partial`, `blocked` or `unavailable`, matched exactly and
    /// case-sensitively. `redacted` means an enforcing chain REWROTE part of
    /// the prompt before the provider saw it and the request then served;
    /// `partial` means only that some content went uninspected, never that
    /// anything was rewritten.
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
    /// Prompt compression outcome: applied | not_requested | off | skipped.
    public var compression: String?
    /// Which chain entry answered: direct | fallback:<n>. Absent on cache hits and refusals.
    public var routing: String?
    /// Provider calls made for this request (>= 1). Absent on cache hits and refusals.
    public var attempts: Int?
    /// The top intent category evaluated by the preflight chain, if intent routing was requested.
    public var intent: String?
    /// How this response was funded.
    public var fundingSource: String?
    /// When the current usage allowance resets.
    public var allowanceReset: Int?

    /// Every header this SDK reads, exactly as the spec names them.
    public static let headerNames: [String] = [
        "x-nr-request-id",
        "x-nr-latency-ms",
        "x-nr-trace-id",
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
        "x-nr-compression",
        "x-nr-routing",
        "x-nr-attempts",
        "x-nr-intent",
        "x-nr-funding-source",
        "x-nr-allowance-reset",
    ]

    public init() {}

    /// Parse from anything that looks a header up by lowercase name.
    ///
    /// An unparseable numeric header stays `nil` rather than defaulting: a zero
    /// here would be indistinguishable from a real zero.
    public init(lookup: (String) -> String?) {
        func int(_ name: String) -> Int? { lookup(name).flatMap(Int.init) }
        requestID = lookup("x-nr-request-id")
        // int(), not a raw read: the gateway sends whole milliseconds, so a
        // fractional or garbage value is a mangled header rather than a
        // latency a caller should chart.
        latencyMs = int("x-nr-latency-ms")
        traceID = lookup("x-nr-trace-id")
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
        compression = lookup("x-nr-compression")
        routing = lookup("x-nr-routing")
        attempts = int("x-nr-attempts")
        intent = lookup("x-nr-intent")
        fundingSource = lookup("x-nr-funding-source")
        allowanceReset = int("x-nr-allowance-reset")
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

    public struct BudgetWarningInfo: Equatable, Sendable {
        public let scope: String
        public let spend: Double
        public let ceiling: Double
    }

    public func parseBudgetWarning() -> BudgetWarningInfo? {
        guard let bw = budgetWarning else { return nil }
        let parts = bw.split(whereSeparator: \.isWhitespace).map(String.init)
        guard parts.count == 3, parts[1] == "soft_budget" else { return nil }
        let scope = parts[0]
        let amounts = parts[2].components(separatedBy: "/")
        guard amounts.count == 2,
              let spend = Double(amounts[0]),
              let ceiling = Double(amounts[1]),
              spend >= 0, ceiling > 0, spend.isFinite, ceiling.isFinite else { return nil }
        return BudgetWarningInfo(scope: scope, spend: spend, ceiling: ceiling)
    }

    public var isCacheHit: Bool { responseCache == "hit" }
    public var isCacheMiss: Bool { responseCache == "miss" }
    public var cacheAgeSeconds: Int { responseCacheAge ?? 0 }
}
