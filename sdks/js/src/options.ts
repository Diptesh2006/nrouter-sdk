// The translator between the SDK's ergonomic options and the OpenAI-shaped
// request body the gateway actually reads.
//
// It exists so that exactly one place in this SDK knows the wire shape. Every
// rule below is a behaviour the hosted playground already relies on
// (nrouter-app `src/app/[organization]/playground/page.tsx`, the `nrouterOverrides`
// block and `buildPlaygroundHistory`); a divergence here would mean an option a
// user can toggle in our own UI silently does nothing from npm.
//
// The nRouter field set is CLOSED — `extra_body_fields` in
// spec/nrouter-sdk-spec.json (Rule #14). The gateway strips the fields it knows
// and forwards the rest to the provider, so a field this SDK invents is not an
// error a caller ever sees: it is a dead option that looks live.
//
// `nrouter_guardrail_ids` WAS exactly that dead option, and it is now refused
// rather than sent. See the refusal in `buildExtraBody` for the measurement.

import { configurationError } from './errors';
import { dataUrlToPart } from './multimodal';
import type {
  ChatContentPart,
  ChatMessage,
  NRouterCallOptions,
  NRouterExtraBody,
  NRouterFeatureOptions,
} from './types';

/**
 * Map the nRouter-specific options onto the three `extra_body_fields` the
 * gateway reads. Anything absent is OMITTED rather than sent as a null or an
 * empty value — omission and emptiness mean different things on this wire.
 *
 * TENANCY IS NEVER IN HERE. No `organization_id`, `team_id`, `org_id` or
 * `user_id` is ever written into a request body by this SDK. The gateway
 * resolves the tenant from the authenticated virtual key alone (Rule #8;
 * gateway rules §4f gate 5) — a body-supplied tenancy field is the
 * spend-attribution spoof that gate exists to stop.
 */
export function buildExtraBody(opts: NRouterFeatureOptions): NRouterExtraBody {
  const extra: NRouterExtraBody = {};

  if (opts.promptTemplateId) {
    extra.nrouter_prompt_template_id = opts.promptTemplateId;
  }

  // `promptVariables` WITHOUT `promptTemplateId` is passed through, deliberately.
  //
  // The playground drops it (it only fills `nrouter_prompt_variables` inside the
  // `if (selectedTemplateId)` branch), but that is a property of its UI, not of
  // the wire: the template picker is the only way it can produce variables at
  // all. The gateway disagrees. `prompt_runtime.rs` takes both fields off the
  // body independently, and when no template id was sent it resolves the
  // key/team/org prompt ASSIGNMENT instead, then renders it with
  // `variables.extend(caller_variables)` — the caller's variables apply in both
  // branches. So variables alone are meaningful, and dropping them here would
  // break the org-assigned-template case, which is the common one in production.
  //
  // Nothing is thrown for the same reason: when no template and no assignment
  // resolve, the gateway has already removed both fields and returns normally.
  // A caller mistake here costs nothing on the wire; inventing a client-side
  // validation the gateway does not have would refuse requests that work.
  if (opts.promptVariables && Object.keys(opts.promptVariables).length > 0) {
    extra.nrouter_prompt_variables = opts.promptVariables;
  }

  // REFUSED, and this used to send `nrouter_guardrail_ids`. It was a FAKE
  // SURFACE — an option our own docs advertised that nothing on the serving
  // path has ever read.
  //
  // MEASURED 2026-08-28 against nrouter-rust-gateway:
  //   * `grep -rn nrouter_guardrail_ids` over the WHOLE repo returns ZERO
  //     hits, against 608 `guardrail` references. Guardrail selection there is
  //     resolved per org/key/team from config, with no per-request override.
  //   * the gateway's own OpenAPI advertises only the other three extra_body
  //     fields (`src/http/openapi.rs`, the `nrouter_cache` /
  //     `nrouter_prompt_template_id` / `nrouter_prompt_variables` triple).
  //   * every provider transformation explicitly strips what it knows
  //     (`object.remove("nrouter_cache")` in all six), and NONE strips this
  //     one — so the field was serialized straight through to OpenAI or
  //     Anthropic, which rejected the call as an unrecognized argument. The
  //     caller paid a round trip to learn nothing that named the cause.
  //
  // THROWING rather than dropping, deliberately, and this is the whole point.
  // nrouter-app already faced the same choice for the playground and refuses
  // with 400 GATEWAY_FEATURE_UNSUPPORTED, because "the user picked a safety
  // control and would get a normal-looking answer without it" is a fake
  // success and a security regression. Quietly deleting the option here would
  // ship precisely that: this is a PUBLISHED package, and TypeScript's
  // excess-property check only fires on a fresh object literal, so a plain-JS
  // caller — or a TS caller spreading a widened options object — would see no
  // error at all. This SDK must not be the laxer surface than our own BFF.
  //
  // CONFIGURATION kind, which is permanent and never retried: a caller's
  // generic `if (isRetryable(e)) retry` loop must not spin on a condition no
  // retry improves.
  //
  // Scoped to a NON-EMPTY list on purpose. `[]` expresses no selection, so
  // nothing the caller asked for goes unserved and the org's guardrails apply
  // exactly as before; refusing it would break `guardrailIds: state.selected`
  // with an empty default on a request that is, and stays, correct.
  if (opts.guardrailIds && opts.guardrailIds.length > 0) {
    throw configurationError(
      'guardrailIds is not supported: the gateway runs no per-request ' +
        'guardrail override, so this option was never applied to a request. ' +
        'Guardrails are assigned per key, team or organization in the nRouter ' +
        'dashboard and already apply automatically to every call — remove ' +
        '`guardrailIds` to use them. Sent as-is it reached the provider as an ' +
        'unrecognized argument and the request failed there.',
    );
  }

  // `nrouter_cache` is sent ONLY to turn caching off. `true` is the gateway
  // default (spec: `"default": true`), so transmitting it changes nothing and
  // just adds a field to every body — the playground omits it for that reason
  // (`if (!cacheEnabled)`). Note the strict `=== false`: `undefined` must not
  // fall into this branch.
  if (opts.cache === false) {
    extra.nrouter_cache = false;
  }

  return extra;
}

/**
 * Keys that would place a tenancy identifier in a request body.
 *
 * Gateway rules §4f GATE 5: tenancy is resolved from the authenticated caller
 * ALONE — never a header, body or query param — because a body-supplied org or
 * team id is the spend-attribution spoof, one tenant's usage billed to another.
 *
 * This set MIRRORS the one in `src/memory.ts`, whose comment already claimed
 * "test/options.test.ts already pins this for the body builders". It did not:
 * memory refused `{ role, content, organization_id }` while `opts.extra` walked
 * the same identifier straight onto the wire. The stricter gate was on the
 * quieter path. The two sets must stay in step.
 *
 * Compared NORMALIZED (lowercased, underscores dropped), so `organization_id`,
 * `organizationId` and `ORGANIZATION_ID` are one entry.
 */
const TENANCY_KEYS = new Set(['organizationid', 'orgid', 'teamid', 'userid', 'nrouterorg']);

const normalizeKey = (key: string): string => key.toLowerCase().replace(/_/g, '');

/**
 * Vet the caller's escape hatch before it is merged into the body.
 *
 * `extra` exists so a gateway or provider field this SDK does not model yet is
 * never a blocker, and that stays true — this refuses exactly two shapes, both
 * of which are broken rather than unmodelled:
 *
 *   * a TENANCY key. It is ignored by the gateway (gate 5) and then forwarded
 *     verbatim to the provider, which rejects it as an unrecognized argument.
 *     REFUSED rather than stripped, for the reason memory.ts already gives:
 *     stripping leaves the caller believing they attributed spend somewhere,
 *     and that belief is wrong forever and silently.
 *
 *   * `__proto__`. `Object.assign` invokes the setter rather than defining a
 *     property, so a JSON-parsed hatch carrying it never reaches the wire AND
 *     replaces the body object's prototype. Measured 2026-08-28:
 *     `extra: JSON.parse('{"__proto__":{"stream":true}}')` makes `chat()` throw
 *     "remove `stream: true` from `extra`" at a caller who never set stream,
 *     while the field they did set vanishes.
 */
function vetExtra(extra: Record<string, unknown>): void {
  for (const key of Object.keys(extra)) {
    if (TENANCY_KEYS.has(normalizeKey(key))) {
      throw configurationError(
        `extra must not carry the tenancy field "${key}". The gateway resolves the ` +
          'organization, team and user from the authenticated API key alone; a ' +
          'body-supplied identifier attributes no spend, and reaches the provider as ' +
          'an unrecognized argument that fails the request.',
      );
    }
    if (key === '__proto__') {
      throw configurationError(
        'extra must not carry a "__proto__" key: it is never serialized onto the wire ' +
          "and instead replaces the request body's prototype, which makes unrelated " +
          'fields appear to be set. Remove it.',
      );
    }
  }
}

export function buildFeatureBody(
  body: Record<string, unknown>,
  opts: NRouterFeatureOptions = {},
): Record<string, unknown> {
  return {
    ...body,
    ...buildExtraBody(opts),
  };
}

/** Build the image content-parts for one turn, in the playground's order. */
function imageParts(images: readonly string[]): ChatContentPart[] {
  // VALIDATED, through the same function the media surface uses.
  //
  // The comment here used to say a client-side check "would only be able to be
  // wrong", and that was true of a URL REACHABILITY check — it is not true of
  // the shape. `dataUrlToPart` already refuses a bare path, an http:// URL,
  // an impossible base64 length and a URL that does not parse, and every one
  // of those fails at the provider AFTER the request is billed. Leaving this
  // path unvalidated meant the SDK's own documented image contract was
  // enforced on `nr.media.*` and quietly ignored on the far more common
  // `nr.chat({ images })`.
  return images.map((url) => dataUrlToPart(url));
}

/**
 * Fold images into one turn, converting a string body to a parts array.
 *
 * The empty-text case is deliberate: the playground pushes the text part only
 * `if (input)`, so an image-only turn carries image parts and no text part.
 * Several providers reject a zero-length text block outright, and an empty
 * string is not something the caller asked to send.
 */
function withImages(message: ChatMessage, images: readonly string[]): ChatMessage {
  const content: unknown = message.content;
  const parts: ChatContentPart[] = Array.isArray(content)
    ? // Copy rather than push into the caller's array — `buildMessages` must
      // never mutate the `messages` a caller may reuse for a second call.
      [...(content as ChatContentPart[])]
    : typeof content === 'string' && content
      ? [{ type: 'text', text: content }]
      : // `null` is what OpenAI puts on an assistant turn that only made tool
        // calls, and spreading it threw a TypeError naming nothing useful.
        [];

  // SPREAD the turn rather than rebuilding it from two fields: `tool_calls`,
  // `tool_call_id` and `name` live alongside `role` and `content`, and a turn
  // rebuilt from a two-property literal drops them silently.
  return { ...message, content: [...parts, ...imageParts(images)] };
}

/**
 * Assemble the message list from the ergonomic options.
 *
 * Order and precedence match `buildPlaygroundHistory`:
 *  - a non-empty `systemPrompt` becomes the LEADING `system` turn (the
 *    playground's `if (systemPrompt)` — an empty string adds no turn, because
 *    an empty system message still costs tokens and can change behaviour);
 *  - explicit `messages` WIN over `prompt`, which is only a single-turn
 *    convenience;
 *  - `images` fold into the LAST user turn, exactly where the playground puts
 *    them, so a multi-turn conversation attaches them to what the user just
 *    said rather than to some earlier turn.
 *
 * The caller's `messages` array and its elements are never mutated.
 */
export function buildMessages(opts: NRouterCallOptions): ChatMessage[] {
  const out: ChatMessage[] = [];

  if (opts.systemPrompt) {
    out.push({ role: 'system', content: opts.systemPrompt });
  }

  if (opts.messages && opts.messages.length > 0) {
    // Shallow-copy each turn WHOLE. `{ role, content }` was the defect: it
    // rebuilt every turn from two properties and discarded the rest, so an
    // assistant turn lost its `tool_calls` and a tool result lost the
    // `tool_call_id` binding it to that call — the two fields this SDK's own
    // Anthropic translator reads (`chat.ts`, `role === 'tool'` and
    // `assistant && tool_calls`), which made that translator unreachable and
    // every replayed tool conversation a billed provider rejection.
    //
    // Still a COPY, for the original reason: the images fold below replaces one
    // of these entries and a caller reusing the array must not see our edit.
    for (const message of opts.messages) {
      out.push({ ...message });
    }
  } else if (opts.prompt !== undefined) {
    // An empty array of `messages` falls through to `prompt` on purpose: a
    // request carrying zero messages is a guaranteed provider 400, so treating
    // `[]` as "supplied" would turn a caller's uninitialised state into a
    // failed billed round trip.
    out.push({ role: 'user', content: opts.prompt });
  }

  const images = opts.images;
  if (!images || images.length === 0) return out;

  let lastUser = -1;
  for (let i = out.length - 1; i >= 0; i--) {
    if (out[i].role === 'user') {
      lastUser = i;
      break;
    }
  }

  if (lastUser === -1) {
    // No user turn to attach to (e.g. only a `systemPrompt` was given). Carry
    // the images in a new user turn rather than dropping them silently — a
    // dropped attachment is invisible until the model answers as if it never
    // saw the image, which reads as a model failure, not an SDK one.
    out.push({ role: 'user', content: imageParts(images) });
    return out;
  }

  out[lastUser] = withImages(out[lastUser], images);
  return out;
}

/**
 * Assemble the full OpenAI-shaped chat body.
 *
 * Merge order is fixed and load-bearing:
 *   1. `model`, `messages`
 *   2. `max_tokens` — only when the caller set it. Unlike the playground, which
 *      always sends `clampMaxTokens(maxTokens)` because its slider always has a
 *      value, an unset option here means "let the provider apply its default"
 *      rather than "cap at whatever number this SDK picked".
 *   3. the sampling params — passed in ALREADY RESOLVED by the sampling policy
 *      (the `advancedSampling` opt-in and the Anthropic temperature-XOR-top_p
 *      rule). They are not re-derived here; two implementations of that policy
 *      is how the SDK and the playground start rejecting different requests.
 *   4. the nRouter `extra_body` fields.
 *   5. `opts.extra` LAST, so a caller can always reach a gateway or provider
 *      field this SDK does not model yet — including overriding anything above
 *      it. That escape hatch is what stops a missing option from being a
 *      blocker until the next release.
 *
 * NOT here, and never: `stream` (the transport owns it), the API key (it is an
 * `Authorization` header, never a body field — the playground's `api_key` is an
 * nrouter-app proxy field that never reaches the gateway body), and any tenancy
 * identifier. Tenancy comes from the authenticated key alone (Rule #8, gateway
 * gate 5); this function adds no `organization_id`, `team_id` or `user_id`, and
 * one supplied through `opts.extra` is not authoritative to the gateway either.
 */
export function buildChatBody(
  opts: NRouterCallOptions,
  sampling: { temperature?: number; top_p?: number },
): Record<string, unknown> {
  const messages = buildMessages(opts);
  if (messages.length === 0) {
    // This file's own reasoning, applied to itself: "a request carrying zero
    // messages is a guaranteed provider 400". It was emitted anyway whenever
    // neither `prompt` nor `messages` was supplied — an uninitialised caller
    // state became an opaque upstream rejection instead of a sentence naming
    // the missing option.
    throw configurationError(
      'a chat request needs at least one message: set `prompt` for a single turn, ' +
        'or `messages` for a conversation. A body with an empty message list is ' +
        'rejected by every provider.',
    );
  }

  const body: Record<string, unknown> = {
    model: opts.model,
    messages,
  };

  if (opts.maxTokens !== undefined) {
    // REFUSED, never rounded or clamped. `max_tokens: NaN` serializes to JSON
    // `null` — a value the caller never chose, on the field that bounds what
    // the request costs — and `NaN` is exactly what `parseInt('')` returns from
    // an empty form field. A fraction or a zero is rejected by every provider,
    // so refusing locally is free and refusing upstream is not.
    if (!Number.isInteger(opts.maxTokens) || opts.maxTokens < 1) {
      throw configurationError(
        `maxTokens must be a whole number of at least 1, got ${String(opts.maxTokens)}. ` +
          'It is not rounded or clamped here: silently changing the token ceiling ' +
          'changes what the request costs.',
      );
    }
    body.max_tokens = opts.maxTokens;
  }

  // Spread only what the policy actually resolved. `temperature: undefined` is
  // not the same as an absent key once the body is serialised by a transport
  // that keeps undefined-valued properties, and sending `temperature` alongside
  // `top_p` is exactly the pair Anthropic rejects.
  if (sampling.temperature !== undefined) {
    body.temperature = sampling.temperature;
  }
  if (sampling.top_p !== undefined) {
    body.top_p = sampling.top_p;
  }

  Object.assign(body, buildExtraBody(opts));

  if (opts.extra) {
    vetExtra(opts.extra);
    Object.assign(body, opts.extra);
  }

  return body;
}
