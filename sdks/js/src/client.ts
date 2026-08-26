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

type FetchLike = (url: string, init?: any) => Promise<any>;

export class NRouterModels {
  constructor(
    private readonly apiKey: string,
    private readonly baseURL: string,
    /**
     * The transport the client was configured with. Falls back to the global
     * `fetch` only when the caller passed no override, so a configured proxy,
     * timeout or instrumentation hook still applies to model discovery.
     */
    private readonly fetchImpl?: FetchLike,
  ) {}

  /**
   * List models using nRouter's raw JSON response.
   *
   * The OpenAI JS SDK currently receives the right raw body from nRouter, but
   * its page parser exposes an empty `data` array. This helper stays direct so
   * model discovery remains reliable.
   */
  async list(): Promise<NRouterModelList> {
    const fetchImpl = this.fetchImpl ?? ((globalThis as any).fetch as FetchLike | undefined);
    if (typeof fetchImpl !== "function") {
      throw new Error(
        "nRouter model listing requires a fetch implementation: pass `fetch` to the " +
          "nRouter constructor, or run on a runtime with a global fetch.",
      );
    }

    const response = await fetchImpl(`${this.baseURL.replace(/\/+$/, "")}/models`, {
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
      },
    });

    if (!response.ok) {
      let message = `nRouter models request failed with status ${response.status}`;
      try {
        const body = await response.json();
        message = body?.error?.message || body?.error || message;
      } catch {
        // Keep the status-based message when the body is not JSON.
      }
      throw new Error(message);
    }

    return response.json();
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

    this.nrouterModels = new NRouterModels(
      apiKey,
      baseURL,
      (options as { fetch?: FetchLike } | undefined)?.fetch,
    );
    this.nrouter_models = this.nrouterModels;
  }
}
