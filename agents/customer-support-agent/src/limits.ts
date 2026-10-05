import type { ChatRequest, PayloadLimits, ChatTurn, TrustedContext } from './types.js';
import { SupportAgentError } from './errors.js';

/** Validate host-supplied trusted context (shape and caps only). Throws SupportAgentError('invalid_request'). */
export function validateTrustedContext(ctx: unknown): TrustedContext {
  if (ctx === undefined || ctx === null) {
    return {};
  }
  if (!isPlainObject(ctx)) {
    throw new SupportAgentError('invalid_request', 'context must be a plain object');
  }

  const result: TrustedContext = {};

  if ('identity' in ctx && ctx.identity !== undefined) {
    if (!isPlainObject(ctx.identity)) {
      throw new SupportAgentError('invalid_request', 'identity must be an object');
    }
    result.identity = {};
    if ('name' in ctx.identity && ctx.identity.name !== undefined) {
      if (typeof ctx.identity.name !== 'string' || ctx.identity.name.length > 200) {
        throw new SupportAgentError('invalid_request', 'identity.name must be a string <= 200 chars');
      }
      result.identity.name = ctx.identity.name;
    }
    if ('email' in ctx.identity && ctx.identity.email !== undefined) {
      if (typeof ctx.identity.email !== 'string' || ctx.identity.email.length > 200) {
        throw new SupportAgentError('invalid_request', 'identity.email must be a string <= 200 chars');
      }
      result.identity.email = ctx.identity.email;
    }
    if ('plan' in ctx.identity && ctx.identity.plan !== undefined) {
      if (typeof ctx.identity.plan !== 'string' || ctx.identity.plan.length > 200) {
        throw new SupportAgentError('invalid_request', 'identity.plan must be a string <= 200 chars');
      }
      result.identity.plan = ctx.identity.plan;
    }
  }

  if ('audiences' in ctx && ctx.audiences !== undefined) {
    if (!Array.isArray(ctx.audiences) || ctx.audiences.length > 20) {
      throw new SupportAgentError('invalid_request', 'audiences must be an array of length <= 20');
    }
    for (let i = 0; i < ctx.audiences.length; i++) {
      if (typeof ctx.audiences[i] !== 'string' || ctx.audiences[i].length === 0 || ctx.audiences[i].length > 64) {
        throw new SupportAgentError('invalid_request', `audiences[${i}] must be a non-empty string <= 64 chars`);
      }
    }
    result.audiences = [...ctx.audiences];
  }

  if ('sessionId' in ctx && ctx.sessionId !== undefined) {
    if (typeof ctx.sessionId !== 'string' || ctx.sessionId.length < 1 || ctx.sessionId.length > 128) {
      throw new SupportAgentError('invalid_request', 'sessionId must be a string 1..128 chars');
    }
    result.sessionId = ctx.sessionId;
  }

  return result;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Validate an untrusted chat request body. Throws SupportAgentError('invalid_request'). */
export function validateChatRequest(req: unknown, limits: PayloadLimits): ChatRequest {
  if (!isPlainObject(req)) {
    throw new SupportAgentError('invalid_request', 'request must be an object');
  }

  if (!Array.isArray(req.messages) || req.messages.length === 0 || req.messages.length > limits.maxMessages) {
    throw new SupportAgentError('invalid_request', 'messages must be an array of length 1 to maxMessages');
  }

  const messages: ChatTurn[] = [];
  for (let i = 0; i < req.messages.length; i++) {
    const msg = req.messages[i];
    if (!isPlainObject(msg)) {
      throw new SupportAgentError('invalid_request', `messages[${i}] must be an object`);
    }
    if (msg.role !== 'user' && msg.role !== 'assistant') {
      throw new SupportAgentError('invalid_request', `messages[${i}].role must be 'user' or 'assistant'`);
    }
    if (typeof msg.content !== 'string' || msg.content.trim().length === 0 || msg.content.length > limits.maxMessageChars) {
      throw new SupportAgentError('invalid_request', `messages[${i}].content must be a non-empty string <= maxMessageChars`);
    }
    messages.push({ role: msg.role as 'user' | 'assistant', content: msg.content });
  }

  if (messages[messages.length - 1]!.role !== 'user') {
    throw new SupportAgentError('invalid_request', 'last message must have role user');
  }

  const result: ChatRequest = { messages };

  if ('pageContext' in req && req.pageContext !== undefined) {
    if (typeof req.pageContext !== 'string' || req.pageContext.length > limits.maxPageContextChars * 10) {
      throw new SupportAgentError('invalid_request', 'pageContext must be a string <= 10x maxPageContextChars');
    }
    result.pageContext = req.pageContext.length > limits.maxPageContextChars 
      ? req.pageContext.slice(0, limits.maxPageContextChars) 
      : req.pageContext;
  }

  if ('signal' in req && req.signal !== undefined) {
    if (typeof req.signal !== 'object' || req.signal === null || !('aborted' in req.signal)) {
      throw new SupportAgentError('invalid_request', 'signal must be an AbortSignal');
    }
    result.signal = req.signal as AbortSignal;
  }

  return result;
}
