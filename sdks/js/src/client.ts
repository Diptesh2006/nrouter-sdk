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
import { configurationError, redactKeys, transportError } from './errors';
import { metaFromHeaders, type HeaderSource } from './meta';
import { NRouterModels, type RawRequester } from './models';
import { Multimodal, type Transport, type TransportRequest, type TransportResponse } from './multimodal';
import { streamChat, type StreamRunner, type StreamResult } from './stream';
import type { NRouterCallOptions, NRouterResponse, ResponseMeta } from './types';

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
function resolveApiKey(apiKey?: string): string {
  const resolved = apiKey || process.env[ENV_KEY];
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

type NRouterOptions = ConstructorParameters<typeof OpenAI>[0];

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
    const err = super.makeStatusError(status, redacted, redactKeys(message ?? ''), headers);
    // KEEP THE PARSED BODY. `APIError.generate` populates `err.error` from a
    // NESTED `{"error":{…}}` envelope and DISCARDS a bare `{code,message}` one
    // — which a proxy in front of the gateway does produce. Without this a bare
    // guardrail_blocked lost both fields and reclassified as a plain request
    // error, and a bare budget 402 came back as insufficient credit: opposite
    // remedies, confidently wrong.
    Object.defineProperty(err, ORIGINAL_BODY, { value: redacted, enumerable: false });
    return err;
  }

  constructor(options: NRouterOptions = {}) {
    const apiKey = resolveApiKey(options?.apiKey);
    const baseURL = options?.baseURL || DEFAULT_BASE_URL;

    super({ ...options, apiKey, baseURL });

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
      text: new TextDecoder().decode(buffer),
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
   * caller's `fetch` override, `timeout`, `maxRetries`, `httpAgent`,
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
