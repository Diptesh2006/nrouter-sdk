import type { ChatRunner, ChatRunnerResponse } from './chat';
import { configurationError, createError, parseErrorBody, transportError } from './errors';
import { metaFromHeaders } from './meta';
import type { NRouterResponse, ResponseMeta } from './types';

export async function jsonRequest(
  runner: ChatRunner,
  path: string,
  body: Record<string, unknown>,
): Promise<NRouterResponse<Record<string, unknown>>> {
  const res = await runner.request(path, body);
  const meta = metaFromHeaders(res.headers);

  if (res.status < 200 || res.status >= 300) {
    throw gatewayFailure(res, meta);
  }

  // A 2xx that is not JSON is a REAL response the caller was BILLED for —
  // audio bytes, a video body, an SSE stream. CONFIGURATION, not transport,
  // and the distinction is money: `transportError` is retryable, so a caller's
  // ordinary `while (isRetryable(e))` loop would resend an already-charged
  // POST at whatever rate the loop turns. The wrong method was called for this
  // endpoint and no retry changes that. Same refusal, same reasoning, as
  // chat.ts REFUSAL 1 and multimodal.ts `requireJson`.
  //
  // `status` and `meta` are carried deliberately: without them the failure
  // reports status null — "never reached the gateway" — on a request that
  // plainly did, and the request id, the caller's only join key to the spend
  // row, would exist nowhere but a message string.
  if (!isJson(res.contentType)) {
    throw configurationError(
      `${path} returned ${res.status} with content-type ` +
        `"${res.contentType || 'none'}", which is not JSON. Use the raw-bytes ` +
        'path for binary or streaming endpoints — parsing this as JSON would ' +
        'report success with an empty body for a request that was billed.',
      { status: res.status, meta },
    );
  }

  let decoded: unknown;
  try {
    decoded = JSON.parse(res.text);
  } catch (cause) {
    throw transportError(`could not parse JSON returned by ${path}`, {
      status: res.status,
      meta,
      cause,
    });
  }

  if (!isRecord(decoded)) {
    throw transportError(`${path} returned JSON that is not an object`, {
      status: res.status,
      meta,
    });
  }

  const envelope = parseErrorBody(decoded);
  if (envelope.code || envelope.message) {
    throw createError(envelope.message ?? 'nRouter request failed', {
      code: envelope.code,
      status: res.status,
      meta,
    });
  }

  return { body: decoded, meta };
}

function gatewayFailure(res: ChatRunnerResponse, meta: ResponseMeta): Error {
  let parsed: unknown = null;
  try {
    parsed = JSON.parse(res.text);
  } catch {
    parsed = { error: { message: res.text } };
  }
  const envelope = parseErrorBody(parsed);
  return createError(envelope.message ?? 'nRouter request failed', {
    code: envelope.code,
    status: res.status,
    meta,
  });
}

function isJson(contentType: string): boolean {
  return /^application\/(?:[^+;]+\+)?json(?:;|$)/i.test(contentType);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
