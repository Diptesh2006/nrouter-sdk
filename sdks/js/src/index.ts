/**
 * @nrouter_ai/sdk — one API key for models across six provider clouds.
 *
 *   import { nRouter } from "@nrouter_ai/sdk";
 *
 *   const client = new nRouter();              // reads NROUTER_API_KEY
 *   const res = await client.nr.chat({
 *     model: "claude-sonnet-4-5-20250929",
 *     prompt: "Hello!",
 *     cache: false,
 *   });
 *   console.log(client.nr.text(res));
 *   // Unpriced is NOT free — it is unknown. Never render null as 0.
 *   console.log(res.meta.cost ?? `unpriced (${res.meta.costStatus})`);
 *
 * Every OpenAI resource is inherited unchanged: `client.chat.completions`,
 * `client.embeddings`, `client.images` all work as they always did.
 */

export {
  nRouter,
  NRouterSurface,
  DEFAULT_BASE_URL,
  DEFAULT_BODY_IDLE_TIMEOUT_MS,
  DEFAULT_REQUEST_TIMEOUT_MS,
  ENV_KEY,
  KEY_PREFIX,
  validateGatewayBaseUrl,
  extractTraceHeaders,
  withTraceContext,
} from './client';

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

export {
  metaFromHeaders,
  metaFromLookup,
  isPriced,
  EMPTY_META,
  parseBudgetWarning,
  isCacheHit,
  isCacheMiss,
  type BudgetWarningInfo,
} from './meta';
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
  parseGatewayErrorEnvelope,
  type ParsedErrorEnvelope,
  type ParsedErrorBody,
  parseRetryAfter,
  MAX_RETRY_AFTER_SECONDS,
  computeJitteredBackoff,
  type BackoffOptions,
  safeJsonParse,
  formatNRouterError,
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

// The Anthropic Messages wire. Exported for the same reason `buildChatBody` is:
// a caller assembling its own request needs to know which wire a model is
// served on, because the gateway declares `chat_completions: None` for
// Anthropic and answers 404 there. `MESSAGES_PATH` and the refusal helper stay
// unexported — `stream.ts` reaches them internally and they are not a contract.
export {
  usesMessagesWire,
  toAnthropicMessagesRequest,
  toOpenAIChatCompletion,
  isAnthropicMessageResponse,
  createAnthropicSSETranslator,
  extractNRouterHeaders,
  toFinishReason,
  toOpenAIUsage,
  type OpenAIUsage,
  type AnthropicRequestResult,
} from './chat';

// Conversation memory. CLIENT-SIDE ONLY — the gateway stores nothing between
// requests, and `memory` appears nowhere in the wire spec. Every method is a
// Promise so an async store (Redis, a file) is a one-line swap rather than a
// change at every call site.
export {
  createMemory,
  createArrayStore,
  slidingWindow,
  type Memory,
  type MemoryStore,
  type MemoryOptions,
  type WindowOptions,
} from './memory';

// Prompt templates. Ergonomics over the two wire fields that DO exist and are
// consumed (`prompt_runtime.rs` removes each independently); no new field, and
// a test pins that this module's key set equals `buildExtraBody`'s so the
// omission rules cannot fork.
export {
  PROMPT_TEMPLATE_ID_FIELD,
  PROMPT_VARIABLES_FIELD,
  PROMPT_WIRE_FIELDS,
  SYSTEM_VARIABLE_NAMES,
  promptTemplate,
  promptVariables,
  withVariables,
  promptExtraBody,
  applyPrompt,
  systemVariableConflicts,
  renderPrompt,
  type PromptSelection,
  type SystemVariableName,
  type RenderPromptOptions,
} from './prompts';

// chatTextDiagnostic is re-exported here deliberately: index.ts uses an explicit named
// list, not export *, so an accessor added to chat.ts is unreachable to a package
// consumer until it appears on this line (DIPTESH-094).
export {
  chatText,
  chatTextDiagnostic,
  compareError,
  COMPARE_ERROR_KEY,
  type ChatRunner,
  type ChatRunnerResponse,
  type ChatTextDiagnostic,
  type ChatTextCondition,
} from './chat';

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
  VALID_AUDIO_FORMATS,
  validateAudioFormat,
  type AudioFormat,
  type WaitForVideoOptions,
  type Transport,
  type TransportRequest,
  type TransportResponse,
} from './multimodal';

export {
  diagnoseReasoningExhaustion,
  type ReasoningExhaustionReport,
} from './diagnostics';

export { nRouter as default } from './client';
