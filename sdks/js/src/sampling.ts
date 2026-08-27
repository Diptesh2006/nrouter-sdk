// ---------------------------------------------------------------------------
// Sampling-parameter policy — PORTED from the hosted playground's single source
// of truth (`nrouter-app/src/lib/playground/sampling-params.ts`), which the
// playground send path, the compare stream and the copy-a-snippet generators
// all share. The npm SDK must produce the SAME request body the playground
// would, or a snippet copied out of the dashboard behaves differently once it
// runs against the SDK.
//
// This is a policy, not a convenience wrapper. Each rule below prevents a
// specific, observed failure:
//
//   1. DEFAULT MODE SENDS NOTHING. Every provider ships its own tuned defaults
//      for temperature and top_p, and they are not the same number. Filling in
//      a "sensible" 0.7 silently overrides all of them, so the same prompt
//      answers differently through us than it does direct — with no user
//      action to explain it.
//
//   2. CLAUDE IS temperature XOR top_p. Anthropic's newer Claude models REJECT
//      a request carrying both, with a 400 reading "Please use only one" that
//      the caller cannot act on because they never set both explicitly. For
//      Claude, a non-neutral top_p WINS and temperature is dropped.
//
//   3. top_p === 1 IS NEVER SENT. 1 is the neutral/no-op value everywhere, so
//      sending it changes no output — but on Claude it is enough to trigger
//      rule 2's 400. Zero behavioural gain, real failure risk.
//
//   4. CLAUDE IS MATCHED BY FAMILY, NOT HOST CLOUD. The same weights are served
//      by Anthropic direct, by Bedrock (`us.anthropic.claude-sonnet-4-6-v1:0`)
//      and by Vertex. All of them enforce the XOR. Keying off a provider
//      allowlist of "anthropic" would let every Bedrock/Vertex Claude request
//      through into the 400.
// ---------------------------------------------------------------------------

/**
 * Inputs to the sampling policy.
 *
 * `temperature` and `topP` are OPTIONAL here, unlike the app version — the
 * playground reads them from a store that always holds a number, whereas an
 * SDK caller may legitimately set one, the other, or neither. Absent means
 * "the caller did not choose a value", and the policy NEVER substitutes one:
 * an omitted param falls back to the provider's own default, which is exactly
 * what rule 1 above is protecting.
 */
export interface SamplingInput {
  /** Advanced sampling explicitly enabled by the caller. When false, NOTHING is sent. */
  advanced: boolean;
  /** The model id or public alias being called (e.g. `claude-haiku-4-5-20251001`). */
  model: string;
  /** Optional provider attribution, when the caller knows it (e.g. from model_info). */
  provider?: string | null;
  /** Caller-chosen temperature. Absent = not chosen; never defaulted to a number. */
  temperature?: number;
  /** Caller-chosen top_p. Absent (or 1, the neutral value) = never sent. */
  topP?: number;
}

/** The wire-shaped subset of the request body this policy owns. */
export interface SamplingParams {
  temperature?: number;
  top_p?: number;
}

/**
 * The neutral top_p. Sending it changes no output on any provider, and on
 * Claude it is enough to trigger the temperature/top_p conflict — so it is
 * treated as "unset" rather than as a value the caller chose.
 */
const NEUTRAL_TOP_P = 1;

/**
 * True when the model is from the Claude family, and therefore enforces
 * temperature XOR top_p.
 *
 * Matched by FAMILY, not by host cloud: Bedrock ids (`us.anthropic.claude-…`)
 * and Vertex ids both contain "claude", so a substring match on the model id
 * covers every cloud serving these weights. The `provider` arm is a fallback
 * for the case where the model is a private alias that hides the family name
 * but the provider attribution still says Anthropic.
 */
export function isClaudeModel(model: string, provider?: string | null): boolean {
  return /claude/i.test(model) || /anthropic/i.test(provider ?? '');
}

/**
 * Build the sampling subset of a request body.
 *
 * Truth table (advanced × claude × top_p non-neutral × temperature present):
 *
 *   advanced=false  → {}                       // any model — provider defaults win
 *
 *   advanced=true, claude=true:
 *     top_p non-neutral            → { top_p }                 // top_p WINS; temperature DROPPED
 *     top_p neutral/absent, temp   → { temperature }
 *     top_p neutral/absent, no temp→ {}
 *
 *   advanced=true, claude=false:
 *     top_p non-neutral, temp      → { temperature, top_p }
 *     top_p non-neutral, no temp   → { top_p }
 *     top_p neutral/absent, temp   → { temperature }
 *     top_p neutral/absent, no temp→ {}
 *
 * Note the Claude row: dropping temperature is DELIBERATE and is the whole
 * point of the policy. It is better to honour the more specific of the two
 * knobs than to emit a request the provider refuses.
 *
 * Note the empty results under advanced=true: with neither knob chosen there
 * is nothing to send, and inventing a number here would reintroduce rule 1's
 * silent override.
 */
export function buildSamplingParams(input: SamplingInput): SamplingParams {
  // Rule 1: default mode is a hard "send nothing", checked before anything else.
  if (!input.advanced) return {};

  const { temperature, topP } = input;

  // Rule 3: neutral or absent top_p is not a value the caller chose. The
  // `!== undefined` half is what narrows `topP` to `number` below.
  const topPSet = topP !== undefined && topP !== NEUTRAL_TOP_P;

  // Rule 2: on Claude an explicit top_p wins and temperature is suppressed,
  // because sending both is a 400 the caller cannot diagnose.
  const suppressTemperature = topPSet && isClaudeModel(input.model, input.provider);

  const params: SamplingParams = {};
  if (temperature !== undefined && !suppressTemperature) params.temperature = temperature;
  if (topPSet) params.top_p = topP;
  return params;
}
