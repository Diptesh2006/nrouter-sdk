import type { PayloadLimits, ConfidenceThresholds, ResolvedConfig, SupportAgentConfig, KnowledgeStore, KnowledgeIndex } from './types.js';
import { SupportAgentError } from './errors.js';
import { createClient } from './client.js';
import { createMemoryKnowledgeStore } from './knowledge/store.js';

export const DEFAULT_LIMITS: PayloadLimits = { maxMessages: 12, maxMessageChars: 2000, maxPageContextChars: 1000 };
export const DEFAULT_CONFIDENCE: ConfidenceThresholds = { high: 0.55, medium: 0.4 };
export const DEFAULT_TOP_K = 5;
export const DEFAULT_MAX_TOKENS = 1024;
export const DEFAULT_MAX_TOOL_STEPS = 4;
export const DEFAULT_AGENT_NAME = 'Support';

export const MAX_MODELS = 3;
export const DEFAULT_BOOKING_LABEL = 'Book a meeting';
export const MAX_BOOKING_URL_CHARS = 2048;
export const MAX_BOOKING_LABEL_CHARS = 60;
export const DEFAULT_SUGGESTIONS_MAX = 3;
export const MAX_SUGGESTIONS = 5;

function isKnowledgeIndex(k: KnowledgeStore | KnowledgeIndex): k is KnowledgeIndex {
  return 'version' in k && 'chunks' in k && k.version === 1;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** One id or an ordered list → a non-empty, de-duplicated list of at most MAX_MODELS. */
function resolveModels(model: unknown): string[] {
  const list = Array.isArray(model) ? model : [model];
  if (list.length === 0 || list.some((m) => typeof m !== 'string' || m.trim() === '')) {
    throw new SupportAgentError('invalid_config', 'model is required and must be a non-empty string or a list of them');
  }
  const models = [...new Set(list as string[])];
  if (models.length > MAX_MODELS) {
    throw new SupportAgentError('invalid_config', `model must list at most ${MAX_MODELS} distinct models`);
  }
  return models;
}

function resolveDefaultHeaders(headers: unknown): Record<string, string> | undefined {
  if (headers === undefined) return undefined;
  if (!isPlainObject(headers) || Object.entries(headers).some(([k, v]) => k.trim() === '' || typeof v !== 'string')) {
    throw new SupportAgentError('invalid_config', 'defaultHeaders must be an object of string header values');
  }
  return headers as Record<string, string>;
}

function resolveBooking(booking: unknown): ResolvedConfig['booking'] {
  if (booking === undefined) return null;
  if (!isPlainObject(booking)) {
    throw new SupportAgentError('invalid_config', 'booking must be an object with a url');
  }
  const { url, label } = booking;
  let protocol = '';
  if (typeof url === 'string' && url.length <= MAX_BOOKING_URL_CHARS) {
    try {
      protocol = new URL(url).protocol;
    } catch {
      protocol = '';
    }
  }
  if (protocol !== 'https:') {
    throw new SupportAgentError('invalid_config', `booking.url must be an https URL of at most ${MAX_BOOKING_URL_CHARS} characters`);
  }
  if (label === undefined) {
    return { url: url as string, label: DEFAULT_BOOKING_LABEL };
  }
  if (typeof label !== 'string' || label.trim() === '' || label.length > MAX_BOOKING_LABEL_CHARS) {
    throw new SupportAgentError('invalid_config', `booking.label must be a non-empty string of at most ${MAX_BOOKING_LABEL_CHARS} characters`);
  }
  return { url: url as string, label };
}

function resolveSuggestions(suggestions: unknown): ResolvedConfig['suggestions'] {
  if (suggestions === undefined || suggestions === false) return null;
  if (suggestions === true) return { max: DEFAULT_SUGGESTIONS_MAX };
  if (!isPlainObject(suggestions)) {
    throw new SupportAgentError('invalid_config', 'suggestions must be a boolean or an object');
  }
  const max = suggestions.max === undefined ? DEFAULT_SUGGESTIONS_MAX : suggestions.max;
  if (typeof max !== 'number' || !Number.isInteger(max) || max < 1 || max > MAX_SUGGESTIONS) {
    throw new SupportAgentError('invalid_config', `suggestions.max must be an integer from 1 to ${MAX_SUGGESTIONS}`);
  }
  return { max };
}

/** Apply defaults and validate. Throws SupportAgentError('invalid_config') naming the field, never a value. */
export function resolveConfig(config: SupportAgentConfig): ResolvedConfig {
  const models = resolveModels(config.model);
  const defaultHeaders = resolveDefaultHeaders(config.defaultHeaders);
  const booking = resolveBooking(config.booking);
  const suggestions = resolveSuggestions(config.suggestions);

  let client = config.client;
  if (!client) {
    if (!config.apiKey || typeof config.apiKey !== 'string' || !config.apiKey.startsWith('sk-nrouter-')) {
      throw new SupportAgentError('invalid_config', 'apiKey is required and must start with sk-nrouter-');
    }
    client = createClient(config.apiKey, config.baseURL, defaultHeaders);
  }

  if (!config.knowledge) {
    throw new SupportAgentError('invalid_config', 'knowledge is required');
  }

  let store: KnowledgeStore;
  if (isKnowledgeIndex(config.knowledge)) {
    store = createMemoryKnowledgeStore(config.knowledge);
  } else {
    store = config.knowledge;
  }

  if (typeof store.search !== 'function' || !store.embeddingModel || typeof store.embeddingModel !== 'string' || !Number.isInteger(store.dimensions) || store.dimensions <= 0) {
    throw new SupportAgentError('invalid_config', 'invalid knowledge store shape');
  }

  const limits = { ...DEFAULT_LIMITS, ...config.limits };
  if (!Number.isInteger(limits.maxMessages) || limits.maxMessages <= 0) {
    throw new SupportAgentError('invalid_config', 'limits.maxMessages must be a positive integer');
  }
  if (!Number.isInteger(limits.maxMessageChars) || limits.maxMessageChars <= 0) {
    throw new SupportAgentError('invalid_config', 'limits.maxMessageChars must be a positive integer');
  }
  if (!Number.isInteger(limits.maxPageContextChars) || limits.maxPageContextChars <= 0) {
    throw new SupportAgentError('invalid_config', 'limits.maxPageContextChars must be a positive integer');
  }

  const confidence = { ...DEFAULT_CONFIDENCE, ...config.confidence };
  if (!Number.isFinite(confidence.high) || !Number.isFinite(confidence.medium)) {
    throw new SupportAgentError('invalid_config', 'confidence thresholds must be finite numbers');
  }
  if (confidence.medium <= 0 || confidence.high < confidence.medium || confidence.high > 1) {
    throw new SupportAgentError('invalid_config', 'confidence thresholds must satisfy 0 < medium <= high <= 1');
  }

  const topK = config.topK !== undefined ? config.topK : DEFAULT_TOP_K;
  if (!Number.isInteger(topK) || topK <= 0 || topK > 50) {
    throw new SupportAgentError('invalid_config', 'topK must be a positive integer <= 50');
  }

  const maxTokens = config.maxTokens !== undefined ? config.maxTokens : DEFAULT_MAX_TOKENS;
  if (!Number.isInteger(maxTokens) || maxTokens <= 0) {
    throw new SupportAgentError('invalid_config', 'maxTokens must be a positive integer');
  }

  const maxToolSteps = config.maxToolSteps !== undefined ? config.maxToolSteps : DEFAULT_MAX_TOOL_STEPS;
  if (!Number.isInteger(maxToolSteps) || maxToolSteps <= 0) {
    throw new SupportAgentError('invalid_config', 'maxToolSteps must be a positive integer');
  }

  if (config.maskPii !== undefined && typeof config.maskPii !== 'boolean') {
    throw new SupportAgentError('invalid_config', 'maskPii must be a boolean');
  }
  const maskPii = config.maskPii !== false;

  return {
    client,
    models,
    booking,
    suggestions,
    store,
    agentName: config.agentName ?? DEFAULT_AGENT_NAME,
    instructions: config.instructions ?? '',
    topK,
    maxTokens,
    confidence,
    limits,
    tools: config.tools ?? [],
    maxToolSteps,
    webSearch: config.webSearch === false || config.webSearch === undefined ? null : config.webSearch,
    memoryStore: config.memoryStore ?? null,
    hooks: config.hooks ?? {},
    maskPii,
  };
}
