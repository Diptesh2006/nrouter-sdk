// nRouter client: the OpenAI wire format, plus everything the hosted
// playground can do.
//
// The class still EXTENDS the vendor OpenAI client, so every call you already
// write keeps working unchanged. What it adds is the `nr` namespace: the
// options a user can toggle in the playground — prompt templates, guardrail
// selection, the response cache, the Claude-safe sampling policy, image
// attachments — plus the `x-nr-*` metadata the vendor client discards.

import OpenAI from 'openai';

import { chat as runChat, chatText, compare as runCompare, type ChatRunner } from './chat';
import { configurationError, isAbortLike, redactKeys, transportError } from './errors';
import { metaFromHeaders, type HeaderSource } from './meta';
import { NRouterModels, type RawRequester } from './models';
import { Multimodal, type Transport, type TransportRequest, type TransportResponse } from './multimodal';
import { buildFeatureBody } from './options';
import { jsonRequest } from './json';
import { streamChat, type StreamRunner, type StreamResult } from './stream';
import type { NRouterCallOptions, NRouterFeatureOptions, NRouterResponse, ResponseMeta } from './types';

/** The gateway's customer surface. A dynamic value: override it for stage. */
export const DEFAULT_BASE_URL = 'https://api.nrouter.ai/v1';
/** The one environment variable this SDK reads. */
export const ENV_KEY = 'NROUTER_API_KEY';
/** Every customer key carries this prefix. */
export const KEY_PREFIX = 'sk-nrouter-';

/**
 * Resolve and validate a key: the explicit argument first, then the
 * environment.
 *
 * Validation happens before any request, so a malformed key fails locally
 * rather than as a 401 that looks like a revoked credential.
 */
/**
 * `process.env`, or nothing.
 *
 * This SDK supports the browser via `dangerouslyAllowBrowser`, and browsers,
 * workers and Deno have no `process` — an unguarded `process.env[...]` throws
 * a ReferenceError at construction, before the caller's explicit key is ever
 * looked at. openai 7 guards its own environment reads for the same reason.
 */
function envValue(name: string): string | undefined {
  return (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.[
    name
  ];
}

/**
 * Validate a key WITHOUT the environment fallback.
 *
 * The fallback belongs to construction only. On a ROTATION it is a tenancy
 * hazard: `client.apiKey = ''` or `null` would resolve to `NROUTER_API_KEY`
 * and silently move the client to a different tenant's key, billing them,
 * instead of rejecting an assignment that is plainly a mistake.
 */
function assertNRouterKey(value: unknown): string {
  if (typeof value !== 'string' || value === '') {
    throw configurationError(
      'apiKey must be a non-empty string. Clearing it is not supported: build a ' +
        'new client instead of leaving one in a state with no credential.',
    );
  }
  if (!value.startsWith(KEY_PREFIX)) {
    throw configurationError(
      `nRouter API keys must start with ${KEY_PREFIX}; got one that does not.`,
    );
  }
  return value;
}

function resolveApiKey(apiKey?: unknown): string {
  // `unknown`, not `string`, because openai 7 widened its own `apiKey` option
  // to `string | ApiKeySetter | null | undefined` and NRouterOptions inherits
  // that shape. REFUSE the setter form rather than passing it through: this
  // function's whole job is the `sk-nrouter-` prefix check below, and a
  // function is unverifiable until the request is already in flight — so
  // accepting one would forward an arbitrary credential to the gateway with
  // the guard silently skipped.
  if (apiKey != null && typeof apiKey !== 'string') {
    throw configurationError(
      'apiKey must be a string. The openai client also accepts a function that ' +
        'returns a key, but this SDK validates the nRouter key prefix up front ' +
        'and cannot check a value that does not exist yet.',
    );
  }
  const resolved = apiKey || envValue(ENV_KEY);
  if (!resolved) {
    throw configurationError(
      `No nRouter API key: pass apiKey or set ${ENV_KEY}.`,
    );
  }
  if (!resolved.startsWith(KEY_PREFIX)) {
    throw configurationError(
      `nRouter API keys must start with ${KEY_PREFIX}; got one that does not.`,
    );
  }
  return resolved;
}

/**
 * Vendor options, with `apiKey` NARROWED to a string.
 *
 * openai 7 widened its own `apiKey` to accept a function returning a key. This
 * SDK refuses that at runtime — `resolveApiKey` must check the `sk-nrouter-`
 * prefix before a request, and a function cannot be checked until the request
 * is already in flight. Inheriting the wider type unchanged would let
 * TypeScript accept `{ apiKey: async () => … }`, compile clean, and throw at
 * construction: a contract advertised in the types and denied at runtime.
 */
// NonNullable first: the vendor's parameter is optional, and `Omit` over a
// `X | undefined` union silently drops every property — which showed up as
// "Property 'baseURL' does not exist", not as anything about apiKey.
/**
 * The caller's default headers, normalized to a record, with the nRouter
 * bearer forced on and OpenAI's tenancy headers explicitly nulled.
 *
 * NORMALIZED, not spread. `defaultHeaders` is `HeadersLike`, which is four
 * different shapes — a `Headers`, an array of pairs, a plain record, and the
 * vendor's own BRANDED bag `{ values: Headers, nulls: Set }`. Object-spreading
 * is correct for exactly one of them: a `Headers` spreads to nothing, pairs
 * become numeric keys, and the branded bag spreads to its internals so an
 * appended `Authorization` sits beside `values` where the vendor never reads
 * it.
 *
 * That last case is not hypothetical. `withOptions({ apiKey })` passes the
 * branded bag straight back in, so a spread would leave the OLD key on the
 * wire — authenticating, and billing, the wrong tenant.
 */
function nrouterHeaders(
  source: unknown,
  apiKey: string,
): Record<string, string | string[] | null> {
  // `Object.create(null)` — NOT `{}`. This object is keyed by header names
  // that come from an environment variable, and `'toString' in {}` is true, so
  // a plain object would report inherited members as already-present. See the
  // env loop below, where that read decides whether a header is stripped.
  // Keyed by LOWERCASE name. Header names are case-insensitive, so
  // `[['X-Tag','a'],['x-tag','b']]` is two values of one header; exact-case
  // slots would keep only the last. The first casing seen is preserved for the
  // wire.
  const slots = new Map<string, { name: string; value: string[] | null }>();
  // Explicit caller names, lowercased, for the environment strip below.
  const fromCaller = new Set<string>();
  const add = (k: string, v: unknown, mode: 'set' | 'append' = 'append') => {
    // `undefined` CONTRIBUTES NOTHING, and must not register the name as
    // caller-set: doing so made `defaultHeaders: { 'api-key': undefined }`
    // suppress the environment strip below, so an OPENAI_CUSTOM_HEADERS
    // credential of the same name reached the gateway. Only a value or an
    // explicit `null` removal is an expression of intent.
    if (v === undefined) return;
    // An EMPTY array, or one holding only `undefined`, contributes nothing —
    // the vendor's builder treats it that way too. Registering a slot for it
    // would create a `null`, REMOVING the vendor's own header, and would
    // register caller intent that suppresses the environment strip below.
    const items = Array.isArray(v) ? v : [v];
    if (!items.some((x) => x !== undefined)) return;
    const key = k.toLowerCase();
    fromCaller.add(key);
    const slot = slots.get(key) ?? { name: k, value: null };
    slots.set(key, slot);
    // A RECORD property is a setter — `{ 'X-Tag': 'a', 'x-tag': 'b' }` ends as
    // `b`, because the two are the same header written twice. Tuple entries
    // are different: `[['X-Tag','a'],['x-tag','b']]` is a LIST, and both
    // values belong on the wire. Same names, different containers, different
    // meaning.
    if (mode === 'set') slot.value = null;
    // SEQUENTIAL, matching the vendor's own builder: entries are applied in
    // order, so `null` clears what came before and a value AFTER a null
    // restores the header. Short-circuiting on "an array contains a null"
    // would delete a header the caller had just re-set.
    for (const item of items) {
      if (item === undefined) continue;
      if (item === null) {
        slot.value = null;
        continue;
      }
      slot.value = [...(slot.value ?? []), String(item)];
    }
  };
  if (source instanceof Headers) {
    source.forEach((v, k) => add(k, v));
  } else if (Array.isArray(source)) {
    for (const pair of source as unknown[][]) add(String(pair[0]), pair[1]);
  } else if (source && typeof source === 'object') {
    const bag = source as { values?: unknown; nulls?: unknown };
    if (bag.values instanceof Headers) {
      bag.values.forEach((v, k) => add(k, v));
      // The branded bag carries removals separately; losing them would
      // resurrect a header the caller had already removed.
      if (bag.nulls instanceof Set) for (const k of bag.nulls as Set<string>) add(k, null);
    } else {
      for (const [k, v] of Object.entries(source as Record<string, unknown>)) add(k, v, 'set');
    }
  }

  // EVERY header the environment named, not just the ones we thought of.
  // OPENAI_CUSTOM_HEADERS is free-form, so a credential can arrive under any
  // name — `api-key:`, `x-api-key:`, anything — and an allowlist of
  // Authorization plus the two tenancy headers would forward the rest to
  // api.nrouter.ai. Gateway rules §4f gate 9: no provider credential in a
  // customer-visible header. A header the CALLER set explicitly is kept; only
  // the environment's contribution is removed.
  const out = Object.create(null) as Record<string, string | string[] | null>;
  for (const { name, value } of slots.values()) {
    out[name] = value === null ? null : value.length === 1 ? value[0]! : value;
  }
  const envHeaders = envValue('OPENAI_CUSTOM_HEADERS');
  if (envHeaders) {
    for (const line of envHeaders.split('\n')) {
      const colon = line.indexOf(':');
      if (colon < 0) continue;
      const name = line.slice(0, colon).trim();
      if (name && !fromCaller.has(name.toLowerCase())) out[name] = null;
    }
  }
  // These two are option-shaped as well as header-shaped (OPENAI_ORG_ID,
  // OPENAI_PROJECT_ID), so they are nulled whatever the caller passed: they
  // identify a different service's account and mean nothing to the gateway.
  out['OpenAI-Organization'] = null;
  out['OpenAI-Project'] = null;
  // LAST, and unconditional: the key on the wire is the one resolveApiKey
  // validated, whatever the environment or the caller put in first.
  out['Authorization'] = `Bearer ${apiKey}`;
  return out;
}

type NRouterOptions = Omit<
  NonNullable<ConstructorParameters<typeof OpenAI>[0]>,
  // `apiKey` — narrowed to a string below.
  // The rest are openai 7 authentication and routing options that CANNOT work
  // here: this constructor always injects an nRouter `apiKey` and `baseURL`,
  // and the vendor treats each of these as mutually exclusive with one or
  // both. Leaving them in the public type lets a call compile and then fail
  // inside the vendor with a mutually-exclusive-option error that names
  // nothing the caller wrote.
  // `credential` and `x509Transport` join them: an X.509 credential conflicts
  // with the injected `apiKey`, and `x509Transport` requires the
  // `workloadIdentity` omitted above, so neither can reach a working state.
  | 'apiKey'
  | 'provider'
  | 'workloadIdentity'
  | 'dataResidency'
  | 'credential'
  | 'x509Transport'
  // Always replaced with `null` below, so accepting them advertises an option
  // that silently does nothing.
  | 'adminAPIKey'
  | 'organization'
  | 'project'
> & {
  apiKey?: string;
  /**
   * `headers` is omitted deliberately. The constructor discards it — the
   * vendor spreads `fetchOptions` onto the request after the headers this SDK
   * pins, so it would overwrite the Authorization. Set headers through
   * `defaultHeaders`, which is normalized.
   */
  fetchOptions?: Omit<
    NonNullable<NonNullable<ConstructorParameters<typeof OpenAI>[0]>['fetchOptions']>,
    'headers'
  >;
};

/** The caller's own `fetch`, kept on our wrapper so a nested construction can
 * unwrap instead of stacking another closure over a stale key. */
const UNWRAPPED_FETCH = Symbol('nrouter.unwrappedFetch');

/** Where the untouched parsed error body is kept. Symbol-keyed and
 * non-enumerable so it can never surface in a log or a JSON.stringify. */
const ORIGINAL_BODY = Symbol('nrouter.originalErrorBody');

/**
 * The vendor client raises its own typed error on a non-2xx BEFORE the raw
 * response reaches us, which would make every nRouter error code unreachable.
 * This turns that throw back into a response so our own classifier — which
 * knows the nine gateway codes, the codeless status dispatch and the
 * `Retry-After` forms — is the one that decides.
 *
 * Anything that is not an APIError (DNS, TLS, an abort) is genuinely transport
 * and is re-thrown as such.
 */
function responseFromApiError(err: unknown): { status: number; headers: HeaderSource; text: string } {
  if (err instanceof OpenAI.APIError && typeof err.status === 'number') {
    const headers = (err.headers ?? new Headers()) as Headers;
    // Prefer the body stashed in makeStatusError: `err.error` is EMPTY for a
    // bare envelope, and that is exactly the shape whose loss misclassifies a
    // guardrail block and a budget ceiling.
    const body = (err as unknown as Record<symbol, unknown>)[ORIGINAL_BODY] ?? err.error;
    // A non-JSON error has NO parsed body at all — OpenAI keeps the response
    // text in `message` instead. Reconstructing an empty body there threw away
    // the only signal present: a text/plain 502 saying the upstream response
    // was "too large" is a PERMANENT condition, and without its wording it
    // classified as a transient service failure and invited a retry of a
    // request that was already billed (gateway gate 8).
    const text =
      body !== undefined
        ? JSON.stringify(body)
        : err.message
          ? JSON.stringify({ error: { message: redactKeys(err.message) } })
          : '';
    return { status: err.status, headers, text };
  }
  // NOT a raw rethrow. DNS, TLS, a timeout, an abort or exhausted retries all
  // arrive here as a vendor APIConnectionError, and `nr.chat()` was the only
  // helper that normalized it — so `nr.stream()` and every `nr.media.*` call
  // handed the caller a VENDOR error instead, and a single
  // `catch (e) { if (e instanceof nRouterError) ... }` silently missed them.
  //
  // The cause is preserved, so an abort is still recognisable through the
  // chain and `isRetryable` still answers false for it.
  // AN ABORT IS NOT A TRANSPORT FAILURE. When the signal fires while the
  // vendor client is awaiting response headers it throws `APIUserAbortError`
  // — whose `.name` is the string "Error", MEASURED, so a name-based check
  // misses it entirely. Wrapping it as an ordinary transport failure made
  // isRetryable() answer TRUE, and a generic retry loop could resend a
  // cancelled POST that had already been billed (gate 8).
  //
  // Normalized to a cause named AbortError so every downstream check —
  // isAbortError, isRetryable, the stream reader — agrees it was a
  // cancellation, whatever the runtime called it.
  if (err instanceof OpenAI.APIUserAbortError || isAbortLike(err)) {
    const abort = new Error('the request was cancelled before a response arrived');
    abort.name = 'AbortError';
    throw transportError('the request was cancelled before a response arrived', { cause: abort });
  }
  throw transportError(err instanceof Error ? err.message : String(err), { cause: err });
}

function contentTypeOf(headers: HeaderSource): string {
  const value =
    typeof (headers as { get?: unknown }).get === 'function'
      ? (headers as { get(name: string): string | null | undefined }).get('content-type')
      : (headers as Record<string, string | string[] | undefined>)['content-type'];
  const single = Array.isArray(value) ? value[0] : value;
  return (single ?? '').toLowerCase();
}

/**
 * Client pre-configured for nRouter.
 *
 * Every OpenAI resource (`chat.completions`, `embeddings`, `images`, …) is
 * inherited unchanged. `client.nr` adds the nRouter surface.
 */
export class nRouter extends OpenAI {
  /** Model discovery. See models.ts for why it reads the raw response. */
  readonly nrouterModels: NRouterModels;
  /** Snake-case alias kept for callers written against 1.0.0. */
  readonly nrouter_models: NRouterModels;
  /** Everything the playground can do. */
  readonly nr: NRouterSurface;

  /**
   * Node renders a plain object's fields on `console.log`, and the VENDOR base
   * class stores `apiKey` as a public field — so `console.log(client)` printed
   * the key verbatim into whatever log aggregator was listening (Rule #5). The
   * Go SDK guards the same thing with String/GoString; this is the JS
   * equivalent, and it covers `console.log`, `util.inspect` and `%o`.
   *
   * Addressed by `Symbol.for` rather than by importing `node:util`, so the
   * bundle stays runtime-agnostic and needs no node typings.
   */
  [Symbol.for('nodejs.util.inspect.custom')](): string {
    return this.toString();
  }

  toString(): string {
    const key = this.apiKey ?? '';
    const tail = key.length > 4 ? key.slice(-4) : '';
    return `nRouter { apiKey: '${KEY_PREFIX}...${tail}', baseURL: '${this.baseURL}' }`;
  }

  /** JSON.stringify must not be the way around the guard above. */
  toJSON(): Record<string, unknown> {
    return { baseURL: this.baseURL };
  }

  /**
   * EVERY vendor-raised error passes through here, including one from a
   * resource this SDK never wraps (`client.chat.completions.create()`).
   *
   * The gateway should never echo a key, but `message` and `error` are built
   * from a response body we do not control, and the test suite caught a real
   * case: a 401 whose body quoted the rejected key produced
   * `Error: 401 key sk-nrouter-…abcd refused`. `redactKeys` runs inside
   * `nRouterError` and this path never reaches it, so the redaction has to
   * happen at the source instead.
   *
   * The vendor ERROR TYPE is preserved — callers catching `OpenAI.APIError`
   * around an inherited resource keep working. Only the text changes.
   */
  protected override makeStatusError(
    ...args: Parameters<OpenAI['makeStatusError']>
  ): ReturnType<OpenAI['makeStatusError']> {
    // Positional and type-derived from the base signature rather than
    // restated: the vendor's `headers` is its OWN Headers type, not the DOM
    // one, and spelling it out here breaks on an upstream release for no gain.
    const [status, error, message, headers] = args;
    const redacted = redactDeep(error);
    // A CAST, not a `?? {}` default, and the difference is measurable. openai 7
    // types this parameter `Object` while the vendor itself passes `undefined`
    // for a non-JSON error body — measured against 7.8.0. `APIError.generate`
    // uses `message` only when `error` is absent: hand it an empty object and
    // it stops using the message and produces a generic "nRouter request
    // failed", so a `text/plain` 502 saying "the upstream response was too
    // large to process" reaches the caller with its wording gone and nothing
    // to act on. Satisfying the type with `{}` looked harmless and silently
    // deleted the only useful part of that error.
    const err = super.makeStatusError(status, redacted as Object, redactKeys(message ?? ''), headers);
    // KEEP THE PARSED BODY. `APIError.generate` populates `err.error` from a
    // NESTED `{"error":{…}}` envelope and DISCARDS a bare `{code,message}` one
    // — which a proxy in front of the gateway does produce. Without this a bare
    // guardrail_blocked lost both fields and reclassified as a plain request
    // error, and a bare budget 402 came back as insufficient credit: opposite
    // remedies, confidently wrong.
    Object.defineProperty(err, ORIGINAL_BODY, { value: redacted, enumerable: false });
    return err;
  }

  /**
   * Narrowed to the same contract as the constructor.
   *
   * openai 7 declares `withOptions(options: Partial<ClientOptions>)`, and
   * inheriting it unchanged reopens every door the constructor type closes:
   * `client.withOptions({ apiKey: async () => key })` compiles, then calls
   * this class's constructor and throws. A type that is narrow in one entry
   * point and wide in the other is not narrowed.
   */
  override withOptions(options: Partial<NRouterOptions>): this {
    // SEED FROM THE LIVE KEY. The vendor clones from `_options.apiKey`, which
    // is the constructor-time value and which the `apiKey` setter never
    // updates — so after a rotation every clone silently reverted to the
    // ORIGINAL key and billed the original tenant. An explicit `apiKey` in
    // `options` still wins, because it comes second.
    const seeded = { apiKey: this.apiKey as string, ...options };
    return super.withOptions(
      // Same NonNullable reason as NRouterOptions: the vendor parameter is
      // optional, so `Partial<...>` over it carries `undefined`.
      seeded as Partial<NonNullable<ConstructorParameters<typeof OpenAI>[0]>>,
    ) as this;
  }

  constructor(options: NRouterOptions = {}) {
    const apiKey = resolveApiKey(options?.apiKey);
    const baseURL = options?.baseURL || DEFAULT_BASE_URL;

    // MEASURED against openai 7.8.0, with OPENAI_CUSTOM_HEADERS and
    // OPENAI_ORG_ID set in the environment: `nr.chat()` sent
    // `authorization: Bearer sk-openai-LEAKED` and `openai-organization:
    // org-leak` TO api.nrouter.ai. The vendor reads OPENAI_CUSTOM_HEADERS,
    // OPENAI_ORG_ID, OPENAI_PROJECT_ID and OPENAI_ADMIN_KEY from the
    // environment and merges the parsed headers BEFORE `defaultHeaders`, so
    // they beat the auth header it derives from `apiKey`.
    //
    // That is a credential disclosure to the wrong service — an OpenAI key
    // handed to the nRouter gateway — and it needs nothing unusual to happen:
    // one process using both clients, one env var meant for the other one.
    //
    // `null` closes the three option-shaped channels. `Authorization` is set
    // explicitly LAST because ours is merged after the environment's and
    // therefore wins; this is the one place the SDK touches the key itself,
    // and it does so to guarantee the key on the wire is the one that was
    // validated above.
    // `fetchOptions` is spread onto the request AFTER the headers built above,
    // so `fetchOptions.headers` overwrites them wholesale — including the
    // Authorization this constructor just pinned. Reproduced: an
    // `Authorization: Bearer sk-openai-…` in there arrived at `fetch`
    // unchanged, which is the same credential-disclosure and wrong-tenant
    // billing the header normalization exists to prevent, reached by a
    // different door.
    //
    // Dropped rather than merged: every other transport setting in
    // `fetchOptions` is kept, and headers have a supported home in
    // `defaultHeaders`, which IS normalized.
    const { headers: _discardedFetchHeaders, ...fetchOptions } =
      (options.fetchOptions ?? {}) as Record<string, unknown>;

    // THE LAST SEAM, and the only one that covers every path. Everything above
    // sanitizes what this constructor is given; none of it reaches openai 7's
    // PER-REQUEST `fetchOptions`, which an inherited resource accepts as a
    // second argument (`client.chat.completions.create(body, { fetchOptions })`)
    // and which the vendor spreads onto the request LAST. An `Authorization`
    // there would reach api.nrouter.ai ahead of the validated key.
    //
    // Pinning it here instead of chasing each entry point means no future
    // vendor option can open a third door: whatever assembles the request,
    // these three headers are set on the way out.
    // UNWRAP FIRST. `withOptions({ apiKey })` re-enters this constructor with
    // the PREVIOUS instance's options, whose `fetch` is already a wrapper
    // closed over the OLD key. Stacking a new wrapper outside it leaves the
    // old one running last, so the re-keyed call went out on the original key
    // — authenticating and billing the wrong tenant, which is exactly what
    // the withOptions test exists to catch.
    const priorInner = (options.fetch as { [UNWRAPPED_FETCH]?: typeof fetch } | undefined)?.[
      UNWRAPPED_FETCH
    ];
    const callerFetch =
      priorInner ?? options.fetch ?? ((globalThis as { fetch?: typeof fetch }).fetch as typeof fetch);
    // LATE-BOUND, not the constructor-captured constant. `apiKey` is a public,
    // writable field on the vendor client, and before this wrapper existed the
    // vendor read it at dispatch — so `client.apiKey = nextKey` rotated the
    // credential. A captured constant would keep authenticating, and BILLING,
    // the previous tenant while the field says otherwise, and assigning `null`
    // would fail to disable anything. Rule #36: multi-tenancy and zero credit
    // leak.
    const self: { client?: { apiKey?: unknown } } = {};
    const pinnedFetch = ((url: unknown, init?: RequestInit) => {
      // Read, not validated. Validation happens in the `apiKey` SETTER
      // installed after `super()`: throwing from inside `fetch` gets wrapped by
      // the vendor into a RETRYABLE "Connection error.", so a caller's
      // `while (isRetryable(e))` loop would spin forever on a permanent
      // mistake in its own input — measured, and the exact anti-pattern this
      // SDK fixes elsewhere. The setter throws at the assignment site instead,
      // which is where the mistake was made.
      const current = (self.client?.apiKey as string | undefined) ?? apiKey;
      const headers = new Headers(init?.headers as ConstructorParameters<typeof Headers>[0]);
      headers.set('Authorization', `Bearer ${current}`);
      headers.delete('OpenAI-Organization');
      headers.delete('OpenAI-Project');
      return callerFetch(url as never, { ...(init ?? {}), headers });
    }) as typeof fetch;
    Object.defineProperty(pinnedFetch, UNWRAPPED_FETCH, {
      value: callerFetch,
      enumerable: false,
    });

    super({
      ...options,
      ...(options.fetchOptions ? { fetchOptions: fetchOptions as never } : {}),
      fetch: pinnedFetch,
      apiKey,
      baseURL,
      organization: null,
      project: null,
      adminAPIKey: null,
      defaultHeaders: nrouterHeaders(options.defaultHeaders, apiKey),
    });

    // After `super()`, so the wrapper above can see the live field.
    self.client = this as unknown as { apiKey?: unknown };

    // `apiKey` is a public writable field on the vendor client, so a caller can
    // rotate it — and must be able to, since the vendor read it at dispatch.
    // The setter keeps that working AND keeps the prefix guarantee: an invalid
    // rotation throws a permanent configuration error right here, rather than
    // travelling to the gateway or surfacing later as a retryable transport
    // failure.
    let key = apiKey;
    Object.defineProperty(this, 'apiKey', {
      get: () => key,
      set: (next: unknown) => {
        key = assertNRouterKey(next);
      },
      enumerable: true,
      configurable: true,
    });

    this.nrouterModels = new NRouterModels(this as unknown as RawRequester);
    this.nrouter_models = this.nrouterModels;
    this.nr = new NRouterSurface(this);
  }
}

/**
 * The nRouter-specific surface, hung off `client.nr` so it cannot collide with
 * a vendor resource now or after an upstream release.
 */
export class NRouterSurface implements ChatRunner, StreamRunner, Transport {
  readonly media: Multimodal;

  constructor(private readonly client: nRouter) {
    this.media = new Multimodal(this);
  }

  /** Model discovery, reachable from the same namespace as everything else. */
  get models(): NRouterModels {
    return this.client.nrouterModels;
  }

  /** One buffered call with full playground parity; returns body AND metadata. */
  chat(opts: NRouterCallOptions): Promise<NRouterResponse<Record<string, unknown>>> {
    return runChat(this, opts);
  }

  /** The assistant text of a buffered reply, defensively. */
  text(res: NRouterResponse<Record<string, unknown>>): string {
    return chatText(res);
  }

  /** The same options against several models at once, results in model order. */
  compare(
    opts: NRouterCallOptions,
    models: string[],
  ): Promise<NRouterResponse<Record<string, unknown>>[]> {
    return runCompare(this, opts, models);
  }

  /** Server-sent-events streaming, with the response metadata beside it. */
  stream(opts: NRouterCallOptions, signal?: AbortSignal): Promise<StreamResult> {
    return streamChat(this, opts, signal);
  }

  /** POST /v1/responses with nRouter feature options and response metadata. */
  responses(
    body: Record<string, unknown>,
    opts?: NRouterFeatureOptions,
  ): Promise<NRouterResponse<Record<string, unknown>>> {
    return jsonRequest(this, '/responses', buildFeatureBody(body, opts));
  }

  /** POST /v1/messages with nRouter feature options and response metadata. */
  messages(
    body: Record<string, unknown>,
    opts?: NRouterFeatureOptions,
  ): Promise<NRouterResponse<Record<string, unknown>>> {
    return jsonRequest(this, '/messages', buildFeatureBody(body, opts));
  }

  /** POST /v1/messages/count_tokens. This endpoint is not billed. */
  countTokens(body: Record<string, unknown>): Promise<NRouterResponse<Record<string, unknown>>> {
    return jsonRequest(this, '/messages/count_tokens', body);
  }

  /** Parse the `x-nr-*` headers of a response obtained some other way. */
  meta(headers: HeaderSource): ResponseMeta {
    return metaFromHeaders(headers);
  }

  // --- ChatRunner ---------------------------------------------------------
  async request(
    pathOrReq: string | TransportRequest,
    body?: unknown,
  ): Promise<
    { status: number; headers: HeaderSource; text: string; contentType: string } & TransportResponse
  > {
    // ONE method serving both seams. ChatRunner calls request(path, body);
    // Transport (multimodal) calls request({method, path, body, ...}). They are
    // distinguished by argument shape rather than by two near-identical
    // methods, because two implementations of "send a request" is exactly how
    // a header or a refusal ends up applied on one path and not the other.
    const req: TransportRequest =
      typeof pathOrReq === 'string'
        ? { method: 'POST', path: pathOrReq, contentType: 'application/json', body: encodeJson(body) }
        : pathOrReq;

    let res: FetchResponse;
    try {
      res = await this.raw(req);
    } catch (err) {
      const recovered = responseFromApiError(err);
      const headers = recovered.headers;
      const bytes = new TextEncoder().encode(recovered.text);
      return {
        status: recovered.status,
        headers,
        text: recovered.text,
        contentType: contentTypeOf(headers),
        bytes: async () => bytes,
      };
    }

    // The socket can fail AFTER the headers arrived. Letting arrayBuffer()
    // reject raw here meant chat() reported a null status and null request id
    // for a request that DID reach the gateway and may have been billed, and
    // every nr.media.* helper leaked the bare Error because its own body-read
    // catch is downstream of this point. Normalize here, where the status and
    // headers are already in hand.
    let buffer: Uint8Array;
    try {
      buffer = new Uint8Array(await res.arrayBuffer());
    } catch (err) {
      const meta = metaFromHeaders(res.headers);
      const failure = transportError(
        `the response body could not be read (${err instanceof Error ? err.message : String(err)}); ` +
          'the request reached the gateway and may have been billed',
        { status: res.status, meta, cause: err },
      );
      throw failure;
    }
    return {
      status: res.status,
      headers: res.headers,
      // LAZY. `text` used to be decoded eagerly, so every binary response —
      // a video from videoContent(), an mp3 from speech() — was materialised
      // as a second, unused JavaScript string the size of the payload. On a
      // large MP4 that is an unbounded extra allocation and a plausible way to
      // exhaust the Node heap on a response the caller only ever reads as
      // bytes. A getter costs nothing until something asks.
      get text() {
        return new TextDecoder().decode(buffer);
      },
      contentType: contentTypeOf(res.headers),
      bytes: async () => buffer,
    };
  }

  // --- StreamRunner -------------------------------------------------------
  async open(
    path: string,
    body: unknown,
    signal?: AbortSignal,
  ): Promise<{
    status: number;
    headers: HeaderSource;
    body: AsyncIterable<Uint8Array> | null;
    text?: () => Promise<string>;
  }> {
    let res: FetchResponse;
    try {
      res = await this.raw({
        method: 'POST',
        path,
        contentType: 'application/json',
        body: encodeJson(body),
        signal,
      });
    } catch (err) {
      const recovered = responseFromApiError(err);
      return {
        status: recovered.status,
        headers: recovered.headers,
        body: null,
        text: async () => recovered.text,
      };
    }
    return {
      status: res.status,
      headers: res.headers,
      // A stream must NOT be buffered here: the whole point is that the caller
      // sees the first token before the last one exists.
      body: res.body as unknown as AsyncIterable<Uint8Array> | null,
      text: () => res.text(),
    };
  }

  /**
   * The single place a request leaves this SDK.
   *
   * It goes through the VENDOR client's own pipeline, which is what keeps the
   * caller's `fetch` override, `timeout`, `maxRetries`, `fetchOptions`,
   * `defaultHeaders` and `defaultQuery` applied to every nRouter call too —
   * and is why this SDK never touches the API key itself.
   */
  private async raw(req: TransportRequest): Promise<FetchResponse> {
    const headers: Record<string, string> = {};
    if (req.contentType) headers['content-type'] = req.contentType;

    const options = {
      body: req.body,
      headers,
      signal: req.signal as AbortSignal | undefined,
      // NO CLIENT-SIDE RETRY ON A BILLED POST. The vendor client retries twice
      // by default and these calls are NOT idempotent: a timeout or a 5xx
      // after the gateway already accepted `POST /videos` creates and bills a
      // SECOND job, with no idempotency key for anything to dedupe on. Gateway
      // gate 8 is explicit that a retry is a second call and a second BILL,
      // and the gateway owns retry and fallback on its own side, where the
      // credit is reserved once per customer request.
      //
      // GET keeps the caller's setting: re-reading /models costs nothing.
      ...(req.method === 'GET' ? {} : { maxRetries: 0 }),
      // The vendor client would otherwise JSON-encode `body` a second time.
      //
      // MEASURED FLOOR: `__binaryRequest` landed in openai 4.50.0 — absent in
      // 4.45/4.47/4.48/4.49, present in 4.50.0. package.json used to declare
      // `^4.0.0`, so a consumer resolving 4.44 got a client that IGNORED this
      // flag and JSON.stringify'd the Uint8Array into {"0":82,"1":73,…} —
      // corrupt bodies on EVERY nr call — while this repo's suite stayed green
      // because the lockfile pins 4.104.0. The floor is now ^4.50.0 and
      // test/client.test.ts asserts it, so the range cannot quietly widen back.
      __binaryRequest: true,
    } as unknown as Record<string, unknown>;

    const promise =
      req.method === 'GET'
        ? this.client.get(req.path, options)
        : this.client.post(req.path, options);
    const res = (await promise.asResponse()) as unknown as FetchResponse;
    // DUCK-TYPED, not `instanceof Response`. MEASURED: the vendor client hands
    // back a Response whose CONSTRUCTOR IS NAMED `Response` but is not the
    // global one — node-fetch's, or undici's bundled copy, depending on the
    // runtime. `res instanceof Response` is therefore false for a perfectly
    // good response, and the guard rejected every call in the first end-to-end
    // run. Check for the capabilities actually used instead.
    if (typeof res?.status !== 'number' || typeof res?.headers?.get !== 'function') {
      throw transportError('the vendor client returned an unusable response object');
    }
    return res;
  }
}

/**
 * The slice of a fetch Response this SDK uses.
 *
 * Structural on purpose: see the note in `raw` — the concrete class differs by
 * runtime and naming it would tie the SDK to one of them.
 */
interface FetchResponse {
  status: number;
  headers: { get(name: string): string | null };
  arrayBuffer(): Promise<ArrayBuffer>;
  text(): Promise<string>;
  body: unknown;
}

function encodeJson(body: unknown): Uint8Array {
  // A BigInt or a circular reference in `opts.extra` throws here, before
  // anything is sent. It used to surface through the chat and streaming paths
  // as a RETRYABLE transport failure, so a caller honouring isRetryable()
  // looped forever on a permanent mistake in its own input that no retry could
  // fix. Configuration: local, and permanent.
  try {
    return new TextEncoder().encode(JSON.stringify(body ?? {}));
  } catch (err) {
    throw configurationError(
      `the request body cannot be JSON-encoded (${err instanceof Error ? err.message : String(err)}). ` +
        'A BigInt or a circular reference in `extra` is the usual cause; nothing was sent.',
    );
  }
}

/**
 * Redact any key inside a parsed error body.
 *
 * Round-tripping through JSON is deliberate: the body is arbitrary provider
 * JSON, and walking it by hand would miss a key nested in an array, in a
 * `metadata` blob, or under a field this SDK has never seen. Anything that
 * cannot be serialized is dropped rather than passed through unexamined.
 */
function redactDeep(body: Object | undefined): Object | undefined {
  if (body === undefined) return undefined;
  try {
    return JSON.parse(redactKeys(JSON.stringify(body))) as Object;
  } catch {
    return undefined;
  }
}
