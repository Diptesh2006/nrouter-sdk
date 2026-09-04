// The shared contract every module in this SDK codes against.
//
// It exists so the transport, the metadata parser, the error mapper and the
// high-level helpers cannot drift apart: each imports the same shapes, and a
// change here is a compile error everywhere it matters rather than a runtime
// surprise at one call site.

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
   * "no guardrail applied", which is the explicit `none`. Not published on the
   * image, audio or video routes.
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
}

/**
 * Every response header this SDK reads, exactly as the gateway spells them.
 * Exported as data so a caller can forward the same set through their own
 * logging or tracing layer without retyping it.
 */
export const HEADER_NAMES = [
  'x-nr-request-id',
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
] as const;

export type HeaderName = (typeof HEADER_NAMES)[number];

/**
 * The nRouter-specific request fields, exactly as `extra_body_fields` in
 * spec/nrouter-sdk-spec.json names them. This list is closed: the gateway
 * ignores anything else, so an invented field is a silently dead option.
 *
 * It was FOUR fields until 2026-08-28. `nrouter_guardrail_ids` was removed
 * because it was that silently dead option: `grep -rn nrouter_guardrail_ids`
 * over the whole nrouter-rust-gateway repo returns ZERO hits (against 608
 * `guardrail` references), and the gateway's OpenAPI advertises only the three
 * below. Guardrail selection is resolved per org/key/team from config, with no
 * per-request override — so the field was forwarded verbatim to the provider,
 * which rejected it. `guardrailIds` now throws in `buildExtraBody` rather than
 * producing a body field nothing reads.
 */
export interface NRouterExtraBody {
  /** Override the org default prompt template (UUID). */
  nrouter_prompt_template_id?: string;
  /** Jinja2 variables for that template. */
  nrouter_prompt_variables?: Record<string, string>;
  /** Tenant-isolated response cache for buffered text. Default true; false forces provider egress. */
  nrouter_cache?: boolean;
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
   * @deprecated NOT SUPPORTED — a non-empty value THROWS a configuration error.
   *
   * The gateway runs no per-request guardrail override (measured 2026-08-28:
   * zero references in nrouter-rust-gateway), so this never scoped anything;
   * it was forwarded to the provider and rejected there. Guardrails are
   * assigned per key, team or organization in the nRouter dashboard and apply
   * automatically. Kept as a REFUSAL rather than deleted: this is a published
   * package, and a type-only removal is silent to plain-JS callers and to any
   * TS caller spreading a widened options object.
   */
  guardrailIds?: string[];
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

  /** Prompt template + its Jinja2 variables. */
  promptTemplateId?: string;
  promptVariables?: Record<string, string>;
  /**
   * @deprecated NOT SUPPORTED — a non-empty value THROWS a configuration error.
   *
   * The gateway runs no per-request guardrail override (measured 2026-08-28:
   * zero references in nrouter-rust-gateway), so this never scoped anything;
   * it was forwarded to the provider and rejected there. Guardrails are
   * assigned per key, team or organization in the nRouter dashboard and apply
   * automatically. Kept as a REFUSAL rather than deleted: this is a published
   * package, and a type-only removal is silent to plain-JS callers and to any
   * TS caller spreading a widened options object.
   */
  guardrailIds?: string[];
  /** Set false to force provider egress. Omitted when true — true is the gateway default. */
  cache?: boolean;

  /** Image attachments as data URLs or https URLs, folded into the user turn. */
  images?: string[];

  /** Anything else goes through untouched to the OpenAI-shaped body. */
  extra?: Record<string, unknown>;
}

export type ChatRole = 'system' | 'user' | 'assistant';

export interface ChatMessage {
  role: ChatRole;
  content: string | ChatContentPart[];
}

export type ChatContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } };

/** A response body paired with the metadata the gateway reported for it. */
export interface NRouterResponse<T> {
  body: T;
  meta: ResponseMeta;
}
