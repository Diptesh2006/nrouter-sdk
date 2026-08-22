// nRouter client — thin wrapper around the OpenAI SDK.

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

/**
 * Client pre-configured for nRouter (OpenAI wire format).
 *
 * Supports the same resources as the OpenAI SDK (chat.completions,
 * completions, embeddings, images, models, ...) — nRouter proxies the
 * standard OpenAI wire format, so every method works unmodified.
 */
export class nRouter extends OpenAI {
  constructor(options: NRouterOptions = {}) {
    super({
      ...options,
      apiKey: resolveApiKey(options?.apiKey),
      baseURL: options?.baseURL || DEFAULT_BASE_URL,
    });
  }
}
