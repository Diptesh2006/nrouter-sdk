export interface ReasoningExhaustionReport {
  exhausted: boolean;
  finishReason: string;
  reasoningTokens: number;
  outputTokens: number;
  message?: string;
}

/**
 * Diagnoses if a response produced no text because reasoning tokens consumed the entire budget.
 */
export function diagnoseReasoningExhaustion(
  finishReason: string,
  outputTokens: number = 0,
  reasoningTokens: number = 0,
  content: string = '',
): ReasoningExhaustionReport {
  const f = finishReason.trim().toLowerCase();
  if ((f === 'length' || f === 'max_tokens') && !content.trim()) {
    if (reasoningTokens > 0 || outputTokens > 0) {
      return {
        exhausted: true,
        finishReason,
        reasoningTokens,
        outputTokens,
        message:
          'Reasoning consumed the entire token budget before completion text could be generated. Increase max_tokens or max_completion_tokens.',
      };
    }
  }
  return {
    exhausted: false,
    finishReason,
    reasoningTokens,
    outputTokens,
  };
}
