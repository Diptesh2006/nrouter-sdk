// The high-level buffered chat helper: playground parity in one call.
//
// Everything the hosted playground can set on a request is reachable through
// `NRouterCallOptions`, and every response comes back paired with the `x-nr-*`
// metadata the gateway reported for it. An option a user can toggle in our own
// UI and cannot express here is a feature that exists only inside our UI.
//
// This module takes a `ChatRunner`, not the OpenAI client. The transport stays
// the integrator's — their `fetch`, timeout, retries, proxy and headers — and
// this file owns only what happens to the bytes that come back. That seam is
// also what makes every refusal below unit-testable with no network and no
// vendor mock: a two-line fake runner reproduces a streaming response, a
// truncated body or a 429 exactly.
//
// Nothing here re-implements a cross-cutting concern that a sibling already
// owns. Error classification, key redaction, `Retry-After` parsing and error-
// envelope parsing all live in ./errors, and metadata parsing lives in ./meta.
// A second copy of any of them is how two code paths start disagreeing about
// the same header.

import { metaFromHeaders, EMPTY_META } from './meta';
import type { HeaderSource } from './meta';
import {
  nRouterError,
  createError,
  configurationError,
  transportError,
  parseErrorBody,
  parseRetryAfter,
  errorEnvelopeOnSuccess,
} from './errors';
import { buildSamplingParams } from './sampling';
import { buildChatBody } from './options';
import type { NRouterCallOptions, NRouterResponse, ResponseMeta } from './types';

/** The gateway's buffered chat endpoint. Path only — the runner owns the base URL. */
const CHAT_PATH = '/chat/completions';

/**
 * The gateway's Anthropic-native endpoint. Path only, same rule.
 *
 * NOT an alternative spelling of the endpoint above — it is the ONLY text wire
 * a Claude or Bedrock model can be reached on. Measured in the gateway's own
 * source: Anthropic declares `chat_completions: None`
 * (`nrouter-rust-gateway/src/sdk/providers/anthropic/transformation.rs:55-57`)
 * and Bedrock does the same (`bedrock/transformation.rs:862`), so `transform.rs`
 * answers a 404 UnknownModel reading "is not available on
 * /v1/chat/completions". Sending every model to one path made every id this
 * package advertises in its own keywords — `claude`, `bedrock` — uncallable
 * through `nr.chat()` and `nr.stream()`.
 */
export const MESSAGES_PATH = '/messages';

/**
 * Anthropic REQUIRES `max_tokens`; a body without it is refused outright.
 *
 * The same 1024 the hosted playground injects
 * (`nrouter-app/src/app/api/nrouter-proxy/chat/route.ts:308-310`). Matching it
 * matters more than the number does: a snippet copied out of the dashboard has
 * to behave the same way from npm.
 */
const DEFAULT_ANTHROPIC_MAX_TOKENS = 1024;

/** OpenAI allows 0–2; Anthropic 400s above 1. */
const ANTHROPIC_MAX_TEMPERATURE = 1;

/**
 * OpenAI fields Anthropic's Messages wire has no equivalent for.
 *
 * Ported verbatim from the app's translator, reasons and all, because a drop
 * list without reasons is how a MATERIAL field ends up on it later. Every entry
 * here is a sampling nudge or a no-op — none of them changes what safety ran or
 * what the model was asked. `n` is the exception and is not dropped: it is
 * REFUSED, below, because answering an `n: 3` request with one choice is a fake
 * success the caller pays for.
 *
 *   stream_options    Anthropic streams usage unconditionally and rejects the
 *                     key: "stream_options: Extra inputs are not permitted".
 *   frequency_penalty / presence_penalty / logit_bias / seed / logprobs /
 *   top_logprobs      no Anthropic equivalent.
 *   response_format   Anthropic has no JSON-mode switch on this wire.
 *   user              never forwarded anyway — the gateway derives identity
 *                     from the authenticated key (gateway rules §4b).
 */
const OPENAI_ONLY_FIELDS = [
  'stream_options',
  'frequency_penalty',
  'presence_penalty',
  'logit_bias',
  'n',
  'seed',
  'logprobs',
  'top_logprobs',
  'response_format',
  'user',
] as const;

/** Key under which a failed `compare` arm parks its error. See `compare`. */
export const COMPARE_ERROR_KEY = 'nrouter_error';

/** One response, exactly as the transport saw it and before anything is parsed. */
export interface ChatRunnerResponse {
  status: number;
  headers: HeaderSource;
  /**
   * The body UNPARSED. Deciding whether a 2xx is even parseable is this
   * module's job — a runner that helpfully called `JSON.parse` for us would
   * have already destroyed the evidence refusal #1 depends on.
   */
  text: string;
  /** Reported separately so the JSON/not-JSON decision never depends on the body. */
  contentType: string;
}

/**
 * The transport seam. One method, deliberately: the caller wires it to the
 * `nRouter` client, to `fetch`, or to a fake in a test, and this module never
 * learns which.
 */
export interface ChatRunner {
  request(path: string, body: unknown): Promise<ChatRunnerResponse>;
}

/**
 * Run one buffered chat completion with full playground parity.
 *
 * Resolves to the decoded body paired with the gateway's per-request metadata:
 * cost, token counts, cache outcome, and the model that actually served it.
 * Cost is `null` when the model is unpriced — never `0`, because no enabled
 * model is free (Rule #28).
 *
 * Rejects with an `nRouterError` and nothing else, so one `catch` covers every
 * failure mode. Every rejection raised after the response headers arrived
 * carries that response's context.
 */
export async function chat(
  runner: ChatRunner,
  opts: NRouterCallOptions,
): Promise<NRouterResponse<Record<string, unknown>>> {
  const sampling = buildSamplingParams({
    advanced: opts.advancedSampling ?? false,
    model: opts.model,
    provider: opts.modelProvider ?? null,
    temperature: opts.temperature,
    topP: opts.topP,
  });
  const body = buildChatBody(opts, sampling);

  // REFUSAL 0 — before a single byte leaves the process.
  //
  // `buildChatBody` never sets `stream` itself, so it can only arrive through
  // `opts.extra`. Sent as-is it produces an SSE stream that this buffered
  // helper would refuse at refusal #1 — but only AFTER the provider had been
  // called and the customer already billed. Refusing at the door is the one
  // place the refusal costs nothing.
  //
  // CONFIGURATION for the same reason refusal #1 is: the wrong helper was
  // called, and that is not a condition any retry improves.
  if (body['stream'] === true) {
    throw configurationError(
      'chat() is the BUFFERED helper and cannot consume a stream; remove ' +
        '`stream: true` from `extra` or use the streaming entry point. Sent ' +
        'as-is it would bill a provider call whose body this helper cannot ' +
        'return.',
    );
  }

  // THE WIRE, chosen from the model and before anything is sent.
  //
  // Picking the PATH is only half the job, and the other half is what the
  // hosted playground learned the expensive way. That route selected
  // `/v1/messages` for `claude*` while still sending the OpenAI request shape
  // at it and handing the Anthropic response shape back to a client that reads
  // `choices[0].delta.content`. Its comment records the measurement: "a 200 in
  // ~14s that rendered an EMPTY BOX while the tokens were billed". A silent
  // success delivering no product is worse than an error — nothing pages on it
  // and the spend is real. So the request is TRANSLATED on the way out and the
  // response is translated on the way back, or neither.
  //
  // This is a SHIM and its deletion condition is upstream, not here: when the
  // gateway stops declaring `chat_completions: None` for Anthropic and serves
  // `claude*` on `/v1/chat/completions`, every line of it goes, because
  // `toOpenAIChatCompletion` already passes an OpenAI-shaped document through
  // untouched and would degrade to a no-op on that day.
  const messagesWire = usesMessagesWire(opts.model, opts.modelProvider);
  if (messagesWire) {
    refuseUnservableOnMessagesWire(body);
  }
  const res = await send(
    runner,
    messagesWire ? MESSAGES_PATH : CHAT_PATH,
    messagesWire ? toAnthropicMessagesRequest(body).body : body,
  );
  const meta = metaFromHeaders(res.headers);

  if (res.status < 200 || res.status >= 300) {
    throw gatewayFailure(res, meta);
  }

  // REFUSAL 1 — a 2xx that is not JSON is a REAL RESPONSE the caller was
  // billed for: audio from /audio/speech, a video body, or an SSE stream.
  // `JSON.parse` on it either throws or, worse, yields something empty — and
  // then the call reports success while the customer receives nothing for
  // money that is already spent.
  //
  // CONFIGURATION, deliberately, NOT transport. This was a retryable transport
  // error in the Go draft and a reviewer flagged it P1: a caller's generic
  // `if (isRetryable(e)) retry` loop would repeat a BILLED request forever,
  // burning real credits at whatever rate the loop turns. The wrong method was
  // called for this endpoint, and that condition is permanent.
  if (!res.contentType.toLowerCase().includes('json')) {
    throw configurationError(
      `gateway returned ${res.status} with content-type "${res.contentType}", ` +
        'which is not JSON. Use the raw-bytes path for binary or streaming ' +
        'endpoints (/audio/speech, /videos/{id}/content, or "stream": true) — ' +
        'parsing this as JSON would report success with an empty body for a ' +
        'request that was billed.',
      // REFUSAL 3 — the response context. Without `status` and `meta` this
      // failure would carry status null ("never reached the gateway") on a
      // request that plainly did, and the request id — the caller's only join
      // key to the spend row — would exist nowhere but a message string.
      { status: res.status, meta },
    );
  }

  // REFUSAL 2 — a 2xx whose JSON does not parse is a TRUNCATED or corrupted
  // billed response, not an empty one. Returning `{}` here hands back a
  // completion with no choices and lets the caller conclude the model said
  // nothing.
  //
  // This one IS transient: the identical request can return an intact body
  // next time, so it is a transport error and a retry loop is right to take
  // it. That is the whole reason refusals #1 and #2 are different kinds
  // despite both being "a 2xx we could not read".
  let decoded: unknown;
  try {
    decoded = JSON.parse(res.text) as unknown;
  } catch (cause) {
    throw transportError(
      `gateway returned ${res.status} with unparseable JSON ` +
        `(${describe(cause)}); the request was billed but the body did not ` +
        'arrive intact.',
      { status: res.status, meta, cause },
    );
  }

  // A JSON scalar, array or null where an object was promised is the same
  // corruption one step later: `res.body.choices` on a `null` throws inside
  // the caller's code, far from the request id that would have explained it.
  if (decoded === null || typeof decoded !== 'object' || Array.isArray(decoded)) {
    throw transportError(
      `gateway returned ${res.status} with a JSON body that is not an object; ` +
        'the request was billed but the response is not shaped like a ' +
        'completion.',
      { status: res.status, meta },
    );
  }

  // SDK-026 — A GUARDRAIL BLOCK ARRIVES AS HTTP 200.
  //
  // The gateway serves PostCallVerdict::Blocked by REPLACING the body with
  // {"error":{"type":"guardrail_blocked","message":...}} while keeping the
  // UPSTREAM status: axum_status is computed from the provider's status before
  // the verdict is consulted (chat_completions.rs:527 vs ~598). So the one
  // refusal a caller most needs to see arrives labelled 200, and every "2xx =
  // success" client hands it back as a completion with no `choices`. The
  // application shows an empty answer and the guardrail protects nobody
  // downstream, while reading as configured in the dashboard.
  //
  // The test is deliberately narrow. A real completion never carries a
  // top-level `error`, and the withheld document carries nothing ELSE — so
  // requiring both (an error object with a message, AND no completion-shaped
  // key beside it) cannot swallow a legitimate reply whose payload happens to
  // mention an error.
  const envelope = errorEnvelopeOnSuccess(decoded);
  if (envelope) {
    throw createError(envelope.message, {
      code: envelope.code,
      status: res.status,
      meta,
    });
  }

  // Translated only on the wire that needs it. `toOpenAIChatCompletion` is a
  // pass-through for anything OpenAI-shaped, but running it on every response
  // would put the buffered OpenAI path — by far the busiest — behind a shape
  // heuristic it has no reason to be behind.
  const decodedBody = messagesWire
    ? (toOpenAIChatCompletion(decoded, {
        requestedModel: opts.model,
        requestId: meta.requestId,
      }) as Record<string, unknown>)
    : (decoded as Record<string, unknown>);

  return { body: decodedBody, meta };
}


// ---------------------------------------------------------------------------
// The Anthropic Messages wire
//
// A bounded translator, ported from the surface that already proved it in
// production: nrouter-app `src/lib/nrouter-proxy/anthropic-translation.ts`.
// Two rules it inherits and must keep:
//
//   * NEVER invent usage. A response with nothing countable carries NO usage
//     block — never a zero. Rule #28 and gateway §4f gate 3: absent is
//     `Unpriced`, and a confident `0` reads as a free request.
//   * NEVER silently drop a material field. A field Anthropic cannot carry is
//     listed in OPENAI_ONLY_FIELDS with its reason; `tools` are translated
//     rather than dropped, because a dropped tool definition produces a
//     normal-looking answer that ignored the caller's tools — the same fake
//     success as the empty box, and billed the same.
// ---------------------------------------------------------------------------

/**
 * True when this model must be called on `/messages` rather than
 * `/chat/completions`.
 *
 * DELIBERATELY NOT `isClaudeModel` from ./sampling, even though the two overlap
 * almost entirely. That predicate answers a different question — "does this
 * model enforce temperature XOR top_p" — and widening it to cover the Bedrock
 * ids that are NOT Claude (Nova, Titan, Llama) would change which sampling
 * params get suppressed for models that never had the XOR rule. Two questions,
 * two predicates.
 *
 * The id arms mirror the playground's
 * (`nrouter-app/src/app/api/nrouter-proxy/chat/route.ts:298-307`) with one
 * widening: `includes('claude')` rather than `startsWith`, because this SDK's
 * own README calls models by their prefixed aliases
 * (`anthropic/claude-sonnet-4-5-…`, `us.anthropic.claude-opus-4-1-v1:0`) which
 * a prefix match sends to the path that 404s them.
 *
 * The `provider` arm covers a private alias that hides the family name. It uses
 * the same attribution the caller already passes to the sampling policy, so it
 * costs no new option. Both failure directions are LOUD — a wrong wire is a
 * 404, never a wrong answer — which is why a heuristic is acceptable here at
 * all.
 */
export function usesMessagesWire(model: string, provider?: string | null): boolean {
  const id = (model ?? '').toLowerCase();
  if (
    id.includes('claude') ||
    id.startsWith('bedrock-') ||
    id.includes('haiku') ||
    id.includes('sonnet') ||
    id.includes('opus')
  ) {
    return true;
  }
  const attribution = (provider ?? '').toLowerCase();
  return attribution.includes('anthropic') || attribution.includes('bedrock');
}

/**
 * Refuse, before sending, what this wire cannot serve honestly.
 *
 * `n` is the only OpenAI field whose omission changes the ANSWER rather than
 * the sampling. Anthropic returns exactly one message and has no `n`, so a
 * dropped `n: 3` comes back as a single choice that reads like a success — and
 * the customer paid for it. The playground refuses the same request for the
 * same reason (route.ts:325-336).
 *
 * CONFIGURATION, so `isRetryable` says false: no retry turns a wire without
 * `n` into one that has it, and a caller's generic retry loop must not spin on
 * it. Raised BEFORE the runner, which is the one place a refusal costs nothing.
 */
export function refuseUnservableOnMessagesWire(body: Record<string, unknown>): void {
  const n = body['n'];
  if (typeof n === 'number' && n > 1) {
    throw configurationError(
      `this model answers on the Anthropic Messages wire, which returns exactly ` +
        `one completion, so n=${n} cannot be served. Send n=1, or call an ` +
        'OpenAI-wire model. Dropping the field would return one choice and ' +
        'report success for a request that asked for more and was billed.',
    );
  }
}

/** The translated body, plus the fields this wire could not carry. */
export interface AnthropicRequestResult {
  body: Record<string, unknown>;
  /** Dropped because Anthropic has no equivalent. Diagnostic only. */
  dropped: string[];
}

/**
 * Translate an OpenAI chat-completions body into an Anthropic Messages body.
 *
 * The three structural moves, each of which is a hard 400 if skipped:
 *   1. `system` messages come OUT of `messages` and become the top-level
 *      `system` field. Anthropic rejects `role: "system"` inside `messages`.
 *   2. `max_tokens` is REQUIRED.
 *   3. `stop` becomes `stop_sequences`, and must be an array.
 */
export function toAnthropicMessagesRequest(
  openai: Record<string, unknown>,
): AnthropicRequestResult {
  const dropped: string[] = [];
  const out: Record<string, unknown> = { model: openai['model'] };

  const systemChunks: string[] = [];
  const messages: Record<string, unknown>[] = [];
  const input = Array.isArray(openai['messages']) ? (openai['messages'] as unknown[]) : [];

  for (const raw of input) {
    const turn = asObject(raw);
    if (turn === null) continue;
    const role = typeof turn['role'] === 'string' ? turn['role'] : '';

    if (role === 'system' || role === 'developer') {
      // Anthropic's `system` is a plain string; flatten whatever text is there.
      const content = turn['content'];
      if (typeof content === 'string') {
        systemChunks.push(content);
      } else if (Array.isArray(content)) {
        for (const part of content) {
          const p = asObject(part);
          if (p?.['type'] === 'text' && typeof p['text'] === 'string') {
            systemChunks.push(p['text']);
          }
        }
      }
      continue;
    }

    // Anthropic has no `tool` role: a result replays as a USER turn carrying a
    // tool_result block. Dropping it makes the model answer as if the tool
    // never ran, on a conversation the caller is paying to replay.
    if (role === 'tool') {
      const content = turn['content'];
      messages.push({
        role: 'user',
        content: [
          {
            type: 'tool_result',
            tool_use_id:
              typeof turn['tool_call_id'] === 'string' ? turn['tool_call_id'] : '',
            content: typeof content === 'string' ? content : JSON.stringify(content ?? ''),
          },
        ],
      });
      continue;
    }

    if (role === 'assistant' && Array.isArray(turn['tool_calls'])) {
      const blocks: Record<string, unknown>[] = [];
      const text = typeof turn['content'] === 'string' ? turn['content'] : '';
      if (text) blocks.push({ type: 'text', text });
      for (const call of turn['tool_calls'] as unknown[]) {
        const c = asObject(call);
        const fn = asObject(c?.['function']);
        let args: unknown = {};
        try {
          const serialized = fn?.['arguments'];
          args = typeof serialized === 'string' && serialized ? JSON.parse(serialized) : {};
        } catch {
          // A malformed argument string from a PREVIOUS turn must not 400 the
          // whole history. Replay it as an empty object and let the model see
          // the call happened.
          args = {};
        }
        blocks.push({
          type: 'tool_use',
          id: typeof c?.['id'] === 'string' ? c['id'] : '',
          name: typeof fn?.['name'] === 'string' ? fn['name'] : '',
          input: args,
        });
      }
      messages.push({ role: 'assistant', content: blocks });
      continue;
    }

    if (role !== 'user' && role !== 'assistant') continue;
    messages.push({ role, content: contentToAnthropic(turn['content']) });
  }

  if (systemChunks.length > 0) out['system'] = systemChunks.join('\n\n');
  out['messages'] = messages;

  const maxTokens = finite(openai['max_tokens']);
  out['max_tokens'] =
    maxTokens !== null && maxTokens > 0 ? maxTokens : DEFAULT_ANTHROPIC_MAX_TOKENS;

  const stop = openai['stop'];
  if (typeof stop === 'string' && stop) {
    out['stop_sequences'] = [stop];
  } else if (Array.isArray(stop) && stop.length > 0) {
    out['stop_sequences'] = stop.filter((s) => typeof s === 'string' && s.length > 0);
  }

  const temperature = finite(openai['temperature']);
  if (temperature !== null) {
    // CLAMPED, not refused. OpenAI's range is 0–2 and Anthropic's is 0–1, so
    // anything above 1 is a hard 400 upstream. Clamping is lossy and
    // deliberate: the alternative refuses a value our own dashboard slider
    // offers, and the sampling policy above already let it through.
    out['temperature'] = Math.min(Math.max(temperature, 0), ANTHROPIC_MAX_TEMPERATURE);
  }
  const topP = finite(openai['top_p']);
  if (topP !== null) out['top_p'] = topP;

  if (openai['stream'] === true) out['stream'] = true;

  const tools = toolsToAnthropic(openai['tools']);
  if (tools) {
    out['tools'] = tools;
    const choice = toolChoiceToAnthropic(openai['tool_choice']);
    if (choice) out['tool_choice'] = choice;
  } else if (openai['tools'] !== undefined) {
    dropped.push('tools');
  }

  for (const field of OPENAI_ONLY_FIELDS) {
    if (openai[field] !== undefined) dropped.push(field);
  }

  // Everything the gateway itself reads — the `nrouter_*` extra_body fields —
  // is forwarded UNCHANGED. It is stripped at the gateway before the provider
  // sees the body, so it belongs on this wire exactly as it does on the other;
  // dropping it would silently disable prompt templates and the response cache
  // for every Claude call.
  for (const key of Object.keys(openai)) {
    if (key.startsWith('nrouter_')) out[key] = openai[key];
  }

  return { body: out, dropped };
}

/**
 * True when a decoded document is an Anthropic Messages response.
 *
 * An OpenAI document ALWAYS carries `choices`, so that test comes first and
 * makes this a pass-through the day the gateway grows its own façade.
 */
export function isAnthropicMessageResponse(json: unknown): boolean {
  const doc = asObject(json);
  if (doc === null) return false;
  if (Array.isArray(doc['choices'])) return false;
  return doc['type'] === 'message' || Array.isArray(doc['content']);
}

/**
 * Translate a buffered Anthropic Messages response into OpenAI's
 * `chat.completion` shape — the half without which `chatText()` returns `''`
 * on a real, billed answer.
 *
 * Anything that does not look Anthropic-shaped is returned UNTOUCHED, by
 * identity, so this is a no-op on an OpenAI document.
 */
export function toOpenAIChatCompletion(
  anthropic: unknown,
  opts: { requestedModel?: string; requestId?: string | null } = {},
): unknown {
  if (!isAnthropicMessageResponse(anthropic)) return anthropic;
  const doc = anthropic as Record<string, unknown>;

  const blocks = Array.isArray(doc['content']) ? (doc['content'] as unknown[]) : [];
  const textParts: string[] = [];
  const toolCalls: Record<string, unknown>[] = [];

  for (const block of blocks) {
    const b = asObject(block);
    if (b === null) continue;
    if (b['type'] === 'text' && typeof b['text'] === 'string') {
      textParts.push(b['text']);
    } else if (b['type'] === 'tool_use') {
      toolCalls.push({
        id: typeof b['id'] === 'string' ? b['id'] : '',
        type: 'function',
        function: {
          name: typeof b['name'] === 'string' ? b['name'] : '',
          arguments: JSON.stringify(b['input'] ?? {}),
        },
      });
    }
    // `thinking` blocks are deliberately not surfaced: OpenAI's shape has no
    // standard field for them, and inventing one puts model reasoning on a
    // customer surface no SDK reads.
  }

  const text = textParts.join('');
  const message: Record<string, unknown> = {
    role: 'assistant',
    // OpenAI's convention is `null` content on a pure tool call.
    content: text.length > 0 ? text : toolCalls.length > 0 ? null : '',
  };
  if (toolCalls.length > 0) message['tool_calls'] = toolCalls;

  const out: Record<string, unknown> = {
    id: `chatcmpl-${(typeof doc['id'] === 'string' && doc['id']) || opts.requestId || 'nrouter'}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model: (typeof doc['model'] === 'string' && doc['model']) || opts.requestedModel || '',
    choices: [
      {
        index: 0,
        message,
        finish_reason: toFinishReason(doc['stop_reason']),
      },
    ],
  };

  // Absent usage means NO usage key — never a zero-filled block.
  const usage = toOpenAIUsage(doc['usage']);
  if (usage !== null) out['usage'] = usage;
  return out;
}

/**
 * Map Anthropic's `stop_reason` onto OpenAI's `finish_reason`.
 *
 * `max_tokens` → `length` is the load-bearing one: it is the ONLY thing that
 * distinguishes a truncated answer from a genuinely short one, and a caller
 * shown `stop` bills for a cut-off reply believing it complete. An unknown
 * reason answers `stop` rather than the raw Anthropic token, because leaking a
 * provider-specific string onto a customer-visible field is gateway §4f gate 9.
 */
function toFinishReason(stopReason: unknown): string {
  if (stopReason === 'max_tokens') return 'length';
  if (stopReason === 'tool_use') return 'tool_calls';
  return 'stop';
}

/**
 * Translate an Anthropic `usage` block into OpenAI's, or `null`.
 *
 * `prompt_tokens` SUMS `input_tokens` with the two cache counters when the
 * provider reported them. That is arithmetic over numbers Anthropic returned,
 * not an invention: cache-read and cache-creation tokens are prompt tokens the
 * customer was charged for, and omitting them under-reports the input side.
 * Cost itself still comes from the gateway's `x-nr-request-cost` header; this
 * function computes no money.
 */
function toOpenAIUsage(
  usage: unknown,
): { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null {
  const u = asObject(usage);
  if (u === null) return null;

  const input = finite(u['input_tokens']);
  const cacheCreate = finite(u['cache_creation_input_tokens']);
  const cacheRead = finite(u['cache_read_input_tokens']);
  const output = finite(u['output_tokens']);

  // Nothing countable at all → no usage block. Never zeros (Rule #28).
  if (input === null && cacheCreate === null && cacheRead === null && output === null) {
    return null;
  }

  const prompt = (input ?? 0) + (cacheCreate ?? 0) + (cacheRead ?? 0);
  const completion = output ?? 0;
  return { prompt_tokens: prompt, completion_tokens: completion, total_tokens: prompt + completion };
}

/** One OpenAI message's content → Anthropic content (string or block array). */
function contentToAnthropic(content: unknown): unknown {
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return '';

  const blocks: Record<string, unknown>[] = [];
  for (const raw of content) {
    const part = asObject(raw);
    if (part === null) continue;
    if (part['type'] === 'text' && typeof part['text'] === 'string') {
      blocks.push({ type: 'text', text: part['text'] });
      continue;
    }
    if (part['type'] === 'image_url') {
      const url = asObject(part['image_url'])?.['url'];
      if (typeof url !== 'string' || !url) continue;
      // A `data:` URI carries its own media type, so it must be SPLIT rather
      // than handed over whole — passing the full URI as a URL is a 400.
      const dataUri = /^data:([^;,]+);base64,([\s\S]*)$/.exec(url);
      blocks.push(
        dataUri
          ? { type: 'image', source: { type: 'base64', media_type: dataUri[1], data: dataUri[2] } }
          : { type: 'image', source: { type: 'url', url } },
      );
      continue;
    }
    // An unrecognised part is skipped rather than forwarded: an unknown key
    // reaches Anthropic verbatim and 400s the whole turn.
  }
  return blocks;
}

/** OpenAI `tools` → Anthropic `tools`. Shape only; names and schemas pass through. */
function toolsToAnthropic(tools: unknown): Record<string, unknown>[] | undefined {
  if (!Array.isArray(tools)) return undefined;
  const out: Record<string, unknown>[] = [];
  for (const tool of tools) {
    const fn = asObject(asObject(tool)?.['function']);
    if (fn === null || typeof fn['name'] !== 'string') continue;
    const parameters = fn['parameters'];
    out.push({
      name: fn['name'],
      ...(typeof fn['description'] === 'string' ? { description: fn['description'] } : {}),
      // Anthropic requires an object schema; OpenAI's `parameters` is the same
      // JSON Schema under a different key.
      input_schema:
        parameters !== null && typeof parameters === 'object'
          ? parameters
          : { type: 'object', properties: {} },
    });
  }
  return out.length > 0 ? out : undefined;
}

/** OpenAI `tool_choice` → Anthropic `tool_choice`. */
function toolChoiceToAnthropic(choice: unknown): Record<string, unknown> | undefined {
  if (choice === 'auto') return { type: 'auto' };
  if (choice === 'required') return { type: 'any' };
  // Anthropic expresses "none" by omitting tools, so there is nothing to send.
  if (choice === 'none') return undefined;
  const name = asObject(asObject(choice)?.['function'])?.['name'];
  return typeof name === 'string' ? { type: 'tool', name } : undefined;
}

/** A finite number, or null. `NaN` and `Infinity` are not counts. */
function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Narrow to a plain object; arrays and null are not one. */
function asObject(value: unknown): Record<string, unknown> | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}


/**
 * Pull the assistant's text out of a completion.
 *
 * Returns `''` rather than throwing on an unexpected shape, on purpose. The
 * body is already in the caller's hands and the metadata beside it is already
 * correct — cost, token counts and request id all survive. Throwing here would
 * destroy a response the caller PAID for over a convenience accessor, and it
 * would throw on the legitimate cases too: a guardrail-redacted turn, a
 * tool-call-only choice with `content: null`, a `finish_reason: "length"` cut
 * at zero tokens, and every provider that answers in content PARTS rather than
 * a bare string.
 *
 * `''` is honest here in a way `0` never is for cost: an empty completion is a
 * real thing a model returns, whereas a free request is not (Rule #28). A
 * caller who needs to distinguish "no text" from "unexpected shape" still has
 * the full body — this accessor takes nothing away.
 */
export function chatText(res: NRouterResponse<Record<string, unknown>>): string {
  const choices: unknown = res.body['choices'];
  if (!Array.isArray(choices) || choices.length === 0) {
    return '';
  }
  const message = pluck(pluck(choices[0], 'message'), 'content');
  if (typeof message === 'string') {
    return message;
  }
  // Content PARTS: the Anthropic-shaped and multimodal replies the gateway
  // relays through unchanged. Concatenating the text parts beats reporting
  // "no answer" for a response that plainly contains one.
  if (Array.isArray(message)) {
    let out = '';
    for (const part of message) {
      const text = pluck(part, 'text');
      if (typeof text === 'string') {
        out += text;
      }
    }
    return out;
  }
  return '';
}

/**
 * Run the same options against several models at once — the playground's
 * side-by-side compare, as one call.
 *
 * Results come back in the SAME ORDER as `models`, never in completion order,
 * so `models[i]` and `results[i]` always describe each other. Ordering by
 * whichever model answered first would silently label the fast model's answer
 * with the slow model's name on every run.
 *
 * PARTIAL FAILURE — the choice, and why:
 *
 * Concurrency is `Promise.allSettled`, not `Promise.all`. `all` rejects on the
 * FIRST failure and discards every sibling result, including the ones that
 * already succeeded and were already BILLED. Comparing four models and losing
 * three paid answers because the fourth alias was misspelled is exactly the
 * shape of loss this SDK exists to prevent.
 *
 * A failed arm therefore still occupies its slot, with its `nRouterError`
 * parked at `body[COMPARE_ERROR_KEY]` and read back through `compareError()`.
 * The two alternatives are both worse: throwing an aggregate at the end
 * collapses the whole call again, and an empty `{}` body is indistinguishable
 * from a model that answered with nothing. A sentinel key that no completion
 * carries is the only option that is at once non-lossy and unmistakable.
 *
 * The failed arm's `meta` keeps whatever the gateway managed to report before
 * failing — request id, limit source, auth reason — so the correlation path
 * survives the failure. Everything unknown stays `null` rather than being
 * filled in with a plausible zero.
 *
 * Concurrency is unbounded, matching the playground: a compare is a handful of
 * models chosen by hand, and this helper is not the place to invent a queue
 * the gateway's own RPM limiter already implements. A caller comparing dozens
 * should batch them and will get a typed `nRouterRateLimitError` per arm —
 * with `retryAfter` — rather than one collapsed failure, if they do not.
 */
export async function compare(
  runner: ChatRunner,
  opts: NRouterCallOptions,
  models: string[],
): Promise<NRouterResponse<Record<string, unknown>>[]> {
  const settled = await Promise.allSettled(
    models.map((model) => chat(runner, { ...opts, model })),
  );

  return settled.map((outcome) => {
    if (outcome.status === 'fulfilled') {
      return outcome.value;
    }
    const failure = normalize(outcome.reason);
    return {
      body: { [COMPARE_ERROR_KEY]: failure },
      meta: metaFromError(failure),
    };
  });
}

/**
 * The error from a failed `compare` arm, or `null` when that arm succeeded.
 *
 * Exported so a caller never has to string-match `COMPARE_ERROR_KEY` itself.
 * An implicit key convention is precisely the kind of contract that rots the
 * first time somebody renames it.
 */
export function compareError(
  res: NRouterResponse<Record<string, unknown>>,
): nRouterError | null {
  const parked: unknown = res.body[COMPARE_ERROR_KEY];
  return parked instanceof nRouterError ? parked : null;
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/**
 * Call the runner and normalize whatever it throws.
 *
 * The runner IS the transport, so a raw throw out of it is by definition a
 * transport failure — DNS, TLS, a dropped socket, an abort. Wrapping it here
 * is what lets `chat` promise it rejects with `nRouterError` and nothing else,
 * which is in turn what lets a caller write one `catch` instead of two. No
 * status is stamped: no HTTP exchange happened, and `isRetryable` already
 * declines an aborted cause, so a cancelled request is not retried as a blip.
 */
async function send(
  runner: ChatRunner,
  path: string,
  body: Record<string, unknown>,
): Promise<ChatRunnerResponse> {
  try {
    return await runner.request(path, body);
  } catch (cause) {
    throw normalize(cause);
  }
}

/**
 * Turn a non-2xx into a typed error.
 *
 * REFUSAL 4. Classification is `createError`'s — code when the gateway sent
 * one, then status, then the message — because the gateway's MAIN error path
 * sends no `code` at all (it emits `{"error":{"type","message"}}`), so keying
 * on `code` alone makes `guardrail_blocked` unreachable and tells a caller to
 * fix a request body that was never the problem.
 *
 * `parseErrorBody` reads the envelope BOTH ways — the gateway's nested
 * `{"error":{...}}` and a bare `{code,message}` — because a proxy in front of
 * the gateway may reshape it, and reading only the nested form turns every
 * typed refusal behind such a proxy into a generic one. It also redacts any
 * key that reached the message, which is why the message is never assembled
 * here from raw response text (Rule #5).
 */
function gatewayFailure(res: ChatRunnerResponse, meta: ResponseMeta): nRouterError {
  let envelope: unknown = null;
  try {
    envelope = JSON.parse(res.text) as unknown;
  } catch {
    // An unparseable ERROR body is ordinary — a proxy's HTML 502 page, an
    // empty 504. The status alone still classifies it correctly. The raw text
    // is deliberately NOT promoted into the message: it is unbounded and
    // unredacted, and this module cannot redact it (that lives in ./errors).
  }

  const { code, message } = parseErrorBody(envelope);

  return createError(message ?? 'nRouter request failed', {
    code,
    // REFUSAL 3 — status and metadata from the response that actually
    // happened, so the failure carries the request id, the limit source that
    // explains a 429 and the auth reason that explains a 401.
    status: res.status,
    meta,
    // REFUSAL 4 — `Retry-After` in BOTH RFC 9110 forms. Upstreams do send the
    // HTTP-date form and the gateway relays it unchanged; a delta-seconds-only
    // parse yields nothing for it and the caller retries before the provider
    // said to, which on a 429 is how a backoff becomes a hammer and the limit
    // stays tripped. ./errors owns the parse; this only supplies the header.
    retryAfter: parseRetryAfter(headerValue(res.headers, 'retry-after')),
  });
}

/**
 * Read one header from either shape a runner may hand back.
 *
 * `metaFromHeaders` covers the `x-nr-*` set but not `Retry-After`, which is a
 * standard header rather than one of ours. The record form is matched
 * case-insensitively: HTTP header names are case-insensitive, a `Headers`
 * object normalizes them and a plain object does not, so an exact-key lookup
 * would find `Retry-After` from one runner and miss it from another.
 */
function headerValue(headers: HeaderSource, name: string): string | null {
  const maybe = headers as { get?: (key: string) => string | null | undefined };
  if (typeof maybe.get === 'function') {
    return maybe.get(name) ?? null;
  }
  const record = headers as Record<string, string | string[] | undefined>;
  const wanted = name.toLowerCase();
  for (const key of Object.keys(record)) {
    if (key.toLowerCase() !== wanted) {
      continue;
    }
    const value = record[key];
    if (Array.isArray(value)) {
      return value.length > 0 ? (value[0] ?? null) : null;
    }
    return value ?? null;
  }
  return null;
}

/** Coerce any rejection into the one error type this module promises. */
function normalize(reason: unknown): nRouterError {
  if (reason instanceof nRouterError) {
    return reason;
  }
  return transportError(`the request did not reach the gateway: ${describe(reason)}`, {
    cause: reason,
  });
}

/**
 * Metadata for a `compare` arm that failed.
 *
 * Only what the gateway actually reported survives. Everything else stays
 * `null` via the shared `EMPTY_META`, because a zero cost or a zero token
 * count here would be a fabricated fact about a request that may well have
 * been billed. `EMPTY_META` is a frozen singleton, so it is spread, never
 * stamped.
 */
function metaFromError(err: nRouterError): ResponseMeta {
  return (
    err.meta ?? {
      ...EMPTY_META,
      requestId: err.requestId,
      limitSource: err.limitSource,
      authReason: err.authReason,
    }
  );
}

/** Read one property off a value that may be anything at all. */
function pluck(value: unknown, key: string): unknown {
  if (value === null || typeof value !== 'object') {
    return undefined;
  }
  return (value as Record<string, unknown>)[key];
}

/**
 * Render an unknown rejection as a message.
 *
 * Never `JSON.stringify` and never `String(obj)` on an arbitrary thrown value:
 * what threw is frequently a request or client object, and serializing one is
 * how an `Authorization: Bearer sk-nrouter-…` ends up in an error message, a
 * log line and eventually a bug report. The error constructor redacts what it
 * can, but not producing the string in the first place is the stronger guard
 * (Rule #5).
 */
function describe(reason: unknown): string {
  if (reason instanceof Error) {
    return reason.message;
  }
  if (typeof reason === 'string') {
    return reason;
  }
  return 'unknown failure';
}
