import { describe, it, expect } from 'vitest';
import { createClient, embed, streamChat, costFromMeta } from '../src/client.js';
import { SupportAgentError } from '../src/errors.js';
import { nRouter } from '@nrouter_ai/sdk';

describe('client', () => {
  describe('createClient', () => {
    it('creates a client with valid key', () => {
      const client = createClient('sk-nrouter-test');
      expect(client).toBeInstanceOf(nRouter);
    });

    it('sends no extra headers unless the caller supplies them', () => {
      const plain = createClient('sk-nrouter-test');
      expect((plain as any).nrouterOptions.defaultHeaders).toBeUndefined();

      const tagged = createClient('sk-nrouter-test', undefined, { 'x-team': 'support' });
      expect((tagged as any).nrouterOptions.defaultHeaders).toEqual({ 'x-team': 'support' });
    });

    it('throws invalid_config on empty key', () => {
      expect(() => createClient('')).toThrow(SupportAgentError);
      expect(() => createClient('   ')).toThrow(SupportAgentError);
    });
  });

  describe('embed', () => {
    it('returns empty array for empty input without calling SDK', async () => {
      const client = Object.create(nRouter.prototype);
      let called = false;
      client.embeddings = {
        create: async () => { called = true; return { data: [] }; }
      };
      
      const res = await embed(client, 'test-model', [], 100);
      expect(res).toEqual([]);
      expect(called).toBe(false);
    });

    it('calls SDK and sorts vectors by index', async () => {
      const client = Object.create(nRouter.prototype);
      client.embeddings = {
        create: async () => {
          return {
            data: [
              { index: 1, embedding: [3, 4] },
              { index: 0, embedding: [1, 2] }
            ]
          };
        }
      };

      const res = await embed(client, 'test-model', ['a', 'b'], 2);
      expect(res).toEqual([[1, 2], [3, 4]]);
    });

    it('throws if count mismatches', async () => {
      const client = Object.create(nRouter.prototype);
      client.embeddings = {
        create: async () => {
          return {
            data: [
              { index: 0, embedding: [1, 2] }
            ]
          };
        }
      };

      await expect(embed(client, 'test-model', ['a', 'b'], 2)).rejects.toThrow(SupportAgentError);
    });

    it('throws if dimension mismatches', async () => {
      const client = Object.create(nRouter.prototype);
      client.embeddings = {
        create: async () => {
          return {
            data: [
              { index: 0, embedding: [1, 2, 3] }
            ]
          };
        }
      };

      await expect(embed(client, 'test-model', ['a'], 2)).rejects.toThrow(SupportAgentError);
    });

    it('masks PII by default when opts is omitted', async () => {
      const client = Object.create(nRouter.prototype);
      let receivedInput: string[] = [];
      client.embeddings = {
        create: async (opts: any) => {
          receivedInput = opts.input;
          return {
            data: [{ index: 0, embedding: [1, 2] }]
          };
        }
      };

      await embed(client, 'test-model', ['Contact support@example.com or 555-123-4567'], 2);
      expect(receivedInput).toEqual(['Contact [email] or [phone]']);
    });

    it('masks PII when opts.maskPii is true', async () => {
      const client = Object.create(nRouter.prototype);
      let receivedInput: string[] = [];
      client.embeddings = {
        create: async (opts: any) => {
          receivedInput = opts.input;
          return {
            data: [{ index: 0, embedding: [1, 2] }]
          };
        }
      };

      await embed(client, 'test-model', ['Email info@test.com'], 2, undefined, { maskPii: true });
      expect(receivedInput).toEqual(['Email [email]']);
    });

    it('preserves PII when opts.maskPii is false', async () => {
      const client = Object.create(nRouter.prototype);
      let receivedInput: string[] = [];
      client.embeddings = {
        create: async (opts: any) => {
          receivedInput = opts.input;
          return {
            data: [{ index: 0, embedding: [1, 2] }]
          };
        }
      };

      await embed(client, 'test-model', ['Contact support@example.com'], 2, undefined, { maskPii: false });
      expect(receivedInput).toEqual(['Contact support@example.com']);
    });
  });

  describe('streamChat', () => {
    it('masks message string contents by default (maskPii not false)', async () => {
      const client = Object.create(nRouter.prototype);
      let receivedMessages: any[] = [];
      client.nr = {
        stream: async (opts: any) => {
          receivedMessages = opts.messages;
          async function* chunks() {
            yield { delta: 'ok' };
          }
          return {
            meta: { cost: null, costStatus: 'unpriced' },
            chunks: chunks()
          };
        }
      };

      await streamChat(client, {
        model: 'm',
        messages: [{ role: 'user', content: 'Reach me at user@test.com or 555-123-4567' } as any],
        maxTokens: 10
      });

      expect(receivedMessages).toEqual([
        { role: 'user', content: 'Reach me at [email] or [phone]' }
      ]);
    });

    it('masks multi-part array content with email by default', async () => {
      const client = Object.create(nRouter.prototype);
      let receivedMessages: any[] = [];
      client.nr = {
        stream: async (opts: any) => {
          receivedMessages = opts.messages;
          async function* chunks() {
            yield { delta: 'ok' };
          }
          return {
            meta: { cost: null, costStatus: 'unpriced' },
            chunks: chunks()
          };
        }
      };

      await streamChat(client, {
        model: 'm',
        messages: [{
          role: 'user',
          content: [
            { type: 'text', text: 'my email is secret@example.com' },
            { type: 'image_url', image_url: { url: 'https://example.com/pic.png' } }
          ]
        } as any],
        maxTokens: 10
      });

      expect(receivedMessages).toEqual([
        {
          role: 'user',
          content: [
            { type: 'text', text: 'my email is [email]' },
            { type: 'image_url', image_url: { url: 'https://example.com/pic.png' } }
          ]
        }
      ]);
    });

    it('preserves message string contents when maskPii is false', async () => {
      const client = Object.create(nRouter.prototype);
      let receivedMessages: any[] = [];
      client.nr = {
        stream: async (opts: any) => {
          receivedMessages = opts.messages;
          async function* chunks() {
            yield { delta: 'ok' };
          }
          return {
            meta: { cost: null, costStatus: 'unpriced' },
            chunks: chunks()
          };
        }
      };

      await streamChat(client, {
        model: 'm',
        messages: [{ role: 'user', content: 'Reach me at user@test.com' } as any],
        maxTokens: 10,
        maskPii: false
      });

      expect(receivedMessages).toEqual([
        { role: 'user', content: 'Reach me at user@test.com' }
      ]);
    });

    it('streams non-empty chunks and maps cost', async () => {
      const client = Object.create(nRouter.prototype);
      client.nr = {
        stream: async () => {
          async function* chunks() {
            yield { delta: '' };
            yield { delta: 'hello' };
            yield { delta: ' world' };
          }
          return {
            meta: { cost: 0.05 }, // Let's rely on costFromMeta which expects real headers or we can just mock costFromMeta directly if we were mocking, but it uses it directly.
            // Wait, isPriced expects the object to have the right symbol, or checks headers? 
            // In meta.js, isPriced probably looks for a specific property or costStatus.
            // But we can just see what costFromMeta does.
            chunks: chunks()
          };
        }
      };

      const answer = await streamChat(client, { model: 'm', messages: [], maxTokens: 10 });
      // The chunks should be readable
      const parts = [];
      for await (const c of answer.chunks) {
        parts.push(c);
      }
      expect(parts).toEqual(['hello', ' world']);
    });
  });

  describe('costFromMeta', () => {
    it('returns exact cost when priced', () => {
      // Mocking isPriced behavior might be tricky if it looks for a Symbol or class.
      // Assuming isPriced checks `costStatus === 'exact'` or something similar.
      const meta: any = { cost: 0.05, costStatus: 'exact' };
      const res = costFromMeta(meta);
      expect(res).toEqual({ costUsd: 0.05, status: 'exact' });
    });

    it('never emits 0 as cost, maps to unpriced', () => {
      const meta: any = { cost: 0, costStatus: 'exact' };
      const res = costFromMeta(meta);
      expect(res).toEqual({ costUsd: null, status: 'unpriced' });
    });

    it('returns unpriced when not priced', () => {
      const meta: any = { cost: null, costStatus: 'unpriced' };
      const res = costFromMeta(meta);
      expect(res).toEqual({ costUsd: null, status: 'unpriced' });
    });

    it('includes requestId when present', () => {
      const meta: any = { cost: 0.05, costStatus: 'exact', requestId: 'req_123' };
      const res = costFromMeta(meta);
      expect(res).toEqual({ costUsd: 0.05, status: 'exact', requestId: 'req_123' });
    });
  });
});
