import Foundation

/// Diagnostic details when reasoning tokens exhaust the generation budget.
public struct ReasoningExhaustionReport: Sendable, Equatable {
    public let exhausted: Bool
    public let finishReason: String
    public let reasoningTokens: Int
    public let outputTokens: Int
    public let message: String?

    public init(
        exhausted: Bool,
        finishReason: String,
        reasoningTokens: Int = 0,
        outputTokens: Int = 0,
        message: String? = nil
    ) {
        self.exhausted = exhausted
        self.finishReason = finishReason
        self.reasoningTokens = reasoningTokens
        self.outputTokens = outputTokens
        self.message = message
    }
}

/// Diagnoses if a response produced no text because reasoning tokens consumed the entire budget.
public func diagnoseReasoningExhaustion(
    finishReason: String,
    outputTokens: Int = 0,
    reasoningTokens: Int = 0,
    content: String = ""
) -> ReasoningExhaustionReport {
    let f = finishReason.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if (f == "length" || f == "max_tokens") && content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        if reasoningTokens > 0 || outputTokens > 0 {
            return ReasoningExhaustionReport(
                exhausted: true,
                finishReason: finishReason,
                reasoningTokens: reasoningTokens,
                outputTokens: outputTokens,
                message: "Reasoning consumed the entire token budget before completion text could be generated. Increase max_tokens or max_completion_tokens."
            )
        }
    }
    return ReasoningExhaustionReport(
        exhausted: false,
        finishReason: finishReason,
        reasoningTokens: reasoningTokens,
        outputTokens: outputTokens
    )
}

/// Extract trace routing headers (e.g. `x-nr-request-id`) from response metadata.
public func extractTraceHeaders(_ meta: NRouterResponseMeta) -> [String: String] {
    var out: [String: String] = [:]
    if let reqId = meta.requestID {
        out["x-nr-request-id"] = reqId
    }
    return out
}

/// Extract trace routing headers from an arbitrary dictionary of HTTP headers.
public func extractTraceHeaders(_ headers: [String: String]) -> [String: String] {
    var out: [String: String] = [:]
    for (k, v) in headers {
        let kl = k.lowercased()
        if kl == "x-nr-request-id" || kl == "x-nr-trace-id" || kl == "x-nr-session-id" {
            out[kl] = v
        }
    }
    return out
}

/// Inject trace context headers, validating that traceId and sessionId do not contain CRLF characters.
public func withTraceContext(
    headers: [String: String] = [:],
    traceId: String? = nil,
    sessionId: String? = nil
) throws -> [String: String] {
    if let traceId, traceId.unicodeScalars.contains(where: { $0 == "\r" || $0 == "\n" }) {
        throw NRouterError.configuration("traceId must not contain CRLF characters")
    }
    if let sessionId, sessionId.unicodeScalars.contains(where: { $0 == "\r" || $0 == "\n" }) {
        throw NRouterError.configuration("sessionId must not contain CRLF characters")
    }
    var out: [String: String] = [:]
    for (k, v) in headers {
        if !v.unicodeScalars.contains(where: { $0 == "\r" || $0 == "\n" }) {
            out[k] = v
        }
    }
    if let traceId {
        out["x-nr-trace-id"] = traceId
    }
    if let sessionId {
        out["x-nr-session-id"] = sessionId
    }
    return out
}

