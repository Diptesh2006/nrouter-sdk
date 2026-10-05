import { describe, it, expect } from 'vitest';
import { encodeEvent, toSSE } from '../src/sse.js';
import type { AgentEvent } from '../src/types.js';

describe('encodeEvent', () => {
  it('encodes tool_call', () => {
    const ev: AgentEvent = { type: 'tool_call', tool: 'myTool', title: 'Running tool', status: 'running' };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"tool_call","tool":"myTool","title":"Running tool","status":"running"}\n\n');
  });

  it('encodes confidence', () => {
    const ev: AgentEvent = { type: 'confidence', level: 'high', score: 0.9, webSearched: false };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"confidence","level":"high","score":0.9,"webSearched":false}\n\n');
  });

  it('encodes citations', () => {
    const ev: AgentEvent = { type: 'citations', citations: [{ title: 'Doc', url: 'https://example.com' }] };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"citations","citations":[{"title":"Doc","url":"https://example.com"}]}\n\n');
  });

  it('encodes token', () => {
    const ev: AgentEvent = { type: 'token', text: 'hello' };
    expect(encodeEvent(ev)).toBe('data: {"choices":[{"delta":{"content":"hello"}}]}\n\n');
  });

  it('encodes cost exact', () => {
    const ev: AgentEvent = { type: 'cost', costUsd: 0.05, status: 'exact' };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"cost","costUsd":0.05,"status":"exact"}\n\n');
  });

  it('encodes cost exact with requestId', () => {
    const ev: AgentEvent = { type: 'cost', costUsd: 0.05, status: 'exact', requestId: 'req123' };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"cost","costUsd":0.05,"status":"exact","requestId":"req123"}\n\n');
  });

  it('encodes cost unpriced (no costUsd)', () => {
    const ev: AgentEvent = { type: 'cost', costUsd: null, status: 'unpriced' };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"cost","status":"unpriced"}\n\n');
  });

  it('encodes cost unpriced with requestId', () => {
    const ev: AgentEvent = { type: 'cost', costUsd: null, status: 'unpriced', requestId: 'req123' };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"cost","status":"unpriced","requestId":"req123"}\n\n');
  });

  it('encodes error', () => {
    const ev: AgentEvent = { type: 'error', code: 'internal_error', message: 'failed' };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"error","code":"internal_error","message":"failed"}\n\n');
  });

  it('encodes a book_meeting action', () => {
    const ev: AgentEvent = { type: 'action', action: 'book_meeting', url: 'https://example.com/book', label: 'Book a meeting' };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"action","action":"book_meeting","url":"https://example.com/book","label":"Book a meeting"}\n\n');
  });

  it('encodes suggestions', () => {
    const ev: AgentEvent = { type: 'suggestions', questions: ['Tell me about Pricing', 'How do keys work?'] };
    expect(encodeEvent(ev)).toBe('data: {"nrouter_event":"suggestions","questions":["Tell me about Pricing","How do keys work?"]}\n\n');
  });

  it('encodes done', () => {
    const ev: AgentEvent = { type: 'done' };
    expect(encodeEvent(ev)).toBe('data: [DONE]\n\n');
  });
});

describe('toSSE', () => {
  it('emits events and a single [DONE] if source does not end with done', async () => {
    async function* source() {
      yield { type: 'token', text: 'hi' } as AgentEvent;
    }
    const stream = toSSE(source());
    const reader = stream.getReader();
    const decoder = new TextDecoder();

    let res = await reader.read();
    expect(decoder.decode(res.value)).toBe('data: {"choices":[{"delta":{"content":"hi"}}]}\n\n');

    res = await reader.read();
    expect(decoder.decode(res.value)).toBe('data: [DONE]\n\n');

    res = await reader.read();
    expect(res.done).toBe(true);
  });

  it('does not emit a second [DONE] if source emits done', async () => {
    async function* source() {
      yield { type: 'done' } as AgentEvent;
    }
    const stream = toSSE(source());
    const reader = stream.getReader();
    const decoder = new TextDecoder();

    let res = await reader.read();
    expect(decoder.decode(res.value)).toBe('data: [DONE]\n\n');

    res = await reader.read();
    expect(res.done).toBe(true);
  });

  it('emits error then [DONE] if source throws', async () => {
    async function* source() {
      yield { type: 'token', text: 'hi' } as AgentEvent;
      throw new Error('boom');
    }
    const stream = toSSE(source());
    const reader = stream.getReader();
    const decoder = new TextDecoder();

    let res = await reader.read();
    expect(decoder.decode(res.value)).toBe('data: {"choices":[{"delta":{"content":"hi"}}]}\n\n');

    res = await reader.read();
    expect(decoder.decode(res.value)).toBe('data: {"nrouter_event":"error","code":"internal_error","message":"Internal error"}\n\n');

    res = await reader.read();
    expect(decoder.decode(res.value)).toBe('data: [DONE]\n\n');

    res = await reader.read();
    expect(res.done).toBe(true);
  });

  it('calls abort and return on cancel', async () => {
    let returned = false;
    const iterator = {
      async next() { return { done: false, value: { type: 'token', text: 'hi' } as AgentEvent }; },
      async return() { returned = true; return { done: true, value: undefined }; }
    };
    const iterable = { [Symbol.asyncIterator]: () => iterator };
    const abort = new AbortController();
    
    const stream = toSSE(iterable as any, abort);
    const reader = stream.getReader();
    await reader.cancel();
    
    expect(abort.signal.aborted).toBe(true);
    expect(returned).toBe(true);
  });
});
