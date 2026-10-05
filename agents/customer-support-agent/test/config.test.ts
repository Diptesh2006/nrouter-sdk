import { describe, it, expect } from 'vitest';
import { resolveConfig, DEFAULT_LIMITS, DEFAULT_CONFIDENCE } from '../src/config.js';
import { SupportAgentError } from '../src/errors.js';
import type { SupportAgentConfig, KnowledgeStore, KnowledgeIndex } from '../src/types.js';

describe('resolveConfig', () => {
  const dummyKnowledgeStore: KnowledgeStore = {
    embeddingModel: 'test',
    dimensions: 10,
    search: async () => []
  };

  const dummyKnowledgeIndex: KnowledgeIndex = {
    version: 1,
    embeddingModel: 'test',
    dimensions: 10,
    createdAt: new Date().toISOString(),
    chunks: []
  };

  const validBaseConfig: SupportAgentConfig = {
    model: 'claude-haiku',
    apiKey: 'sk-nrouter-test',
    knowledge: dummyKnowledgeStore
  };

  it('resolves valid config with defaults', () => {
    const resolved = resolveConfig(validBaseConfig);
    expect(resolved.models).toEqual(['claude-haiku']);
    expect(resolved.agentName).toBe('Support');
    expect(resolved.limits).toEqual(DEFAULT_LIMITS);
    expect(resolved.confidence).toEqual(DEFAULT_CONFIDENCE);
    expect(resolved.store).toBe(dummyKnowledgeStore);
    expect(resolved.client).toBeDefined();
  });

  it('rejects missing model', () => {
    expect(() => resolveConfig({ ...validBaseConfig, model: '' })).toThrowError(SupportAgentError);
  });

  it('rejects missing knowledge', () => {
    const cfg = { ...validBaseConfig } as any;
    delete cfg.knowledge;
    expect(() => resolveConfig(cfg)).toThrowError(SupportAgentError);
  });

  it('rejects missing apiKey when client not provided', () => {
    const cfg = { ...validBaseConfig } as any;
    delete cfg.apiKey;
    expect(() => resolveConfig(cfg)).toThrowError(SupportAgentError);
  });

  it('rejects apiKey not starting with sk-nrouter-', () => {
    expect(() => resolveConfig({ ...validBaseConfig, apiKey: 'sk-other-key' })).toThrowError(SupportAgentError);
  });

  it('accepts config without apiKey if client is provided', () => {
    const dummyClient = {} as any;
    const resolved = resolveConfig({ model: 'test', knowledge: dummyKnowledgeStore, client: dummyClient });
    expect(resolved.client).toBe(dummyClient);
  });

  it('converts knowledge index to store', () => {
    const resolved = resolveConfig({ ...validBaseConfig, knowledge: dummyKnowledgeIndex });
    expect(resolved.store).toBeDefined();
    expect(typeof resolved.store.search).toBe('function');
  });

  it('merges limits and confidence', () => {
    const resolved = resolveConfig({
      ...validBaseConfig,
      limits: { maxMessages: 50 },
      confidence: { high: 0.8 }
    });
    expect(resolved.limits.maxMessages).toBe(50);
    expect(resolved.limits.maxMessageChars).toBe(DEFAULT_LIMITS.maxMessageChars);
    expect(resolved.confidence.high).toBe(0.8);
    expect(resolved.confidence.medium).toBe(DEFAULT_CONFIDENCE.medium);
  });

  it('validates limits numbers', () => {
    expect(() => resolveConfig({ ...validBaseConfig, limits: { maxMessages: 0 } })).toThrowError(SupportAgentError);
    expect(() => resolveConfig({ ...validBaseConfig, limits: { maxMessageChars: -1 } })).toThrowError(SupportAgentError);
    expect(() => resolveConfig({ ...validBaseConfig, limits: { maxMessages: 1.5 } })).toThrowError(SupportAgentError);
  });

  it('validates confidence numbers', () => {
    expect(() => resolveConfig({ ...validBaseConfig, confidence: { high: 1.5 } })).toThrowError(SupportAgentError);
    expect(() => resolveConfig({ ...validBaseConfig, confidence: { medium: 0 } })).toThrowError(SupportAgentError);
    expect(() => resolveConfig({ ...validBaseConfig, confidence: { high: 0.3, medium: 0.4 } })).toThrowError(SupportAgentError);
  });

  it('handles webSearch false/undefined', () => {
    let resolved = resolveConfig({ ...validBaseConfig, webSearch: false });
    expect(resolved.webSearch).toBeNull();
    
    resolved = resolveConfig({ ...validBaseConfig, webSearch: undefined });
    expect(resolved.webSearch).toBeNull();
    
    const ws = { label: 'test', search: async () => [] };
    resolved = resolveConfig({ ...validBaseConfig, webSearch: ws });
    expect(resolved.webSearch).toBe(ws);
  });

  // NEW TESTS FOR CONFIG VALIDATION
  it('validates topK is between 1 and 50', () => {
    expect(() => resolveConfig({ ...validBaseConfig, topK: 51 })).toThrowError(/topK/);
    expect(() => resolveConfig({ ...validBaseConfig, topK: 0 })).toThrowError(/topK/);
    const resolved = resolveConfig({ ...validBaseConfig, topK: 50 });
    expect(resolved.topK).toBe(50);
  });

  it('validates KnowledgeStore shape', () => {
    // Missing search
    expect(() => resolveConfig({ ...validBaseConfig, knowledge: { embeddingModel: 'a', dimensions: 10 } as any })).toThrowError(/knowledge/);
    // Bad search
    expect(() => resolveConfig({ ...validBaseConfig, knowledge: { embeddingModel: 'a', dimensions: 10, search: 'not-a-func' } as any })).toThrowError(/knowledge/);
    // Bad model
    expect(() => resolveConfig({ ...validBaseConfig, knowledge: { embeddingModel: '', dimensions: 10, search: async () => [] } })).toThrowError(/knowledge/);
    // Bad dimensions
    expect(() => resolveConfig({ ...validBaseConfig, knowledge: { embeddingModel: 'a', dimensions: -1, search: async () => [] } })).toThrowError(/knowledge/);
    expect(() => resolveConfig({ ...validBaseConfig, knowledge: { embeddingModel: 'a', dimensions: 1.5, search: async () => [] } })).toThrowError(/knowledge/);
  });

  it('resolves maskPii default true and respects false', () => {
    const resDefault = resolveConfig(validBaseConfig);
    expect(resDefault.maskPii).toBe(true);

    const resFalse = resolveConfig({ ...validBaseConfig, maskPii: false });
    expect(resFalse.maskPii).toBe(false);

    const resTrue = resolveConfig({ ...validBaseConfig, maskPii: true });
    expect(resTrue.maskPii).toBe(true);
  });

  it('validates maskPii is a boolean when provided', () => {
    expect(() => resolveConfig({ ...validBaseConfig, maskPii: 'yes' as any })).toThrowError(SupportAgentError);
  });

  describe('model list', () => {
    it('resolves a single model id to a one-entry list', () => {
      expect(resolveConfig(validBaseConfig).models).toEqual(['claude-haiku']);
    });

    it('keeps list order and removes duplicates', () => {
      const resolved = resolveConfig({ ...validBaseConfig, model: ['a', 'b', 'a'] });
      expect(resolved.models).toEqual(['a', 'b']);
    });

    it('rejects an empty list, blank entries and non-strings', () => {
      expect(() => resolveConfig({ ...validBaseConfig, model: [] })).toThrowError(/model/);
      expect(() => resolveConfig({ ...validBaseConfig, model: ['a', ''] })).toThrowError(/model/);
      expect(() => resolveConfig({ ...validBaseConfig, model: ['a', '   '] })).toThrowError(/model/);
      expect(() => resolveConfig({ ...validBaseConfig, model: ['a', 7 as any] })).toThrowError(/model/);
      expect(() => resolveConfig({ ...validBaseConfig, model: 7 as any })).toThrowError(/model/);
    });

    it('rejects more than three distinct models', () => {
      expect(resolveConfig({ ...validBaseConfig, model: ['a', 'b', 'c'] }).models).toHaveLength(3);
      expect(resolveConfig({ ...validBaseConfig, model: ['a', 'b', 'c', 'a'] }).models).toHaveLength(3);
      expect(() => resolveConfig({ ...validBaseConfig, model: ['a', 'b', 'c', 'd'] })).toThrowError(/model/);
    });
  });

  describe('defaultHeaders', () => {
    it('passes headers through to the created client and sets none by default', () => {
      const withHeaders = resolveConfig({ ...validBaseConfig, defaultHeaders: { 'x-team': 'support' } });
      expect((withHeaders.client as any).nrouterOptions.defaultHeaders).toEqual({ 'x-team': 'support' });

      const without = resolveConfig(validBaseConfig);
      expect((without.client as any).nrouterOptions.defaultHeaders).toBeUndefined();
    });

    it('rejects a non-object or non-string header values without echoing them', () => {
      expect(() => resolveConfig({ ...validBaseConfig, defaultHeaders: 'x' as any })).toThrowError(/defaultHeaders/);
      expect(() => resolveConfig({ ...validBaseConfig, defaultHeaders: ['x'] as any })).toThrowError(/defaultHeaders/);
      let message = '';
      try {
        resolveConfig({ ...validBaseConfig, defaultHeaders: { 'x-secret': 12345678 as any } });
      } catch (err) {
        message = (err as Error).message;
      }
      expect(message).toMatch(/defaultHeaders/);
      expect(message).not.toContain('12345678');
    });
  });

  describe('booking', () => {
    it('is null by default', () => {
      expect(resolveConfig(validBaseConfig).booking).toBeNull();
    });

    it('resolves the url and the default label', () => {
      const resolved = resolveConfig({ ...validBaseConfig, booking: { url: 'https://example.com/book' } });
      expect(resolved.booking).toEqual({ url: 'https://example.com/book', label: 'Book a meeting' });
    });

    it('keeps a custom label', () => {
      const resolved = resolveConfig({ ...validBaseConfig, booking: { url: 'https://example.com/book', label: 'Talk to us' } });
      expect(resolved.booking).toEqual({ url: 'https://example.com/book', label: 'Talk to us' });
    });

    it('rejects a url that is not https, naming the field and never the value', () => {
      for (const url of ['http://example.com/book', 'javascript:alert(1)', 'not a url', '', '//example.com']) {
        let message = '';
        try {
          resolveConfig({ ...validBaseConfig, booking: { url } });
        } catch (err) {
          expect(err).toBeInstanceOf(SupportAgentError);
          expect((err as SupportAgentError).code).toBe('invalid_config');
          message = (err as Error).message;
        }
        expect(message).toMatch(/booking\.url/);
        if (url) expect(message).not.toContain(url);
      }
      expect(() => resolveConfig({ ...validBaseConfig, booking: { url: 42 as any } })).toThrowError(/booking\.url/);
      expect(() => resolveConfig({ ...validBaseConfig, booking: 'https://example.com' as any })).toThrowError(/booking/);
    });

    it('caps the url at 2048 characters', () => {
      const base = 'https://example.com/';
      const ok = base + 'a'.repeat(2048 - base.length);
      expect(resolveConfig({ ...validBaseConfig, booking: { url: ok } }).booking?.url).toBe(ok);
      expect(() => resolveConfig({ ...validBaseConfig, booking: { url: ok + 'a' } })).toThrowError(/booking\.url/);
    });

    it('caps the label at 60 characters and rejects an empty or non-string label', () => {
      const url = 'https://example.com/book';
      expect(resolveConfig({ ...validBaseConfig, booking: { url, label: 'a'.repeat(60) } }).booking?.label).toHaveLength(60);
      expect(() => resolveConfig({ ...validBaseConfig, booking: { url, label: 'a'.repeat(61) } })).toThrowError(/booking\.label/);
      expect(() => resolveConfig({ ...validBaseConfig, booking: { url, label: '  ' } })).toThrowError(/booking\.label/);
      expect(() => resolveConfig({ ...validBaseConfig, booking: { url, label: 5 as any } })).toThrowError(/booking\.label/);
    });
  });

  describe('suggestions', () => {
    it('is off by default and when false', () => {
      expect(resolveConfig(validBaseConfig).suggestions).toBeNull();
      expect(resolveConfig({ ...validBaseConfig, suggestions: false }).suggestions).toBeNull();
    });

    it('defaults max to 3', () => {
      expect(resolveConfig({ ...validBaseConfig, suggestions: true }).suggestions).toEqual({ max: 3 });
      expect(resolveConfig({ ...validBaseConfig, suggestions: {} }).suggestions).toEqual({ max: 3 });
    });

    it('accepts max from 1 to 5 and rejects anything else', () => {
      expect(resolveConfig({ ...validBaseConfig, suggestions: { max: 1 } }).suggestions).toEqual({ max: 1 });
      expect(resolveConfig({ ...validBaseConfig, suggestions: { max: 5 } }).suggestions).toEqual({ max: 5 });
      expect(() => resolveConfig({ ...validBaseConfig, suggestions: { max: 0 } })).toThrowError(/suggestions\.max/);
      expect(() => resolveConfig({ ...validBaseConfig, suggestions: { max: 6 } })).toThrowError(/suggestions\.max/);
      expect(() => resolveConfig({ ...validBaseConfig, suggestions: { max: 2.5 } })).toThrowError(/suggestions\.max/);
      expect(() => resolveConfig({ ...validBaseConfig, suggestions: 'yes' as any })).toThrowError(/suggestions/);
    });
  });
});

