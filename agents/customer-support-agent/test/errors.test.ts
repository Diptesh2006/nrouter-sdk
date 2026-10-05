import { describe, it, expect } from 'vitest';
import { SupportAgentError, redact, toSafeError, mapErrorClass, isModelFallbackEligible } from '../src/errors.js';
import {
  classifyError,
  nRouterNotFoundError,
  nRouterAuthenticationError,
  nRouterCreditError,
  nRouterBudgetExceededError,
  nRouterRateLimitError,
  nRouterGuardrailBlockedError,
  nRouterError
} from '@nrouter_ai/sdk';

class FakeAbortError extends Error {
  name = 'AbortError';
}

describe('errors', () => {
  describe('SupportAgentError', () => {
    it('creates an error with a code and safe form', () => {
      const err = new SupportAgentError('invalid_config', 'test msg');
      expect(err.code).toBe('invalid_config');
      expect(err.message).toBe('test msg');
      expect(err.toSafe()).toEqual({ code: 'invalid_config', message: 'test msg' });
    });
  });

  describe('redact', () => {
    it('redacts nrouter keys', () => {
      expect(redact('failed auth for sk-nrouter-abc123_test')).toBe('failed auth for [redacted]');
    });
    
    it('redacts provided secrets that are >= 8 chars', () => {
      expect(redact('my secret123 is here', ['secret123', 'short'])).toBe('my [redacted] is here');
    });

    it('does not redact short secrets', () => {
      expect(redact('my short is here', ['short'])).toBe('my short is here');
    });
  });

  describe('toSafeError', () => {
    it('handles SupportAgentError', () => {
      const err = new SupportAgentError('invalid_index', 'bad index sk-nrouter-abc');
      expect(toSafeError(err)).toEqual({ code: 'invalid_index', message: 'bad index [redacted]' });
    });

    it('handles nRouterAuthenticationError', () => {
      // nRouter error classes take (status, error, message, headers) - actually the signature might vary, let's just mock it or pass undefined
      // wait, `new nRouterAuthenticationError(401, {}, "bad key sk-nrouter-foo", undefined)`
      // Let's check constructor signature or just cast.
      const err = Object.create(nRouterAuthenticationError.prototype);
      err.message = 'bad key sk-nrouter-foo';
      expect(toSafeError(err)).toEqual({ code: 'auth_failed', message: 'bad key [redacted]' });
    });

    it('handles nRouterCreditError', () => {
      const err = Object.create(nRouterCreditError.prototype);
      err.message = 'no money';
      expect(toSafeError(err)).toEqual({ code: 'insufficient_credit', message: 'no money' });
    });

    it('handles nRouterBudgetExceededError', () => {
      const err = Object.create(nRouterBudgetExceededError.prototype);
      err.message = 'budget out';
      expect(toSafeError(err)).toEqual({ code: 'insufficient_credit', message: 'budget out' });
    });

    it('handles nRouterRateLimitError', () => {
      const err = Object.create(nRouterRateLimitError.prototype);
      err.message = 'too fast';
      expect(toSafeError(err)).toEqual({ code: 'rate_limited', message: 'too fast' });
    });

    it('handles nRouterGuardrailBlockedError', () => {
      const err = Object.create(nRouterGuardrailBlockedError.prototype);
      err.message = 'blocked sk-nrouter-bar';
      expect(toSafeError(err)).toEqual({ code: 'guardrail_blocked', message: 'blocked [redacted]' });
    });

    it('handles other nRouterError', () => {
      const err = Object.create(nRouterError.prototype);
      err.message = 'upstream failed';
      expect(toSafeError(err)).toEqual({ code: 'upstream_error', message: 'upstream failed' });
    });

    it('handles AbortError', () => {
      const err = new FakeAbortError('user aborted');
      expect(toSafeError(err)).toEqual({ code: 'aborted', message: 'user aborted' });
    });

    it('handles unknown errors', () => {
      const err = new Error('some internals sk-nrouter-123');
      expect(toSafeError(err)).toEqual({ code: 'internal_error', message: 'An internal error occurred.' });
    });

    it('classifies non-nRouterError with status (OpenAI APIError shape)', () => {
      // Guardrail blocked via status 400 + guardrail in message
      const guardrailErr = { status: 400, message: 'request blocked by a guardrail: PII detected in PreCall content' };
      expect(toSafeError(guardrailErr)).toEqual({
        code: 'guardrail_blocked',
        message: 'request blocked by a guardrail: PII detected in PreCall content'
      });

      // 401 Auth failed
      const authErr = { status: 401, message: 'invalid api key' };
      expect(toSafeError(authErr)).toEqual({
        code: 'auth_failed',
        message: 'invalid api key'
      });

      // 402 Credit error
      const creditErr = { status: 402, message: 'insufficient credits' };
      expect(toSafeError(creditErr)).toEqual({
        code: 'insufficient_credit',
        message: 'insufficient credits'
      });

      // 402 Budget error
      const budgetErr = { status: 402, message: 'budget exceeded for tenant' };
      expect(toSafeError(budgetErr)).toEqual({
        code: 'insufficient_credit',
        message: 'budget exceeded for tenant'
      });

      // 429 Rate limit
      const rateLimitErr = { status: 429, message: 'rate limit reached' };
      expect(toSafeError(rateLimitErr)).toEqual({
        code: 'rate_limited',
        message: 'rate limit reached'
      });

      // Other status (e.g. 500, 502) -> upstream_error
      const upstreamErr = { status: 500, message: 'provider failed' };
      expect(toSafeError(upstreamErr)).toEqual({
        code: 'upstream_error',
        message: 'provider failed'
      });

      // Redacts secrets in message
      const secretErr = { status: 400, message: 'request blocked by a guardrail: sk-nrouter-abc123456' };
      expect(toSafeError(secretErr)).toEqual({
        code: 'guardrail_blocked',
        message: 'request blocked by a guardrail: [redacted]'
      });
    });

    it('survives duplicated SDK instance where error class has right name but different identity', () => {
      const StubGuardrailBlockedError = class nRouterGuardrailBlockedError extends Error {};
      const StubAuthError = class nRouterAuthenticationError extends Error {};
      const StubCreditError = class nRouterCreditError extends Error {};
      const StubBudgetError = class nRouterBudgetExceededError extends Error {};
      const StubRateLimitError = class nRouterRateLimitError extends Error {};
      const StubUpstreamError = class nRouterError extends Error {};

      expect(toSafeError(new StubGuardrailBlockedError('blocked content'))).toEqual({
        code: 'guardrail_blocked',
        message: 'blocked content'
      });
      expect(toSafeError(new StubAuthError('invalid key'))).toEqual({
        code: 'auth_failed',
        message: 'invalid key'
      });
      expect(toSafeError(new StubCreditError('no credits'))).toEqual({
        code: 'insufficient_credit',
        message: 'no credits'
      });
      expect(toSafeError(new StubBudgetError('over budget'))).toEqual({
        code: 'insufficient_credit',
        message: 'over budget'
      });
      expect(toSafeError(new StubRateLimitError('rate limit'))).toEqual({
        code: 'rate_limited',
        message: 'rate limit'
      });
      expect(toSafeError(new StubUpstreamError('upstream issue'))).toEqual({
        code: 'upstream_error',
        message: 'upstream issue'
      });

      // Direct mapErrorClass with right name but different identity
      expect(mapErrorClass(StubGuardrailBlockedError)).toBe('guardrail_blocked');
      expect(mapErrorClass(StubAuthError)).toBe('auth_failed');
      expect(mapErrorClass(StubCreditError)).toBe('insufficient_credit');
      expect(mapErrorClass(StubBudgetError)).toBe('insufficient_credit');
      expect(mapErrorClass(StubRateLimitError)).toBe('rate_limited');
      expect(mapErrorClass(StubUpstreamError)).toBe('upstream_error');
    });
  });

  describe('isModelFallbackEligible', () => {
    it('accepts a 404 that names model_not_found', () => {
      expect(isModelFallbackEligible(classifyError('model_not_found', 'no such model', 404))).toBe(true);
      expect(isModelFallbackEligible({ status: 404, code: 'model_not_found', message: 'x' })).toBe(true);
    });

    it('accepts a code-less 404 the SDK classified as a missing model', () => {
      const err = classifyError(null, 'model "m" not found', 404);
      expect(err).toBeInstanceOf(nRouterNotFoundError);
      expect(isModelFallbackEligible(err)).toBe(true);
      expect(isModelFallbackEligible({ status: 404, code: null, kind: 'not_found' })).toBe(true);
    });

    it('accepts a 503, with or without the service_unavailable code', () => {
      expect(isModelFallbackEligible(classifyError('service_unavailable', 'down', 503))).toBe(true);
      expect(isModelFallbackEligible(classifyError(null, 'down', 503))).toBe(true);
      expect(isModelFallbackEligible({ status: 503 })).toBe(true);
    });

    it('rejects a 404 that is not about a model', () => {
      expect(isModelFallbackEligible(classifyError(null, 'job not found', 404))).toBe(false);
      expect(isModelFallbackEligible({ status: 404, message: 'model not found' })).toBe(false);
      expect(isModelFallbackEligible({ status: 404, code: 'something_else', kind: 'not_found' })).toBe(false);
    });

    it('rejects a 503 that is a failed credit check or carries an unknown code', () => {
      expect(isModelFallbackEligible(classifyError('credit_check_failed', 'x', 503))).toBe(false);
      expect(isModelFallbackEligible({ status: 503, code: 'mystery' })).toBe(false);
    });

    it('rejects auth, credit, budget, rate-limit and guardrail refusals', () => {
      expect(isModelFallbackEligible(classifyError(null, 'bad key', 401))).toBe(false);
      expect(isModelFallbackEligible(classifyError(null, 'forbidden', 403))).toBe(false);
      expect(isModelFallbackEligible(classifyError(null, 'insufficient credits', 402))).toBe(false);
      expect(isModelFallbackEligible(classifyError(null, 'budget exceeded', 402))).toBe(false);
      expect(isModelFallbackEligible(classifyError(null, 'slow down', 429))).toBe(false);
      expect(isModelFallbackEligible(classifyError(null, 'request blocked by a guardrail', 400))).toBe(false);
      expect(isModelFallbackEligible(new nRouterGuardrailBlockedError('blocked', { status: 503 }))).toBe(false);
    });

    it('rejects other upstream statuses, transport failures and aborts', () => {
      expect(isModelFallbackEligible(classifyError(null, 'bad gateway', 502))).toBe(false);
      expect(isModelFallbackEligible(classifyError(null, 'timeout', 504))).toBe(false);
      expect(isModelFallbackEligible(classifyError(null, 'boom', 500))).toBe(false);
      expect(isModelFallbackEligible(new nRouterError('network down'))).toBe(false);
      expect(isModelFallbackEligible(new FakeAbortError('aborted'))).toBe(false);
      const abortedWithStatus = Object.assign(new FakeAbortError('aborted'), { status: 503 });
      expect(isModelFallbackEligible(abortedWithStatus)).toBe(false);
    });

    it('rejects non-errors and package errors', () => {
      expect(isModelFallbackEligible(undefined)).toBe(false);
      expect(isModelFallbackEligible(null)).toBe(false);
      expect(isModelFallbackEligible('503')).toBe(false);
      expect(isModelFallbackEligible({ status: '503' })).toBe(false);
      expect(isModelFallbackEligible(new SupportAgentError('upstream_error', 'x'))).toBe(false);
    });
  });
});
