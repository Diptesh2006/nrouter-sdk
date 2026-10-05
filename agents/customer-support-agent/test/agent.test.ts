import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createSupportAgent } from '../src/agent.js';
import type { nRouter } from '@nrouter_ai/sdk';
import { nRouterGuardrailBlockedError, classifyError } from '@nrouter_ai/sdk';
import { SupportAgentError } from '../src/errors.js';

vi.mock('../src/retrieval.js', () => ({ retrieve: vi.fn().mockResolvedValue([]) }));
vi.mock('../src/confidence.js', () => ({ scoreConfidence: vi.fn().mockReturnValue({ level: 'high', score: 0.9 }) }));
vi.mock('../src/prompt.js', () => ({ buildCitations: vi.fn().mockReturnValue([]), buildSystemPrompt: vi.fn().mockReturnValue('sys') }));
vi.mock('../src/page-context.js', () => ({ sanitizePageContext: vi.fn().mockReturnValue(null) }));
vi.mock('../src/gaps.js', () => ({ latestQuestion: vi.fn().mockReturnValue('Q'), normalizeQuestion: vi.fn().mockReturnValue('q') }));
vi.mock('../src/tools.js', () => ({ runToolPhase: vi.fn().mockImplementation(async (c, m, e) => ({ messages: m, ranTools: false })) }));
vi.mock('../src/web-search.js', () => ({ runWebSearch: vi.fn().mockResolvedValue([]) }));
vi.mock('../src/client.js', () => ({
  createClient: vi.fn(),
  streamChat: vi.fn().mockImplementation(async (client, opts) => {
    const res = await client.nr.stream(opts);
    return { cost: res.meta.cost as any, chunks: res.chunks as any };
  })
}));
vi.mock('../src/hooks.js', () => ({ callHook: vi.fn() }));
vi.mock('../src/sse.js', () => ({
  toSSE: vi.fn().mockReturnValue(new ReadableStream({
    start(c) { c.enqueue(new TextEncoder().encode('[DONE]')); c.close(); }
  }))
}));
vi.mock('../src/feedback.js', () => ({ validateFeedback: vi.fn().mockReturnValue({ rating: 'up' }) }));

describe('SupportAgent', () => {
  let fakeClient: nRouter;
  let streamGenerator: any;
  const fakeIndex = { version: 1 as const, embeddingModel: 't', dimensions: 2, createdAt: '2026', chunks: [] };

  beforeEach(() => {
    vi.clearAllMocks();
    streamGenerator = async function* () {
      yield 'token1';
      yield 'token2';
    };
    fakeClient = {
      nr: {
        stream: vi.fn().mockImplementation(async () => {
          return { meta: { cost: { costUsd: 0.05, status: 'exact' } }, chunks: streamGenerator() };
        })
      },
      embeddings: {
        create: vi.fn().mockResolvedValue({ data: [{ embedding: [1, 0] }] })
      }
    } as unknown as nRouter;
  });

  it('event ORDER (confidence, citations, tokens, cost, done)', async () => {
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'high', score: 0.9 });
    
    const { buildCitations } = await import('../src/prompt.js');
    vi.mocked(buildCitations).mockReturnValue([{ title: 'Doc', url: 'http' }]);

    const agent = createSupportAgent({ client: fakeClient, model: 'm', knowledge: fakeIndex });
    const events = [];
    for await (const ev of agent.chat({ messages: [{ role: 'user', content: 'hi' }] })) {
      events.push(ev);
    }
    
    expect(events.map(e => e.type)).toEqual(['confidence', 'citations', 'token', 'token', 'cost', 'done']);
    expect(events[0]).toMatchObject({ level: 'high', score: 0.9, webSearched: false });
    expect(events[1]).toMatchObject({ citations: [{ title: 'Doc', url: 'http' }] });
    expect(events[2]).toMatchObject({ text: 'token1' });
  });

  it('low confidence → onGap called, web search path', async () => {
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'low', score: 0.1 });
    const { callHook } = await import('../src/hooks.js');

    const agent = createSupportAgent({ 
      client: fakeClient, 
      model: 'm', 
      knowledge: fakeIndex,
      webSearch: { label: 'Google', search: vi.fn() },
      hooks: { onGap: vi.fn() }
    });
    
    const events = [];
    for await (const ev of agent.chat({ messages: [{ role: 'user', content: 'hi' }] })) {
      events.push(ev);
    }
    
    const types = events.map(e => e.type);
    expect(types).toContain('tool_call');
    expect(events.find(e => e.type === 'tool_call' && e.status === 'running')).toBeDefined();
    
    expect(callHook).toHaveBeenCalledWith(expect.anything(), 'onGap', expect.objectContaining({ confidence: 'low', webSearched: true }));
  });

  it('guardrail retry once', async () => {
    const { streamChat } = await import('../src/client.js');
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'low', score: 0.1 });
    
    let calls = 0;
    vi.mocked(streamChat).mockImplementation(async (client, opts) => {
       calls++;
       if (calls === 1) throw new nRouterGuardrailBlockedError('blocked', {} as any);
       const chunks = async function*() { yield 'retry_ok'; }();
       return { cost: { costUsd: null, status: 'unpriced' }, chunks };
    });

    const agent = createSupportAgent({ 
      client: fakeClient, 
      model: 'm', 
      knowledge: fakeIndex,
      webSearch: { label: 'B', search: vi.fn() }
    });
    
    const events = [];
    for await (const ev of agent.chat({ messages: [{ role: 'user', content: 'hi' }] })) {
      events.push(ev);
    }
    
    expect(calls).toBe(2);
    expect(events.find(e => e.type === 'token' && e.text === 'retry_ok')).toBeDefined();
    expect(events.map(e => e.type)).toContain('done');
    expect(events.map(e => e.type)).not.toContain('error');
  });

  it('error event never contains the api key', async () => {
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockRejectedValue(new SupportAgentError('upstream_error', 'failed sk-nrouter-secret-key'));

    const agent = createSupportAgent({ 
      apiKey: 'sk-nrouter-secret-key',
      model: 'm', 
      knowledge: fakeIndex 
    });
    
    const events = [];
    for await (const ev of agent.chat({ messages: [{ role: 'user', content: 'hi' }] })) {
      events.push(ev);
    }
    
    const errEvent = events.find(e => e.type === 'error') as any;
    expect(errEvent).toBeDefined();
    expect(errEvent.message).not.toContain('sk-nrouter-secret-key');
    expect(errEvent.message).toContain('[redacted]');
  });

  it('abort → aborted + done', async () => {
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockImplementation(async () => {
       const err = new Error('abort');
       err.name = 'AbortError';
       throw err;
    });

    const agent = createSupportAgent({ client: fakeClient, model: 'm', knowledge: fakeIndex });
    
    const events = [];
    const ac = new AbortController();
    for await (const ev of agent.chat({ messages: [{ role: 'user', content: 'hi' }], signal: ac.signal })) {
      events.push(ev);
    }
    
    expect(events.map(e => e.type)).toEqual(['confidence', 'citations', 'error', 'done']);
    expect(events[2]).toMatchObject({ code: 'aborted' });
  });

  it('DOUBLE BILLED CALL: tools configured → exactly ONE model call (streamChat skipped)', async () => {
    const { runToolPhase } = await import('../src/tools.js');
    vi.mocked(runToolPhase).mockResolvedValue({
      messages: [{ role: 'assistant', content: 'tool answer' }] as any,
      ranTools: false,
      text: 'tool answer',
      cost: { costUsd: 0.1, status: 'exact' }
    });
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockClear();

    const agent = createSupportAgent({ 
      client: fakeClient, 
      model: 'm', 
      knowledge: fakeIndex,
      tools: [{ definition: { type: 'function', function: { name: 't1' } }, execute: vi.fn() }] as any
    });
    
    const events = [];
    for await (const ev of agent.chat({ messages: [{ role: 'user', content: 'hi' }] })) {
      events.push(ev);
    }
    
    expect(streamChat).not.toHaveBeenCalled();
    expect(events.find(e => e.type === 'token' && e.text === 'tool answer')).toBeDefined();
  });

  it('TRUSTED CONTEXT: req body with audiences must NOT unlock chunk; ctx.audiences must', async () => {
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockClear();
    
    const agent = createSupportAgent({ client: fakeClient, model: 'm', knowledge: fakeIndex });
    
    // Pass audiences in untrusted req body
    const reqWithAudiences = { messages: [{ role: 'user', content: 'hi' }], audiences: ['gated'] };
    for await (const ev of agent.chat(reqWithAudiences, {})) {
       // iterate
    }
    
    // The retrieve call should NOT have 'gated' in its audiences options
    expect(retrieve).toHaveBeenCalledWith(expect.anything(), expect.anything(), expect.objectContaining({ audiences: undefined, signal: undefined }));
    
    vi.mocked(retrieve).mockClear();
    
    // Pass audiences in trusted ctx
    for await (const ev of agent.chat({ messages: [{ role: 'user', content: 'hi' }] }, { audiences: ['gated'] })) {
       // iterate
    }
    
    // The retrieve call MUST have 'gated' in its audiences options
    expect(retrieve).toHaveBeenCalledWith(expect.anything(), expect.anything(), expect.objectContaining({ audiences: ['gated'] }));
  });

  it('chatSSE ends with [DONE]', async () => {
    const agent = createSupportAgent({ client: fakeClient, model: 'm', knowledge: fakeIndex });
    const stream = agent.chatSSE({ messages: [{ role: 'user', content: 'hi' }] });
    const reader = stream.getReader();
    const result = await reader.read();
    expect(new TextDecoder().decode(result.value)).toBe('[DONE]');
  });

  it('MEMORY DUPLICATION: two consecutive turns store holds exactly [user1, assistant1, user2, assistant2]', async () => {
    const { createArrayStore } = await import('@nrouter_ai/sdk');
    const store = createArrayStore();
    
    // We must unmock tools.js and client.js enough so it doesn't crash?
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockImplementation(async (client, opts) => {
      const res = await client.nr.stream(opts);
      return { cost: res.meta.cost as any, chunks: res.chunks as any };
    });
    const agent = createSupportAgent({ 
      client: fakeClient, 
      model: 'm', 
      knowledge: fakeIndex,
      memoryStore: () => store
    });
    
    // Turn 1
    const events1 = [];
    for await (const ev of agent.chat({ messages: [{ role: 'user', content: 'user1' }] }, { sessionId: 'session1' })) {
       events1.push(ev);
    }
    
    // Turn 2
    // A real client would send the full conversation, so messages is [user1, assistant1, user2].
    const events2 = [];
    for await (const ev of agent.chat({ 
       messages: [
         { role: 'user', content: 'user1' }, 
         { role: 'assistant', content: 'token1token2' }, 
         { role: 'user', content: 'user2' }
       ] 
    }, { sessionId: 'session1' })) {
       events2.push(ev);
    }
    console.log(JSON.stringify(events1));
    console.log(JSON.stringify(events2));
    const msgs = await store.load();
    expect(msgs.map(m => m.content)).toEqual(['user1', 'token1token2', 'user2', 'token1token2']);
  });

  it('PII MASKING: masks messages to runToolPhase and passes maskPii to streamChat', async () => {
    const { runToolPhase } = await import('../src/tools.js');
    let capturedToolMessages: any[] = [];
    vi.mocked(runToolPhase).mockImplementation(async (cfg, msgs, cb) => {
      capturedToolMessages = msgs;
      return { messages: msgs, ranTools: false };
    });

    const { streamChat } = await import('../src/client.js');
    let capturedStreamOpts: any = null;
    vi.mocked(streamChat).mockImplementation(async (client, opts) => {
      capturedStreamOpts = opts;
      async function* chunks() { yield 'answer'; }
      return { cost: { costUsd: null, status: 'unpriced' }, chunks: chunks() };
    });

    const agent = createSupportAgent({
      client: fakeClient,
      model: 'm',
      knowledge: fakeIndex,
      maskPii: true
    });

    for await (const _ of agent.chat({
      messages: [{ role: 'user', content: 'Contact me at admin@corp.com or 555-123-4567' }]
    })) {
      // iterate
    }

    // runToolPhase received masked messages
    const userMsgInTool = capturedToolMessages.find(m => m.role === 'user');
    expect(userMsgInTool?.content).toBe('Contact me at [email] or [phone]');

    // streamChat received maskPii: true
    expect(capturedStreamOpts.maskPii).toBe(true);
  });

  it('PII MASKING: masks multi-part array content in tool phase', async () => {
    const { runToolPhase } = await import('../src/tools.js');
    let capturedToolMessages: any[] = [];
    vi.mocked(runToolPhase).mockImplementation(async (cfg, msgs, cb) => {
      capturedToolMessages = msgs;
      return { messages: msgs, ranTools: false };
    });

    const { createArrayStore } = await import('@nrouter_ai/sdk');
    const store = createArrayStore([
      {
        role: 'user',
        content: [
          { type: 'text', text: 'my email is user@domain.com' },
          { type: 'image_url', image_url: { url: 'https://example.com/img.png' } }
        ] as any
      }
    ]);

    const agent = createSupportAgent({
      client: fakeClient,
      model: 'm',
      knowledge: fakeIndex,
      maskPii: true,
      memoryStore: () => store
    });

    for await (const _ of agent.chat({
      messages: [{ role: 'user', content: 'hello' }]
    }, { sessionId: 'sess-1' })) {
      // iterate
    }

    const userMsg = capturedToolMessages.find(m => Array.isArray(m.content));
    expect(userMsg?.content).toEqual([
      { type: 'text', text: 'my email is [email]' },
      { type: 'image_url', image_url: { url: 'https://example.com/img.png' } }
    ]);
  });
});

describe('SupportAgent: model fallback, booking action and suggestions', () => {
  const fakeIndex = { version: 1 as const, embeddingModel: 't', dimensions: 2, createdAt: '2026', chunks: [] };
  const fakeClient = { nr: {}, embeddings: {} } as unknown as nRouter;
  const user = (content: string) => ({ messages: [{ role: 'user', content }] });
  const tool = { definition: { type: 'function', function: { name: 't1' } }, execute: vi.fn() } as any;

  function answer(...tokens: string[]) {
    return {
      cost: { costUsd: 0.01, status: 'exact' as const },
      chunks: (async function* () { for (const t of tokens) yield t; })()
    };
  }

  async function collect(agent: ReturnType<typeof createSupportAgent>, req: unknown): Promise<any[]> {
    const events = [];
    for await (const ev of agent.chat(req)) events.push(ev);
    return events;
  }

  // Earlier tests leave implementations behind; pin every collaborator here.
  beforeEach(async () => {
    vi.clearAllMocks();
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockResolvedValue([]);
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'high', score: 0.9 });
    const { buildCitations } = await import('../src/prompt.js');
    vi.mocked(buildCitations).mockReturnValue([]);
    const { latestQuestion } = await import('../src/gaps.js');
    vi.mocked(latestQuestion).mockReturnValue('Q');
    const { runToolPhase } = await import('../src/tools.js');
    vi.mocked(runToolPhase).mockImplementation(async (c, m) => ({ messages: m, ranTools: false }));
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockImplementation(async () => answer('ok'));
  });

  it.each([
    ['503', () => classifyError(null, 'unavailable', 503)],
    ['404 model_not_found', () => classifyError('model_not_found', 'no such model', 404)],
  ])('falls back to the next model on %s before any token', async (_name, makeErr) => {
    const { streamChat } = await import('../src/client.js');
    const seen: string[] = [];
    vi.mocked(streamChat).mockImplementation(async (_client, opts) => {
      seen.push(opts.model);
      if (opts.model === 'a') throw makeErr();
      return answer('from-b');
    });

    const agent = createSupportAgent({ client: fakeClient, model: ['a', 'b'], knowledge: fakeIndex });
    const events = await collect(agent, user('hi'));

    expect(seen).toEqual(['a', 'b']);
    expect(events.map(e => e.type)).toEqual(['confidence', 'token', 'cost', 'done']);
    expect(events[1]).toEqual({ type: 'token', text: 'from-b' });
    expect(JSON.stringify(events)).not.toContain('"b"');
  });

  it.each([
    ['401', () => classifyError(null, 'bad key', 401), 'auth_failed'],
    ['403', () => classifyError(null, 'forbidden', 403), 'upstream_error'],
    ['402 credit', () => classifyError(null, 'insufficient credits', 402), 'insufficient_credit'],
    ['402 budget', () => classifyError(null, 'budget exceeded', 402), 'insufficient_credit'],
    ['429', () => classifyError(null, 'slow down', 429), 'rate_limited'],
    ['guardrail block', () => classifyError(null, 'request blocked by a guardrail', 400), 'guardrail_blocked'],
    ['abort', () => Object.assign(new Error('aborted'), { name: 'AbortError' }), 'aborted'],
  ])('never falls back on %s', async (_name, makeErr, code) => {
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockImplementation(async () => { throw makeErr(); });

    const agent = createSupportAgent({ client: fakeClient, model: ['a', 'b'], knowledge: fakeIndex });
    const events = await collect(agent, user('hi'));

    expect(streamChat).toHaveBeenCalledTimes(1);
    expect(events.map(e => e.type)).toEqual(['confidence', 'error', 'done']);
    expect(events[1].code).toBe(code);
  });

  it('never falls back once a token has been emitted', async () => {
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockImplementation(async () => ({
      cost: { costUsd: null, status: 'unpriced' as const },
      chunks: (async function* () {
        yield 'partial';
        throw classifyError(null, 'unavailable', 503);
      })()
    }));

    const agent = createSupportAgent({ client: fakeClient, model: ['a', 'b'], knowledge: fakeIndex });
    const events = await collect(agent, user('hi'));

    expect(streamChat).toHaveBeenCalledTimes(1);
    expect(events.map(e => e.type)).toEqual(['confidence', 'token', 'error', 'done']);
  });

  it('never falls back once a host tool has run', async () => {
    const { runToolPhase } = await import('../src/tools.js');
    vi.mocked(runToolPhase).mockImplementation(async (_c, _m, emit) => {
      emit({ tool: 't1', title: 't1', status: 'running' });
      throw classifyError(null, 'unavailable', 503);
    });

    const agent = createSupportAgent({ client: fakeClient, model: ['a', 'b'], knowledge: fakeIndex, tools: [tool] });
    const events = await collect(agent, user('hi'));

    expect(runToolPhase).toHaveBeenCalledTimes(1);
    expect(events.map(e => e.type)).toEqual(['confidence', 'error', 'done']);
  });

  it('runs the tool phase on the fallback model when the primary is refused before any tool ran', async () => {
    const { runToolPhase } = await import('../src/tools.js');
    const seen: unknown[] = [];
    vi.mocked(runToolPhase).mockImplementation(async (_c, m, _emit, _signal, model) => {
      seen.push(model);
      if (model === 'a') throw classifyError(null, 'unavailable', 503);
      return { messages: m, ranTools: false, text: 'tool answer', cost: { costUsd: 0.1, status: 'exact' } };
    });

    const agent = createSupportAgent({ client: fakeClient, model: ['a', 'b'], knowledge: fakeIndex, tools: [tool] });
    const events = await collect(agent, user('hi'));

    expect(seen).toEqual(['a', 'b']);
    expect(events.map(e => e.type)).toEqual(['confidence', 'token', 'cost', 'done']);
  });

  it('is bounded by the model list', async () => {
    const { streamChat } = await import('../src/client.js');
    const seen: string[] = [];
    vi.mocked(streamChat).mockImplementation(async (_client, opts) => {
      seen.push(opts.model);
      throw classifyError(null, 'unavailable', 503);
    });

    const agent = createSupportAgent({ client: fakeClient, model: ['a', 'b', 'c'], knowledge: fakeIndex });
    const events = await collect(agent, user('hi'));

    expect(seen).toEqual(['a', 'b', 'c']);
    expect(events.map(e => e.type)).toEqual(['confidence', 'error', 'done']);
    expect(events[1].code).toBe('upstream_error');
  });

  it('a single model never retries', async () => {
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockImplementation(async () => { throw classifyError(null, 'unavailable', 503); });

    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex });
    await collect(agent, user('hi'));

    expect(streamChat).toHaveBeenCalledTimes(1);
  });

  it('the guardrail retry stays on the model already fallen back to', async () => {
    const { streamChat } = await import('../src/client.js');
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'low', score: 0.1 });
    const seen: string[] = [];
    vi.mocked(streamChat).mockImplementation(async (_client, opts) => {
      seen.push(opts.model);
      if (seen.length === 1) throw classifyError(null, 'unavailable', 503);
      if (seen.length === 2) throw new nRouterGuardrailBlockedError('blocked', {} as any);
      return answer('retry_ok');
    });

    const agent = createSupportAgent({
      client: fakeClient, model: ['a', 'b'], knowledge: fakeIndex,
      webSearch: { label: 'B', search: vi.fn() }
    });
    const events = await collect(agent, user('hi'));

    expect(seen).toEqual(['a', 'b', 'b']);
    expect(events.find(e => e.type === 'token')).toEqual({ type: 'token', text: 'retry_ok' });
    expect(events.map(e => e.type)).not.toContain('error');
  });

  it('the guardrail retry does not replay an answer that already started streaming', async () => {
    const { streamChat } = await import('../src/client.js');
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'low', score: 0.1 });
    vi.mocked(streamChat).mockImplementation(async () => ({
      cost: { costUsd: null, status: 'unpriced' as const },
      chunks: (async function* () {
        yield 'partial';
        throw new nRouterGuardrailBlockedError('blocked', {} as any);
      })()
    }));

    const agent = createSupportAgent({
      client: fakeClient, model: 'a', knowledge: fakeIndex,
      webSearch: { label: 'B', search: vi.fn() }
    });
    const events = await collect(agent, user('hi'));

    expect(streamChat).toHaveBeenCalledTimes(1);
    expect(events.filter(e => e.type === 'token')).toHaveLength(1);
    expect(events.slice(-2).map(e => e.type)).toEqual(['error', 'done']);
    expect(events.at(-2).code).toBe('guardrail_blocked');
  });

  it('the guardrail retry does not run a host tool a second time', async () => {
    const { runToolPhase } = await import('../src/tools.js');
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'low', score: 0.1 });
    vi.mocked(runToolPhase).mockImplementation(async (_c, _m, emit) => {
      emit({ tool: 't1', title: 'T1', status: 'done' });
      throw new nRouterGuardrailBlockedError('blocked', {} as any);
    });

    const agent = createSupportAgent({
      client: fakeClient, model: 'a', knowledge: fakeIndex, tools: [tool],
      webSearch: { label: 'B', search: vi.fn() }
    });
    const events = await collect(agent, user('hi'));

    expect(runToolPhase).toHaveBeenCalledTimes(1);
    expect(events.slice(-2).map(e => e.type)).toEqual(['error', 'done']);
    expect(events.at(-2).code).toBe('guardrail_blocked');
  });

  const chunks = [
    { id: '1', title: 'Routing', url: 'https://example.com/routing', content: 'c', similarity: 0.9 },
    { id: '2', title: 'Pricing', url: 'https://example.com/pricing', content: 'c', similarity: 0.8 },
    { id: '3', title: 'API keys', url: 'https://example.com/keys', content: 'c', similarity: 0.7 },
  ];
  const booking = { url: 'https://example.com/book' };

  it('emits suggestions then the booking action after the tokens and before cost', async () => {
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockResolvedValue(chunks);
    const { latestQuestion } = await import('../src/gaps.js');
    vi.mocked(latestQuestion).mockReturnValue('Can I book a demo?');

    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, booking, suggestions: true });
    const events = await collect(agent, user('Can I book a demo?'));

    expect(events.map(e => e.type)).toEqual(['confidence', 'token', 'suggestions', 'action', 'cost', 'done']);
    expect(events[2]).toEqual({ type: 'suggestions', questions: ['Tell me about Pricing', 'Tell me about API keys'] });
    expect(events[3]).toEqual({ type: 'action', action: 'book_meeting', url: 'https://example.com/book', label: 'Book a meeting' });
  });

  it('makes no extra model call for either event', async () => {
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockResolvedValue(chunks);
    const { latestQuestion } = await import('../src/gaps.js');
    vi.mocked(latestQuestion).mockReturnValue('contact sales');
    const { streamChat } = await import('../src/client.js');
    const { runToolPhase } = await import('../src/tools.js');

    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, booking, suggestions: true });
    await collect(agent, user('contact sales'));

    expect(streamChat).toHaveBeenCalledTimes(1);
    expect(runToolPhase).toHaveBeenCalledTimes(1);
  });

  it('offers booking on low confidence even without booking intent', async () => {
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'low', score: 0.1 });

    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, booking: { ...booking, label: 'Talk to us' } });
    const events = await collect(agent, user('something obscure'));

    expect(events.find(e => e.type === 'action')).toEqual({
      type: 'action', action: 'book_meeting', url: 'https://example.com/book', label: 'Talk to us'
    });
  });

  it('does not offer booking without intent at medium or high confidence', async () => {
    const { latestQuestion } = await import('../src/gaps.js');
    vi.mocked(latestQuestion).mockReturnValue('is the demo key rate limited?');
    const { scoreConfidence } = await import('../src/confidence.js');
    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, booking });

    for (const level of ['high', 'medium'] as const) {
      vi.mocked(scoreConfidence).mockReturnValue({ level, score: 0.5 });
      const events = await collect(agent, user('is the demo key rate limited?'));
      expect(events.map(e => e.type)).not.toContain('action');
    }
  });

  it('emits neither event when not configured', async () => {
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockResolvedValue(chunks);
    const { latestQuestion } = await import('../src/gaps.js');
    vi.mocked(latestQuestion).mockReturnValue('book a demo');

    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex });
    const events = await collect(agent, user('book a demo'));

    expect(events.map(e => e.type)).toEqual(['confidence', 'token', 'cost', 'done']);
  });

  it('omits suggestions when there is no related topic', async () => {
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockResolvedValue(chunks.slice(0, 1));

    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, suggestions: true });
    const events = await collect(agent, user('hi'));

    expect(events.map(e => e.type)).not.toContain('suggestions');
  });

  it('caps suggestions at the configured max', async () => {
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockResolvedValue(chunks);

    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, suggestions: { max: 1 } });
    const events = await collect(agent, user('hi'));

    expect(events.find(e => e.type === 'suggestions')).toEqual({ type: 'suggestions', questions: ['Tell me about Pricing'] });
  });

  it('masks personal data in suggestions unless masking is turned off', async () => {
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockResolvedValue([
      chunks[0]!,
      { id: '9', title: 'Escalations to jane@example.com', url: 'https://example.com/e', content: 'c', similarity: 0.5 },
    ]);

    const masked = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, suggestions: true });
    const maskedEvents = await collect(masked, user('hi'));
    expect(maskedEvents.find(e => e.type === 'suggestions')).toEqual({
      type: 'suggestions', questions: ['Tell me about Escalations to [email]']
    });

    const raw = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, suggestions: true, maskPii: false });
    const rawEvents = await collect(raw, user('hi'));
    expect(rawEvents.find(e => e.type === 'suggestions')).toEqual({
      type: 'suggestions', questions: ['Tell me about Escalations to jane@example.com']
    });
  });

  it('emits neither event on an errored response', async () => {
    const { retrieve } = await import('../src/retrieval.js');
    vi.mocked(retrieve).mockResolvedValue(chunks);
    const { latestQuestion } = await import('../src/gaps.js');
    vi.mocked(latestQuestion).mockReturnValue('book a demo');
    const { scoreConfidence } = await import('../src/confidence.js');
    vi.mocked(scoreConfidence).mockReturnValue({ level: 'low', score: 0.1 });
    const { streamChat } = await import('../src/client.js');
    vi.mocked(streamChat).mockImplementation(async () => { throw classifyError(null, 'slow down', 429); });

    const agent = createSupportAgent({ client: fakeClient, model: 'a', knowledge: fakeIndex, booking, suggestions: true });
    const events = await collect(agent, user('book a demo'));

    expect(events.map(e => e.type)).toEqual(['confidence', 'error', 'done']);
  });
});



