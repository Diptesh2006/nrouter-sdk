import { describe, it, expect, vi } from 'vitest';
import { runToolPhase } from '../src/tools.js';
import type { ResolvedConfig } from '../src/types.js';
import type { AgentTool } from '@nrouter_ai/sdk';

describe('runToolPhase', () => {
  it('returns messages unchanged with no model call if no tools configured', async () => {
    const cfg = {
      tools: [] as AgentTool[],
    } as ResolvedConfig;
    const emit = vi.fn();
    const result = await runToolPhase(cfg, [{ role: 'user', content: 'hello' }], emit);
    expect(result.ranTools).toBe(false);
    expect(emit).not.toHaveBeenCalled();
    expect(result.messages).toEqual([{ role: 'user', content: 'hello' }]);
  });

  it('runs tool, emits events, and handles throwing tool without blowing up the whole runTools flow', async () => {
    // SDK's runTools calls runner.request
    const fakeClient = { nr: { request: vi.fn() } } as any;
    
    let calls = 0;
    fakeClient.nr.request.mockImplementation(async () => {
      calls++;
      if (calls === 1) {
        return {
          status: 200,
          headers: { get: () => null },
          text: JSON.stringify({
            choices: [{
              message: {
                role: 'assistant',
                tool_calls: [{
                  id: 'call_1', type: 'function', function: { name: 'my_tool', arguments: '{"arg":"val"}' }
                }, {
                  id: 'call_2', type: 'function', function: { name: 'bad_tool', arguments: '{"arg":"val"}' }
                }]
              }
            }]
          }),
          contentType: 'application/json'
        };
      }
      return {
        status: 200,
        headers: { get: () => null },
        text: JSON.stringify({
          choices: [{ message: { role: 'assistant', content: 'All done.' } }]
        }),
        contentType: 'application/json'
      };
    });

    const goodTool: AgentTool = {
      definition: { type: 'function', function: { name: 'my_tool' } },
      execute: vi.fn().mockResolvedValue('success'),
    };
    const badTool: AgentTool = {
      definition: { type: 'function', function: { name: 'bad_tool' } },
      execute: vi.fn().mockRejectedValue(new Error('boom')),
    };

    const cfg = {
      client: fakeClient,
      models: ['test-model'],
      tools: [goodTool, badTool],
      maxToolSteps: 2,
    } as any;

    const emit = vi.fn();
    const result = await runToolPhase(cfg, [{ role: 'user', content: 'hi' }], emit);

    expect(result.ranTools).toBe(true);
    expect(emit).toHaveBeenCalledWith({ tool: 'my_tool', title: 'my_tool', status: 'running' });
    expect(emit).toHaveBeenCalledWith({ tool: 'my_tool', title: 'my_tool', status: 'done' });
    expect(emit).toHaveBeenCalledWith({ tool: 'bad_tool', title: 'bad_tool', status: 'running' });
    expect(emit).toHaveBeenCalledWith({ tool: 'bad_tool', title: 'bad_tool', status: 'error' });
  });

  it('honors maxToolSteps', async () => {
    const fakeClient = { nr: { request: vi.fn() } } as any;
    // Always returns a tool call
    fakeClient.nr.request.mockResolvedValue({
      status: 200,
      headers: { get: () => null },
      text: JSON.stringify({
        choices: [{
          message: {
            role: 'assistant',
            tool_calls: [{
              id: 'call_x', type: 'function', function: { name: 'my_tool', arguments: '{}' }
            }]
          }
        }]
      }),
      contentType: 'application/json'
    });

    const tool: AgentTool = {
      definition: { type: 'function', function: { name: 'my_tool' } },
      execute: vi.fn().mockResolvedValue('ok'),
    };

    const cfg = {
      client: fakeClient,
      models: ['test-model'],
      tools: [tool],
      maxToolSteps: 3,
    } as any;

    const emit = vi.fn();
    const result = await runToolPhase(cfg, [{ role: 'user', content: 'hi' }], emit);
    // Should stop after 3 steps due to maxToolSteps
    expect(fakeClient.nr.request).toHaveBeenCalledTimes(3);
    expect(result.ranTools).toBe(true);
  });

  it('calls the primary model by default and the given model when one is passed', async () => {
    const fakeClient = { nr: { request: vi.fn() } } as any;
    fakeClient.nr.request.mockResolvedValue({
      status: 200,
      headers: { get: () => null },
      text: JSON.stringify({ choices: [{ message: { role: 'assistant', content: 'answer' } }] }),
      contentType: 'application/json'
    });
    const tool: AgentTool = {
      definition: { type: 'function', function: { name: 'my_tool' } },
      execute: vi.fn().mockResolvedValue('ok'),
    };
    const cfg = { client: fakeClient, models: ['primary-model', 'backup-model'], tools: [tool], maxToolSteps: 2 } as any;

    await runToolPhase(cfg, [{ role: 'user', content: 'hi' }], vi.fn());
    expect(JSON.stringify(fakeClient.nr.request.mock.calls[0])).toContain('primary-model');
    expect(JSON.stringify(fakeClient.nr.request.mock.calls[0])).not.toContain('backup-model');

    await runToolPhase(cfg, [{ role: 'user', content: 'hi' }], vi.fn(), undefined, 'backup-model');
    expect(JSON.stringify(fakeClient.nr.request.mock.calls[1])).toContain('backup-model');
    expect(JSON.stringify(fakeClient.nr.request.mock.calls[1])).not.toContain('primary-model');
  });
});
