/**
 * @nrouter_ai/sdk — one API key for models across six provider clouds.
 *
 *   import { nRouter } from "@nrouter_ai/sdk";
 *
 *   const client = new nRouter();              // reads NROUTER_API_KEY
 *   const res = await client.nr.chat({
 *     model: "anthropic/claude-sonnet-4-5-20250929",
 *     prompt: "Hello!",
 *     guardrailIds: ["<uuid>"],                // playground parity
 *     cache: false,
 *   });
 *   console.log(client.nr.text(res));
 *   // Unpriced is NOT free — it is unknown. Never render null as 0.
 *   console.log(res.meta.cost ?? `unpriced (${res.meta.costStatus})`);
 *
 * Every OpenAI resource is inherited unchanged: `client.chat.completions`,
 * `client.embeddings`, `client.images` all work as they always did.
 */

export { nRouter, NRouterSurface, DEFAULT_BASE_URL, ENV_KEY, KEY_PREFIX } from './client';

// The contract: metadata, options and the wire shapes.
export {
  HEADER_NAMES,
  type ResponseMeta,
  type HeaderName,
  type NRouterExtraBody,
  type NRouterFeatureOptions,
  type NRouterCallOptions,
  type NRouterResponse,
  type ChatMessage,
  type ChatContentPart,
  type ChatRole,
} from './types';

export { metaFromHeaders, metaFromLookup, isPriced, EMPTY_META } from './meta';
export { jsonRequest } from './json';

// Typed errors. Catch `nRouterError` for all of them, a subclass for one.
export {
  nRouterError,
  nRouterRequestError,
  nRouterGuardrailBlockedError,
  nRouterAuthenticationError,
  nRouterCreditError,
  nRouterBudgetExceededError,
  nRouterNotFoundError,
  nRouterRateLimitError,
  nRouterServiceError,
  nRouterTransportError,
  nRouterConfigurationError,
  classifyError,
  classifyErrorClass,
  createError,
  configurationError,
  transportError,
  isRetryable,
  parseErrorBody,
  parseRetryAfter,
  withResponse,
  ERROR_CLASS_BY_CODE,
  ERROR_STATUS_BY_CODE,
  type nRouterErrorKind,
  type nRouterErrorOptions,
} from './errors';

// The sampling policy, exported because a caller building its own body needs
// the same Claude temperature-XOR-top_p rule the playground applies.
export {
  buildSamplingParams,
  isClaudeModel,
  type SamplingInput,
  type SamplingParams,
} from './sampling';

// Body construction, exported for the same reason.
export { buildChatBody, buildExtraBody, buildFeatureBody, buildMessages } from './options';

export { NRouterModels, type NRouterModel, type NRouterModelList, type RawRequester } from './models';

export { chatText, compareError, COMPARE_ERROR_KEY, type ChatRunner, type ChatRunnerResponse } from './chat';

export {
  parseSSE,
  isAbortError,
  type StreamRunner,
  type StreamChunk,
  type StreamResult,
} from './stream';

export {
  Multimodal,
  dataUrlToPart,
  MULTIMODAL_ENDPOINTS,
  type Transport,
  type TransportRequest,
  type TransportResponse,
} from './multimodal';

export { nRouter as default } from './client';
