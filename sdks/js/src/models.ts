// Model discovery for nRouter, extracted from the client so the transport and
// the discovery logic can be reasoned about (and tested) separately.
//
// Everything here is built on ONE decision, and it is load-bearing: discovery
// goes through the inherited vendor client's own request pipeline, and reads
// the RAW response body rather than the vendor SDK's parsed page object. The
// two halves of that decision are documented on `RawRequester` and on `list()`
// respectively; neither is an implementation detail to be "cleaned up".

/**
 * One model as the gateway describes it.
 *
 * The index signature is deliberate: the gateway may add descriptive fields
 * (context window, modality, provider attribution) and a closed type would
 * discard them silently, leaving a caller unable to read a field they can see
 * in the JSON. Only `id` is guaranteed — it is the only field the wire format
 * requires and the only one this SDK depends on.
 */
export type NRouterModel = {
  id: string;
  object?: string;
  owned_by?: string;
  [key: string]: unknown;
};

/** The `/models` envelope: `data` plus whatever else the gateway sends. */
export type NRouterModelList = {
  data: NRouterModel[];
  object?: string;
  [key: string]: unknown;
};

/**
 * The slice of the inherited OpenAI client this helper needs: its own request
 * pipeline. Going through it is what keeps the caller's `fetch` override,
 * `timeout`, `maxRetries`, `fetchOptions`, `defaultHeaders` and `defaultQuery`
 * applied to model discovery, and is why no global `fetch` is required.
 *
 * It is a structural type rather than an import of the vendor client so this
 * module stays testable with a hand-written double, and so a vendor-side type
 * change is a compile error at one seam instead of a rewrite here.
 */
export interface RawRequester {
  get(
    path: string,
    opts?: unknown
  ): { asResponse(): Promise<{ json(): Promise<unknown>; headers?: Headers }> };
}

/** Whether a value is a plain, non-null object we can read fields off. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Percent-encode a model id for use as a single path segment.
 *
 * Model aliases carry `/` and `:` on some providers (`meta/llama-3.1-70b`,
 * `anthropic.claude-sonnet-4-5:0`). Interpolated unencoded, a `/` splits the
 * id into two path segments and the request silently addresses a DIFFERENT
 * resource — the failure mode is a confusing 404 or, worse, a 200 describing
 * the wrong model. `encodeURIComponent` is the right tool rather than
 * `encodeURI`, which leaves `/` alone precisely because it expects a path.
 */
function encodeModelId(modelId: string): string {
  return encodeURIComponent(modelId);
}

/**
 * Model discovery against `/models` and `/models/{id}`.
 *
 * Constructed with the nRouter client itself; see `RawRequester` for why the
 * client's pipeline — not a bare `fetch` — is the transport.
 */
export class NRouterModels {
  constructor(private readonly client: RawRequester) {}

  /**
   * List every model this key can reach, from nRouter's raw JSON response.
   *
   * The OpenAI JS SDK receives the right raw body from nRouter, but its page
   * parser exposes an EMPTY `data` array. Reading the raw response is the fix,
   * and it keeps model discovery reliable without leaving the client's
   * configured transport. A future "simplify this to `client.models.list()`"
   * is therefore the regression, not the cleanup: it compiles, it returns a
   * well-formed empty list, and every caller concludes the account has no
   * models.
   *
   * Errors are NOT handled here on purpose: a non-2xx raises the vendor
   * client's own typed error (`APIError` and its subclasses) inside `get()`,
   * before this method ever sees a body. The defensiveness below is about a
   * SUCCESSFUL response whose shape is unexpected — a proxy returning HTML, a
   * gateway version that renames the envelope — where returning an empty list
   * lets a caller degrade rather than crash on a discovery call that is
   * usually decorative.
   */
  async list(): Promise<NRouterModelList> {
    const response = await this.client.get('/models').asResponse();
    const body: unknown = await response.json();

    if (!isRecord(body) || !Array.isArray(body.data)) {
      return { data: [] };
    }

    // Spread first so `object` and any future envelope fields survive, then
    // pin `data` to the array we just proved is one.
    return { ...body, data: body.data as NRouterModel[] };
  }

  /**
   * Just the model ids, in the order the gateway returned them.
   *
   * Entries without a usable string `id` are dropped rather than surfaced as
   * `undefined`, because every consumer of this list feeds it straight into a
   * `model:` field where an `undefined` becomes the string "undefined" and a
   * baffling upstream error.
   */
  async ids(): Promise<string[]> {
    const { data } = await this.list();
    return data
      .map((model) => model.id)
      .filter((id): id is string => typeof id === 'string' && id.length > 0);
  }

  /**
   * Fetch one model's descriptor from `/models/{id}`.
   *
   * The gateway serves this route (confirmed: without a key it answers 401,
   * not 404). As with `list()`, a non-2xx — including the 404 for an unknown
   * model — raises the vendor client's typed error before we see a body, so a
   * caller who wants a boolean should use `has()` rather than try/catch here,
   * which would swallow auth and network failures as "not found".
   */
  async get(modelId: string): Promise<NRouterModel> {
    if (typeof modelId !== 'string' || modelId.trim() === '') {
      // Guarded rather than passed through: an empty id builds `/models/`,
      // which is the LIST endpoint, so the caller would get a 200 carrying an
      // envelope instead of an error telling them the id was missing.
      throw new TypeError('modelId must be a non-empty string.');
    }

    const response = await this.client
      .get(`/models/${encodeModelId(modelId)}`)
      .asResponse();
    const body: unknown = await response.json();

    if (!isRecord(body) || typeof body.id !== 'string') {
      throw new Error(
        `Unexpected /models response for '${modelId}': no string 'id' field.`
      );
    }

    return body as NRouterModel;
  }

  /**
   * Whether `modelId` appears in this key's model list.
   *
   * The comparison is EXACT and case-sensitive, deliberately. Model aliases
   * are case-sensitive on the wire, so a case-insensitive match would answer
   * `true` for `Claude-Sonnet-4-5` and then fail at call time — turning a
   * cheap, correct pre-flight check into a false reassurance.
   *
   * Implemented over `ids()` rather than over `get()` so a 401, a timeout or a
   * transport failure propagates as itself instead of being reported as "the
   * model does not exist".
   */
  async has(modelId: string): Promise<boolean> {
    const ids = await this.ids();
    return ids.includes(modelId);
  }
}
