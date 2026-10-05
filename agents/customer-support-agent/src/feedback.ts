import type { FeedbackInput } from './types.js';
import { SupportAgentError } from './errors.js';

/** Validate untrusted feedback. Throws SupportAgentError('invalid_request'). */
export function validateFeedback(value: unknown): FeedbackInput {
  if (!value || typeof value !== 'object') {
    throw new SupportAgentError('invalid_request', 'Invalid feedback payload');
  }

  const fb = value as Record<string, unknown>;

  if (typeof fb.sessionId !== 'string' || fb.sessionId.length === 0 || fb.sessionId.length > 128) {
    throw new SupportAgentError('invalid_request', 'Invalid sessionId');
  }

  if (typeof fb.messageId !== 'string' || fb.messageId.length === 0 || fb.messageId.length > 128) {
    throw new SupportAgentError('invalid_request', 'Invalid messageId');
  }

  if (fb.rating !== 'up' && fb.rating !== 'down') {
    throw new SupportAgentError('invalid_request', 'Invalid rating');
  }

  if (fb.question !== undefined && (typeof fb.question !== 'string' || fb.question.length > 2000)) {
    throw new SupportAgentError('invalid_request', 'Invalid question');
  }

  if (fb.confidence !== undefined && fb.confidence !== 'high' && fb.confidence !== 'medium' && fb.confidence !== 'low') {
    throw new SupportAgentError('invalid_request', 'Invalid confidence');
  }

  if (fb.webSearched !== undefined && typeof fb.webSearched !== 'boolean') {
    throw new SupportAgentError('invalid_request', 'Invalid webSearched');
  }

  if (fb.reason !== undefined && (typeof fb.reason !== 'string' || fb.reason.length > 500)) {
    throw new SupportAgentError('invalid_request', 'Invalid reason');
  }

  return {
    sessionId: fb.sessionId,
    messageId: fb.messageId,
    rating: fb.rating,
    ...(fb.question !== undefined ? { question: fb.question } : {}),
    ...(fb.confidence !== undefined ? { confidence: fb.confidence as FeedbackInput['confidence'] } : {}),
    ...(fb.webSearched !== undefined ? { webSearched: fb.webSearched } : {}),
    ...(fb.reason !== undefined ? { reason: fb.reason } : {}),
  };
}
