// The shared contract every module in this SDK codes against.
//
// It exists so the transport, the metadata parser, the error mapper and the
// high-level helpers cannot drift apart: each imports the same shapes, and a
// change here is a compile error everywhere it matters rather than a runtime
// surprise at one call site.

// TYPE-ONLY, and the only import in this file. `AbortSignalLike` is declared in
// `multimodal.ts` (structural, because this package compiles with no DOM lib,
// so naming `AbortSignal` would make the SDK depend on the caller's ambient
// type environment). Re-declaring it here would give the SDK two cancellation
// types that happen to match today — exactly the drift this module exists to
// prevent. A `import type` is erased at compile time, so there is no cycle.
import type { AbortSignalLike } from './multimodal';

/**
 * Per-request metadata from the gateway's `x-nr-*` response headers.
 *
 * Every numeric field is `number | null`, deliberately. The gateway OMITS a
 * header rather than sending a placeholder, and the omission carries meaning:
 * `x-nr-request-cost` is absent when the model is unpriced — never `0` — so a
 * zero default would report a free request, which no enabled model is.
 */
export interface ResponseMeta {
  /** Present on every response; the join key for a spend row or a support ticket. */
  requestId: string | null;
  /**
   * Milliseconds the gateway measured from edge arrival to response headers.
   *
   * TIME TO HEADERS, not time to the last byte: on a streamed response the
   * headers are ready before the first token, so this is never a
   * total-generation figure. Null only when the header was absent or
   * unparseable — the edge stamps it on every response it produces.
   */
  latencyMs: number | null;
  /**
   * The gateway's OpenTelemetry trace id, or null when no valid trace exists.
   *
   * A caller may SEND `x-nr-trace-id` (and `x-nr-session-id`) to correlate its
   * own spans; the gateway overwrites the response value with its own, so this
   * is what to join on — never assume it echoes what you sent.
   */
  traceId: string | null;
  /** Exact settled cost in USD. `null` when unpriced. Never treat null as 0. */
  cost: number | null;
  /** `exact` or `unpriced`. */
  costStatus: string | null;
  /** The model that actually served the request, which is not always the alias asked for. */
  model: string | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  cacheReadTokens: number | null;
  cacheWriteTokens: number | null;
  /** Which limit measured a 429: key | plan | team | user | budget. Null means the gateway did not say — never guess. */
  limitSource: string | null;
  /** Set when this request crossed a soft budget you configured (it still served): `<scope> soft_budget <spend>/<ceiling>`, e.g. `org soft_budget 80.00/100.00`. */
  budgetWarning: string | null;
  /**
   * Posture of the PRE-CALL guardrail chain: `none` | `monitor` | `pass` |
   * `partial` | `blocked`. Match it exactly and case-sensitively.
   *
   * Null means the gateway made NO guardrail claim about this response (a
   * `/v1/models` call, an auth refusal that never reached preflight) — never
   * "no guardrail applied", which is the explicit `none`.
   *
   * It is published on every wire that runs a pre-call chain: the four text
   * wires, and `image()`, `speech()`, `transcribe()`, `translate()`,
   * `embeddings()` and the video create, `video()`. It is absent on the two
   * free video collection calls, `videoStatus()` and `videoContent()`, which
   * resolve no chain at all — absence there is the contract, not a gap.
   *
   * `partial` is the ordinary answer on `transcribe()` and `translate()`, not
   * an anomaly: alarm on it and you alarm on every speech-to-text call.
   *
   * Posture only, by design: the policy name, its id, the detector family, the
   * rule count and — for `partial` — which channel went uninspected are all
   * deliberately withheld. A rule count moves when a policy moves, so watching
   * it maps a tenant's controls without ever tripping one; naming the
   * uninspected channel hands an evader the smuggling route.
   */
  guardrails: string | null;
  /** The gateway's stable reason for refusing a virtual key on a 401. */
  authReason: string | null;
  /** `hit` or `miss`; null when the response cache did not participate. */
  responseCache: string | null;
  /** Whole seconds since a cached response was produced. Hits only. */
  responseCacheAge: number | null;
  /** Prompt compression outcome: applied | not_requested | off | skipped. */
  compression: string | null;
  /** Which chain entry answered: direct | fallback:<n>. Absent on cache hits and refusals. */
  routing: string | null;
  /** Provider calls made for this request (>= 1). Absent on cache hits and refusals. */
  attempts: number | null;
  /** Which balance paid for this request: allowance or credits. */
  fundingSource: string | null;
  /** Seconds until the tightest usage-allowance window resets. */
  allowanceReset: number | null;
}

/**
 * Every response header this SDK reads, exactly as the gateway spells them.
 * Exported as data so a caller can forward the same set through their own
 * logging or tracing layer without retyping it.
 */
export const HEADER_NAMES = [
  'x-nr-request-id',
  'x-nr-latency-ms',
  'x-nr-trace-id',
  'x-nr-request-cost',
  'x-nr-cost-status',
  'x-nr-model',
  'x-nr-input-tokens',
  'x-nr-output-tokens',
  'x-nr-total-tokens',
  'x-nr-cache-read-tokens',
  'x-nr-cache-write-tokens',
  'x-nr-limit-source',
  'x-nr-budget-warning',
  'x-nr-guardrails',
  'x-nr-auth-reason',
  'x-nr-response-cache',
  'x-nr-response-cache-age',
  'x-nr-compression',
  'x-nr-routing',
  'x-nr-attempts',
  'x-nr-funding-source',
  'x-nr-allowance-reset',
] as const;

export type HeaderName = (typeof HEADER_NAMES)[number];

/**
 * The nRouter-specific request fields, exactly as `extra_body_fields` in
 * spec/nrouter-sdk-spec.json names them. This list is closed: the gateway
 * ignores anything else, so an invented field is a silently dead option.
 *
 * `nrouter_guardrail_ids` was removed on 2026-08-28 because it was exactly that
 * silently dead option: `grep -rn nrouter_guardrail_ids` over the whole
 * nrouter-rust-gateway repo returned ZERO hits (against 608 `guardrail`
 * references), so the field was forwarded verbatim to the provider, which
 * rejected it.
 *
 * `nrouter_fallbacks` and `nrouter_guardrails` (2026-09-17) are NOT that field
 * coming back under new names. The gateway READS both, and each is a different
 * shape from the one that was removed:
 *
 *   * `nrouter_fallbacks` REPLACES the org's fallback policy for that one call.
 *     It is not merged with it, and the primary stays whatever `model` names.
 *   * `nrouter_guardrails` is ADD-ONLY. It cannot remove, relax or replace a
 *     guardrail the org assigned, nor the platform moderation floor — which is
 *     what keeps a per-request field out of the safety decision.
 */
export interface NRouterExtraBody {
  /** Override the org default prompt template (UUID). */
  nrouter_prompt_template_id?: string;
  /** Jinja2 variables for that template. */
  nrouter_prompt_variables?: Record<string, string>;
  /** Tenant-isolated response cache for buffered text. Default true; false forces provider egress. */
  nrouter_cache?: boolean;
  /**
   * Up to 4 model names tried in order when the primary cannot be served.
   * REPLACES the org fallback policy for this one call; `model` stays primary.
   */
  nrouter_fallbacks?: string[];
  /**
   * Up to 8 guardrail ids or names owned by this org. ADD-ONLY: they run in
   * addition to the guardrails already assigned and to the platform moderation
   * floor, and a request can never remove or relax one.
   */
  nrouter_guardrails?: string[];
}

/**
 * Everything the hosted playground can set on a request, in one place.
 *
 * The playground is the reference surface: an option a user can toggle there
 * and cannot express here is a feature that exists only inside our own UI.
 */
export interface NRouterFeatureOptions {
  /** Prompt template + its Jinja2 variables. */
  promptTemplateId?: string;
  promptVariables?: Record<string, string>;
  /**
   * Up to 4 model names tried in order when the primary cannot be served.
   *
   * REPLACES the organization's fallback policy for this one call — it is not
   * merged with it — and `model` stays the primary. A target this key cannot
   * route, and any Smart Router alias, `nrouter/auto`, allowance or
   * capacity-pool model, is refused with 400 `fallback_not_allowed`.
   *
   * An empty array is OMITTED, not sent: `fallbacks: state.selected` with an
   * empty default means no selection, not an empty chain.
   */
  fallbacks?: string[];
  /**
   * Up to 8 guardrail ids or names owned by this organization.
   *
   * ADD-ONLY. These run IN ADDITION to the guardrails already assigned to the
   * key, team or organization, and to the platform moderation floor; a request
   * can never remove, relax or replace one. An id or name the org does not own
   * is refused with 400 `guardrail_not_found` rather than ignored — a silently
   * dropped guardrail is a request the caller believes was inspected and was
   * not.
   *
   * Replaces the removed `guardrailIds`, which the gateway never read.
   */
  guardrails?: string[];
  /** Set false to force provider egress. Omitted when true; true is the gateway default. */
  cache?: boolean;
}

export interface NRouterCallOptions extends NRouterFeatureOptions {
  model: string;
  /** Convenience for a single-turn call; ignored when `messages` is supplied. */
  prompt?: string;
  messages?: ChatMessage[];
  systemPrompt?: string;
  maxTokens?: number;

  /**
   * Sampling is OPT-IN. With `advancedSampling` false (the default) neither
   * `temperature` nor `top_p` is sent and each provider applies its own
   * defaults — which is also what avoids Anthropic's temperature-XOR-top_p
   * rejection. See sampling.ts for the full policy.
   */
  advancedSampling?: boolean;
  temperature?: number;
  topP?: number;
  /** Provider attribution when known; only used to detect the Claude family. */
  modelProvider?: string | null;
  /** Canonical model id behind an alias, if applicable (e.g. for sampling deprecation checks). */
  canonicalModel?: string | null;

  /** Prompt template + its Jinja2 variables. */
  promptTemplateId?: string;
  promptVariables?: Record<string, string>;
  /**
   * Up to 4 model names tried in order when the primary cannot be served.
   *
   * REPLACES the organization's fallback policy for this one call — it is not
   * merged with it — and `model` stays the primary. A target this key cannot
   * route, and any Smart Router alias, `nrouter/auto`, allowance or
   * capacity-pool model, is refused with 400 `fallback_not_allowed`.
   *
   * An empty array is OMITTED, not sent: `fallbacks: state.selected` with an
   * empty default means no selection, not an empty chain.
   */
  fallbacks?: string[];
  /**
   * Up to 8 guardrail ids or names owned by this organization.
   *
   * ADD-ONLY. These run IN ADDITION to the guardrails already assigned to the
   * key, team or organization, and to the platform moderation floor; a request
   * can never remove, relax or replace one. An id or name the org does not own
   * is refused with 400 `guardrail_not_found` rather than ignored — a silently
   * dropped guardrail is a request the caller believes was inspected and was
   * not.
   *
   * Replaces the removed `guardrailIds`, which the gateway never read.
   */
  guardrails?: string[];
  /** Set false to force provider egress. Omitted when true — true is the gateway default. */
  cache?: boolean;

  /**
   * Cancel this call (PGSDK-106).
   *
   * The media helpers have accepted an `AbortSignalLike` since they were
   * written; `chat()` — the helper an agent loop actually calls in a loop — did
   * not, so the only way to stop a runaway turn was to swap the runner out.
   *
   * It is a money control as much as an ergonomic one: an abandoned agent turn
   * nobody can stop keeps calling providers and keeps reserving credit.
   *
   * The signal reaches the transport and NOTHING else — it is never written
   * into the request body. An abort surfaces as an `nRouterError` like every
   * other failure out of `chat()`, and `isRetryable` already declines an
   * aborted cause, so a cancelled request is not retried as a blip.
   */
  signal?: AbortSignalLike;

  /** Image attachments as data URLs or https URLs, folded into the user turn. */
  images?: string[];

  /**
   * Functions the model may call. Mapped to the OpenAI `tools` field and
   * translated to Anthropic's `tools` by `toAnthropicMessagesRequest`.
   *
   * FIRST-CLASS rather than something to push through `extra`: the translation
   * already existed on both wires, so the only thing missing was the type, and
   * without it every agent author reached through the untyped escape hatch and
   * got no checking on the one field a typo silently disarms.
   */
  tools?: ChatTool[];

  /** How the model chooses among `tools`. Requires a non-empty `tools`. */
  toolChoice?: ChatToolChoice;

  /**
   * Ask for a response conforming to a JSON Schema.
   *
   * Mapped to `response_format: { type: 'json_schema', json_schema: … }`. Pair
   * it with `parsed<T>()` — see `JsonSchemaSpec` for the wire on which this is
   * a request rather than a guarantee.
   */
  jsonSchema?: JsonSchemaSpec;

  /** Anything else goes through untouched to the OpenAI-shaped body. */
  extra?: Record<string, unknown>;
}

export type ChatRole = 'system' | 'user' | 'assistant' | 'tool' | 'developer';

/**
 * One tool call the model asked for, on the OpenAI wire.
 *
 * This used to be `unknown[]` on `ChatMessage`, which made the single most
 * important field in an agent conversation untyped at the public boundary:
 * `msg.tool_calls[0].function.name` did not compile, so every author either
 * cast to `any` or re-declared this shape by hand and drifted from the wire
 * silently.
 *
 * `arguments` is a STRING and stays one. The provider emits a JSON document,
 * not an object, and it is emitted incrementally when streaming — so a
 * partial call carries syntactically invalid JSON. Typing it as a parsed
 * object here would make every caller's `JSON.parse` look redundant and hide
 * the one failure mode that actually happens: a truncated or malformed
 * argument document from a model that ran out of output tokens.
 */
export interface ToolCall {
  id: string;
  type: 'function';
  function: { name: string; arguments: string };
}

/** A function the model may call, in the OpenAI `tools` shape. */
export interface ChatTool {
  type: 'function';
  function: {
    name: string;
    description?: string;
    /** A JSON Schema object describing the arguments. */
    parameters?: Record<string, unknown>;
    strict?: boolean;
  };
}

/**
 * How the model should choose among the supplied tools.
 *
 * `'none'` is expressible and meaningful — it offers the tools without
 * permitting a call this turn, which is how an author forces a final natural
 * language answer at the last step of a bounded loop.
 */
export type ChatToolChoice =
  | 'auto'
  | 'none'
  | 'required'
  | { type: 'function'; function: { name: string } };

/**
 * A JSON Schema the response must conform to (OpenAI `response_format`).
 *
 * ⚠️ NOT available on every wire, and the unavailability is a REFUSAL rather
 * than a drop. Anthropic's Messages wire has no JSON-mode switch, so
 * `response_format` is on this SDK's `OPENAI_ONLY_FIELDS` list (chat.ts) — and
 * `refuseUnservableOnMessagesWire` raises a configuration error before the
 * request leaves rather than sending it with the schema removed. Dropping it
 * returned free-form prose that read like a success and was billed like one;
 * refusing costs nothing. Pass `jsonSchema` to an OpenAI-wire model, or ask a
 * Claude model for JSON in the prompt and read the answer with `parsed<T>()`.
 *
 * `parsed<T>()` checks that the reply IS JSON, not that it matches this schema:
 * conformance is enforced by the provider, which is why `strict` defaults on.
 */
export interface JsonSchemaSpec {
  name: string;
  schema: Record<string, unknown>;
  description?: string;
  /** Defaults to `true` — the strict decoding mode, which is the point of asking. */
  strict?: boolean;
}

export interface ChatMessage {
  role: ChatRole;
  content?: string | ChatContentPart[] | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
  [key: string]: unknown;
}

export type ChatContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } };

/** A response body paired with the metadata the gateway reported for it. */
export interface NRouterResponse<T> {
  body: T;
  meta: ResponseMeta;
}
