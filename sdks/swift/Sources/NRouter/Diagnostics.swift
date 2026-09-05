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
