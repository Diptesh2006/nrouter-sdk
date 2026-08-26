// nRouter client: thin wrapper around the OpenAI SDK.

import OpenAI from "openai";

const DEFAULT_BASE_URL = "https://api.nrouter.ai/v1";
const ENV_KEY = "NROUTER_API_KEY";
const KEY_PREFIX = "sk-nrouter-";

function resolveApiKey(apiKey?: string): string {
  const resolved = apiKey || process.env[ENV_KEY];
  if (!resolved || !resolved.startsWith(KEY_PREFIX)) {
    throw new Error(
      `nRouter API keys must start with '${KEY_PREFIX}'; pass apiKey or set ${ENV_KEY}.`
    );
  }
  return resolved;
}

type NRouterOptions = ConstructorParameters<typeof OpenAI>[0];

export type NRouterModel = {
  id: string;
  object?: string;
  owned_by?: string;
  [key: string]: unknown;
};

export type NRouterModelList = {
  data: NRouterModel[];
  object?: string;
  [key: string]: unknown;
};

/**
 * The slice of the inherited OpenAI client this helper needs: its own request
 * pipeline. Going through it is what keeps the caller's `fetch` override,
 * `timeout`, `maxRetries`, `httpAgent`, `defaultHeaders` and `defaultQuery`
 * applied to model discovery, and is why no global `fetch` is required.
 */
type RawRequester = {
  get(path: string, opts?: unknown): { asResponse(): Promise<{ json(): Promise<unknown> }> };
};

export class NRouterModels {
  constructor(private readonly client: RawRequester) {}

  /**
   * List models from nRouter's raw JSON response.
   *
   * The OpenAI JS SDK receives the right raw body from nRouter, but its page
   * parser exposes an empty `data` array. Reading the raw response keeps model
   * discovery reliable without leaving the client's configured transport: a
   * non-2xx still raises the SDK's own typed error before we get here.
   */
  async list(): Promise<NRouterModelList> {
    const response = await this.client.get("/models").asResponse();
    return (await response.json()) as NRouterModelList;
  }
}

/**
 * Client pre-configured for nRouter (OpenAI wire format).
 *
 * Supports the same resources as the OpenAI SDK (chat.completions,
 * completions, embeddings, images, ...). Use `client.nrouterModels.list()` for
 * model discovery because OpenAI JS currently mis-parses nRouter's otherwise
 * valid raw model list.
 */
export class nRouter extends OpenAI {
  readonly nrouterModels: NRouterModels;
  readonly nrouter_models: NRouterModels;

  constructor(options: NRouterOptions = {}) {
    const apiKey = resolveApiKey(options?.apiKey);
    const baseURL = options?.baseURL || DEFAULT_BASE_URL;

    super({
      ...options,
      apiKey,
      baseURL,
    });

    this.nrouterModels = new NRouterModels(this as unknown as RawRequester);
    this.nrouter_models = this.nrouterModels;
  }
}
