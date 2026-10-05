// Shared contracts for @nrouter_ai/support-agent.
//
// Every module implements against these types. Changing a shape here changes
// every module that uses it, so it is changed deliberately, never in passing.

import type { AgentTool, MemoryStore, nRouter } from '@nrouter_ai/sdk';

// ---------------------------------------------------------------------------
// Knowledge
// ---------------------------------------------------------------------------

/** A source document before chunking. */
export interface SourceDoc {
  title: string;
  url: string;
  content: string;
  /** Optional entitlement tags; a chunk with none is visible to every audience. */
  audiences?: string[];
}

/** One embedded chunk of a source document. */
export interface KnowledgeChunk {
  /** Stable id: derived from url + chunk position, identical across rebuilds. */
  id: string;
  title: string;
  url: string;
  content: string;
  audiences?: string[];
  embedding: number[];
}

/** The versioned, serialisable knowledge index. */
export interface KnowledgeIndex {
  version: 1;
  embeddingModel: string;
  dimensions: number;
  /** ISO-8601 timestamp of the build. */
  createdAt: string;
  chunks: KnowledgeChunk[];
}

/** A search hit. The embedding is never returned to callers. */
export interface ScoredChunk {
  id: string;
  title: string;
  url: string;
  content: string;
  audiences?: string[];
  /** Cosine similarity in [-1, 1]. */
  similarity: number;
}

export interface SearchOptions {
  topK: number;
  /** When set, only chunks with no audiences or an overlapping audience match. */
  audiences?: string[];
}

/** Where retrieval reads from. The package ships an in-memory implementation only. */
export interface KnowledgeStore {
  /** The embedding model and dimensions the store was built with. */
  readonly embeddingModel: string;
  readonly dimensions: number;
  search(queryEmbedding: number[], opts: SearchOptions): Promise<ScoredChunk[]>;
}

export interface BuildIndexOptions {
  docs: SourceDoc[];
  /** Embeddings are created through this client. */
  client: nRouter;
  embeddingModel?: string;
  dimensions?: number;
  /** Texts per embeddings request. */
  batchSize?: number;
  signal?: AbortSignal;
  /** Mask emails and phone numbers before text leaves the process (default true). */
  maskPii?: boolean;
  /**
   * When the gateway refuses a document's text under a guardrail: false (default)
   * fails the build naming every refused document; true leaves them out and
   * reports each through `onSkip`.
   */
  skipBlocked?: boolean;
  onSkip?(doc: { title: string; url: string; reason: string }): void;
}

// ---------------------------------------------------------------------------
// Web search (optional tool)
// ---------------------------------------------------------------------------

export interface WebSource {
  title: string;
  url: string;
  snippet: string;
}

/** A host-supplied search backend. The package ships none that needs its own key. */
export interface WebSearchProvider {
  /** Short label shown in the "Searched …" step, e.g. a domain. Never a secret. */
  readonly label: string;
  search(query: string, opts: { maxResults: number; signal?: AbortSignal }): Promise<WebSource[]>;
}

// ---------------------------------------------------------------------------
// Hooks — the host persists; the package stores nothing
// ---------------------------------------------------------------------------

export type ConfidenceLevel = 'high' | 'medium' | 'low';

export interface GapEvent {
  question: string;
  /** Lower-cased, whitespace-collapsed, punctuation-stripped question for grouping. */
  normalized: string;
  confidence: ConfidenceLevel;
  webSearched: boolean;
  sessionId?: string;
}

export type Rating = 'up' | 'down';

export interface FeedbackInput {
  sessionId: string;
  messageId: string;
  rating: Rating;
  question?: string;
  confidence?: ConfidenceLevel;
  webSearched?: boolean;
  reason?: string;
}

export interface CostEvent {
  /** USD when the gateway priced the call; null when unpriced. Never 0 for "unknown". */
  costUsd: number | null;
  status: 'exact' | 'unpriced';
  requestId?: string;
}

export interface ToolCallEvent {
  tool: string;
  title: string;
  status: 'running' | 'done' | 'error';
}

export interface SupportAgentHooks {
  onGap?(gap: GapEvent): void | Promise<void>;
  onFeedback?(fb: FeedbackInput): void | Promise<void>;
  onCost?(cost: CostEvent): void | Promise<void>;
  onToolCall?(ev: ToolCallEvent): void | Promise<void>;
  /** Receives errors from other hooks and non-fatal internal failures. Must not throw. */
  onError?(err: SafeError): void;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** A redacted error safe to show a user or log. Never contains the API key. */
export interface SafeError {
  code: SupportAgentErrorCode;
  message: string;
}

export type SupportAgentErrorCode =
  | 'invalid_config'
  | 'invalid_request'
  | 'invalid_index'
  | 'auth_failed'
  | 'insufficient_credit'
  | 'rate_limited'
  | 'guardrail_blocked'
  | 'upstream_error'
  | 'aborted'
  | 'internal_error';

// ---------------------------------------------------------------------------
// Config and requests
// ---------------------------------------------------------------------------

export interface PayloadLimits {
  /** Max messages per request (default 12). */
  maxMessages: number;
  /** Max characters per message (default 2000). */
  maxMessageChars: number;
  /** Max characters of page context (default 1000). */
  maxPageContextChars: number;
}

export interface ConfidenceThresholds {
  /** Top similarity at or above this is "high" (default 0.55). */
  high: number;
  /** Top similarity at or above this is "medium" (default 0.40); below is "low". */
  medium: number;
}

export interface SupportAgentConfig {
  /** nRouter virtual key (sk-nrouter-…). Required unless `client` is supplied. */
  apiKey?: string;
  /** Override the gateway base URL (defaults to the SDK's). */
  baseURL?: string;
  /** Injected SDK client — tests and hosts that already hold one. */
  client?: nRouter;
  /** One model id, or an ordered list. The first is the primary; later entries are fallbacks. */
  model: string | string[];
  /** Extra headers sent on every gateway call. No default. Ignored when `client` is supplied. */
  defaultHeaders?: Record<string, string>;
  /** Offer a booking link. The URL comes only from here; the model never sees or produces it. */
  booking?: { url: string; label?: string };
  /** Emit related follow-up questions after an answer. Default off. */
  suggestions?: boolean | { max?: number };
  knowledge: KnowledgeStore | KnowledgeIndex;
  agentName?: string;
  /** Extra operator instructions appended to the built-in system prompt. */
  instructions?: string;
  topK?: number;
  maxTokens?: number;
  confidence?: Partial<ConfidenceThresholds>;
  limits?: Partial<PayloadLimits>;
  tools?: AgentTool[];
  maxToolSteps?: number;
  webSearch?: WebSearchProvider | false;
  /** Enables SDK conversation memory keyed by TrustedContext.sessionId. */
  memoryStore?: (sessionId: string) => MemoryStore;
  hooks?: SupportAgentHooks;
  /**
   * Mask emails and phone numbers in everything sent to the gateway (default
   * true). A key whose guardrail redacts PII refuses a prompt that carries any,
   * so an unmasked "my email is …" question would fail; retrieval and answers
   * never need the literal value.
   */
  maskPii?: boolean;
}

/** Config after defaults are applied and validation passed. */
export interface ResolvedConfig {
  client: nRouter;
  /** Non-empty, de-duplicated, at most three. `models[0]` is the primary. */
  models: string[];
  booking: { url: string; label: string } | null;
  suggestions: { max: number } | null;
  store: KnowledgeStore;
  agentName: string;
  instructions: string;
  topK: number;
  maxTokens: number;
  confidence: ConfidenceThresholds;
  limits: PayloadLimits;
  tools: AgentTool[];
  maxToolSteps: number;
  webSearch: WebSearchProvider | null;
  memoryStore: ((sessionId: string) => MemoryStore) | null;
  hooks: SupportAgentHooks;
  maskPii: boolean;
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface EndUserIdentity {
  name?: string;
  email?: string;
  plan?: string;
}

/**
 * What an end user may send. Everything here is UNTRUSTED: a host can forward
 * its request body as-is, so nothing in this shape may grant access.
 */
export interface ChatRequest {
  messages: ChatTurn[];
  pageContext?: string;
  signal?: AbortSignal;
}

/**
 * What only the host may decide, from its own authenticated session — never
 * from the request body. `audiences` gates knowledge, `sessionId` keys stored
 * history, so taking either from the caller would let one user read another's
 * gated docs or conversation. Audiences are entitlement tags, not a tenancy
 * boundary: separate organisations get separate indexes and agents.
 */
export interface TrustedContext {
  identity?: EndUserIdentity;
  audiences?: string[];
  sessionId?: string;
}

// ---------------------------------------------------------------------------
// Events — what chat() yields; sse.ts maps them to the widget wire format
// ---------------------------------------------------------------------------

export interface Citation {
  title: string;
  url: string;
}

export type AgentEvent =
  | { type: 'tool_call'; tool: string; title: string; status: 'running' | 'done' | 'error' }
  | { type: 'confidence'; level: ConfidenceLevel; score: number; webSearched: boolean }
  | { type: 'citations'; citations: Citation[] }
  | { type: 'token'; text: string }
  | { type: 'suggestions'; questions: string[] }
  | { type: 'action'; action: 'book_meeting'; url: string; label: string }
  | { type: 'cost'; costUsd: number | null; status: 'exact' | 'unpriced'; requestId?: string }
  | { type: 'error'; code: SupportAgentErrorCode; message: string }
  | { type: 'done' };

export interface SupportAgent {
  /** `req` is validated as untrusted input; `ctx` comes from the host's auth, never the body. */
  chat(req: unknown, ctx?: TrustedContext): AsyncIterable<AgentEvent>;
  chatSSE(req: unknown, ctx?: TrustedContext): ReadableStream<Uint8Array>;
  feedback(fb: unknown): Promise<void>;
}
