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

import { dataUrlToPart } from './multimodal';
import type {
  ChatContentPart,
  ChatMessage,
  NRouterCallOptions,
  NRouterExtraBody,
  NRouterFeatureOptions,
} from './types';

/**
 * Map the nRouter-specific options onto the four `extra_body_fields` the
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

  // OMITTED when absent OR empty, and the empty case is the one that matters.
  //
  // `[]` is not "no guardrails" — the gateway reads OMISSION as "apply every
  // org-enabled guardrail" and a present list as "run ONLY these". Sending an
  // empty list is therefore a different instruction from sending nothing, and
  // the likely-wrong one: it asks for zero guardrails on a request whose org
  // configured some. The playground guards this the same way
  // (`if (activeGuardrailIds.length > 0)`).
  //
  // A later refactor will want to collapse this to `if (opts.guardrailIds)`.
  // That refactor turns "no guardrail UI state yet" into "disable the org's
  // guardrails", which is a security regression with a green test suite.
  if (opts.guardrailIds && opts.guardrailIds.length > 0) {
    extra.nrouter_guardrail_ids = opts.guardrailIds;
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
  const parts: ChatContentPart[] =
    typeof message.content === 'string'
      ? message.content
        ? [{ type: 'text', text: message.content }]
        : []
      : // Copy rather than push into the caller's array — `buildMessages` must
        // never mutate the `messages` a caller may reuse for a second call.
        [...message.content];

  return { role: message.role, content: [...parts, ...imageParts(images)] };
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
    // Shallow-copy each turn: the images fold below replaces one of them, and a
    // caller reusing this array for a follow-up call must not see our edit.
    for (const message of opts.messages) {
      out.push({ role: message.role, content: message.content });
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
  const body: Record<string, unknown> = {
    model: opts.model,
    messages: buildMessages(opts),
  };

  if (opts.maxTokens !== undefined) {
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
    Object.assign(body, opts.extra);
  }

  return body;
}
