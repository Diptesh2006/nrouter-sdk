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
// `nrouter_guardrail_ids` WAS exactly that dead option, and it was removed
// rather than sent. Its replacements `nrouter_fallbacks` and
// `nrouter_guardrails` are the opposite case — fields the gateway really does
// read — and the note in `buildExtraBody` carries both measurements.

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
 * Published ceilings, from `extra_body_fields` in spec/nrouter-sdk-spec.json.
 * Not folklore: an SDK that invents its own limit either refuses a request the
 * gateway would have served, or learns the real one from a billed 400.
 */
const MAX_FALLBACKS = 4;
const MAX_GUARDRAILS = 8;

/**
 * Normalize one override list, or refuse it.
 *
 * An empty entry is REFUSED rather than trimmed away. Dropping one leaves the
 * caller with a SHORTER list than they wrote and nothing saying so: for
 * guardrails that is a safety control the request was never inspected by, and
 * for fallbacks it is a chain shorter than the one they reasoned about.
 */
function overrideNames(value: readonly string[], option: string, ceiling: number): string[] {
  const out: string[] = [];
  for (const entry of value) {
    if (typeof entry !== 'string' || entry.trim() === '') {
      throw configurationError(
        `${option} contains an empty entry. Every entry must be a non-empty name; ` +
          'an entry silently dropped here is a shorter list than you wrote, with ' +
          'nothing saying so.',
      );
    }
    out.push(entry.trim());
  }
  if (out.length > ceiling) {
    throw configurationError(
      `${option} carries ${out.length} entries; the gateway accepts at most ${ceiling}. ` +
        'Sent as-is the whole request is refused with a 400 before any provider call.',
    );
  }
  return out;
}

/**
 * Map the nRouter-specific options onto the `extra_body_fields` the gateway
 * reads. Anything absent is OMITTED rather than sent as a null or an
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

  // The per-request overrides the gateway added on 2026-09-17.
  //
  // Their predecessor `guardrailIds` was REFUSED here for two releases, and
  // that refusal was correct for as long as it stood. MEASURED 2026-08-28
  // against nrouter-rust-gateway: `grep -rn nrouter_guardrail_ids` over the
  // WHOLE repo returned ZERO hits against 608 `guardrail` references; the
  // gateway's OpenAPI advertised only the three older extra_body fields; and
  // every provider transformation strips what it knows
  // (`object.remove("nrouter_cache")` in all six) while NONE stripped that one,
  // so it was serialized straight through to OpenAI or Anthropic, which
  // rejected the call as an unrecognized argument.
  //
  // What changed is the gateway, not the judgement. It now READS both fields,
  // so the same reasoning that produced the refusal now forbids it: a caller
  // who cannot reach a shipped safety control from npm, while our own hosted
  // surfaces can, has the fake-success problem from the other side.
  //
  // The CEILINGS are enforced here, before egress, for the reason the old
  // refusal was loud: the gateway's 400 names the wire field
  // (`fallback_not_allowed`), costs a round trip, and does not name the option
  // the caller set. CONFIGURATION kind, which is permanent and never retried,
  // so a caller's `if (isRetryable(e)) retry` loop cannot spin on it.
  //
  // An EMPTY array is omitted rather than sent, and that is scoped
  // deliberately: `[]` expresses no selection, so nothing the caller asked for
  // goes unserved — the org's own fallback policy and guardrails apply exactly
  // as before — and refusing it would break `guardrails: state.selected` with
  // an empty default on a request that is, and stays, correct.
  // The RENAME still has to be refused, and for the SAME reason the option
  // itself now exists.
  //
  // Deleting the old `guardrailIds` branch left the name unmodelled rather than
  // rejected, and TypeScript types are ERASED: a plain-JS caller — or a TS
  // caller spreading a widened options object, which is the shape excess-
  // property checking does not see — upgrading from the previous release keeps
  // `guardrailIds: [...]` and gets no error and no guardrails. That is the
  // fake-success this whole file is written against, arriving on the safety
  // option. Python refuses it (unknown kwarg -> TypeError) and Go refuses it
  // (removed struct field -> compile error); JS is the only surface that can
  // swallow it, so the guard belongs here.
  //
  // NON-EMPTY only, the same scoping the old refusal had: `[]` selects nothing,
  // so a caller passing an empty default has asked for nothing and lost nothing.
  const retiredGuardrailIds = (opts as { guardrailIds?: readonly string[] }).guardrailIds;
  if (Array.isArray(retiredGuardrailIds) && retiredGuardrailIds.length > 0) {
    throw configurationError(
      'guardrailIds was renamed to `guardrails` and is no longer read by this SDK. ' +
        'Rename the option: `guardrails` maps onto the gateway field ' +
        '`nrouter_guardrails` (up to 8 org-owned ids or names, ADD-ONLY on top of ' +
        'the guardrails your key, team or org already assigns). This is refused ' +
        'rather than ignored because a dropped guardrail list is a request you ' +
        'believe was inspected and was not.',
    );
  }

  if (opts.fallbacks && opts.fallbacks.length > 0) {
    extra.nrouter_fallbacks = overrideNames(opts.fallbacks, 'fallbacks', MAX_FALLBACKS);
  }

  if (opts.guardrails && opts.guardrails.length > 0) {
    extra.nrouter_guardrails = overrideNames(opts.guardrails, 'guardrails', MAX_GUARDRAILS);
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
    if (key === '__proto__' || key === 'prototype' || key === 'constructor') {
      throw configurationError(
        `extra must not carry a "${key}" key: it can pollute object prototypes or tamper with instantiation. Remove it.`,
      );
    }
  }
}


/**
 * Map the typed tool and structured-output options onto their wire fields.
 *
 * The translation to Anthropic already existed (`toolsToAnthropic` /
 * `toolChoiceToAnthropic` in chat.ts); the only thing missing was a typed way
 * to GET here without `extra`. Everything below is a refusal rather than a
 * silent repair, for this file's standing reason: a request the caller believes
 * carries tools and does not comes back as a normal-looking answer they paid
 * for.
 */
function buildToolFields(opts: NRouterCallOptions): Record<string, unknown> {
  const out: Record<string, unknown> = {};

  if (opts.tools !== undefined) {
    // `tools: []` is what an uninitialised caller state produces. Some
    // providers reject a zero-length list outright and the rest answer as if
    // no tools were offered — a fake success, so refuse it here where the
    // sentence can name the option.
    if (!Array.isArray(opts.tools) || opts.tools.length === 0) {
      throw configurationError(
        'tools must be a non-empty array when supplied. An empty tool list is ' +
          'rejected by some providers and silently ignored by the rest, so the ' +
          'model answers as though no tool existed — omit `tools` instead.',
      );
    }
    const names = new Set<string>();
    for (const tool of opts.tools) {
      const name = tool?.function?.name;
      if (typeof name !== 'string' || name.trim() === '') {
        throw configurationError(
          'every entry in `tools` needs a non-empty `function.name`: the name is ' +
            'the only thing binding a returned tool_call back to your handler.',
        );
      }
      if (names.has(name)) {
        // A duplicate name makes the returned `tool_calls[].function.name`
        // ambiguous, so the caller's dispatch picks one handler arbitrarily.
        throw configurationError(`tools contains two functions named "${name}"; names must be unique.`);
      }
      names.add(name);
    }
    out.tools = opts.tools;
  }

  if (opts.toolChoice !== undefined) {
    if (opts.tools === undefined) {
      throw configurationError(
        'toolChoice was set without `tools`. Naming a function the request does ' +
          'not carry is rejected by every provider.',
      );
    }
    if (
      typeof opts.toolChoice === 'object' &&
      opts.toolChoice !== null &&
      !names_include(opts.tools, opts.toolChoice.function?.name)
    ) {
      throw configurationError(
        `toolChoice names "${String(opts.toolChoice.function?.name)}", which is not in \`tools\`.`,
      );
    }
    out.tool_choice = opts.toolChoice;
  }

  if (opts.jsonSchema !== undefined) {
    const spec = opts.jsonSchema;
    if (!spec || typeof spec.name !== 'string' || spec.name.trim() === '') {
      throw configurationError('jsonSchema needs a non-empty `name`.');
    }
    if (!spec.schema || typeof spec.schema !== 'object' || Array.isArray(spec.schema)) {
      throw configurationError('jsonSchema.schema must be a JSON Schema object.');
    }
    const jsonSchema: Record<string, unknown> = {
      name: spec.name,
      // `strict` defaults ON. Asking for a schema and not getting decoding
      // enforcement is the half-measure that makes `parsed<T>()` fail at the
      // caller instead of at the provider.
      strict: spec.strict ?? true,
      schema: spec.schema,
    };
    if (spec.description !== undefined) jsonSchema.description = spec.description;
    out.response_format = { type: 'json_schema', json_schema: jsonSchema };
  }

  return out;
}

function names_include(tools: NRouterCallOptions['tools'], name: unknown): boolean {
  if (!Array.isArray(tools)) return false;
  return tools.some((tool) => tool?.function?.name === name);
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
 *  - `images` fold into the FINAL turn when it is the user's — which is where
 *    the playground puts them, because a playground conversation always ends on
 *    the user turn. When the conversation ends on an assistant or tool turn (an
 *    agent loop), they become a new trailing user turn instead: PGSDK-111, and
 *    the reasoning is at the fold site below.
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

  // PGSDK-111 — attach to the FINAL turn, and only when that turn is the user's.
  //
  // This used to walk BACKWARDS for the last `role === 'user'`. That is the same
  // answer in a user/assistant conversation, where the final turn IS the user's,
  // and it is wrong the moment tool turns interleave: in an agent loop the newest
  // turn is a tool RESULT and the last user turn is several turns behind it, so
  // the image was folded into a question the model had already answered and
  // arrived BEFORE the tool output it was meant to follow. The request succeeds,
  // the model answers about the wrong turn, and it reads as a model failure.
  //
  // The two rejected alternatives, and why:
  //   * fold into the last NON-ASSISTANT turn — that is the tool result, and
  //     image content-parts on a `tool` message is not a shape providers accept;
  //   * refuse images when the final turn is a tool result — a throw where the
  //     caller's intent ("this image goes with what just happened") is
  //     unambiguous and expressible.
  //
  // A trailing turn that is not the user's therefore gets a NEW user turn, which
  // is the same thing the no-user-turn case already did and for the same reason:
  // never drop an attachment silently.
  const last = out.length - 1;
  if (last >= 0 && out[last].role === 'user') {
    out[last] = withImages(out[last], images);
    return out;
  }

  // Nothing to fold into — only a `systemPrompt`, or the conversation ends on an
  // assistant or tool turn. Carry the images in their own user turn rather than
  // dropping them: a dropped attachment is invisible until the model answers as
  // if it never saw the image.
  out.push({ role: 'user', content: imageParts(images) });
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

  Object.assign(body, buildToolFields(opts));

  Object.assign(body, buildExtraBody(opts));

  if (opts.extra) {
    vetExtra(opts.extra);
    Object.assign(body, opts.extra);
  }

  return body;
}
