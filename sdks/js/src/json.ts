import type { ChatRunner, ChatRunnerResponse } from './chat';
import { createError, parseErrorBody, transportError } from './errors';
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

  if (!isJson(res.contentType)) {
    throw transportError(`${path} returned ${res.contentType || 'no content type'}, not JSON`, {
      status: res.status,
      meta,
    });
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
