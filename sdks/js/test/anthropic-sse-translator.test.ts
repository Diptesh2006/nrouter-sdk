// Tests for createAnthropicSSETranslator, extractNRouterHeaders, toFinishReason, and toOpenAIUsage.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  createAnthropicSSETranslator,
  extractNRouterHeaders,
  toFinishReason,
  toOpenAIUsage,
} = require('../dist/chat');

const encoder = new TextEncoder();
const decoder = new TextDecoder();

async function pump(translator, chunks: string[]): Promise<string[]> {
  const readable = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

  const outputStream = readable.pipeThrough(translator);
  const reader = outputStream.getReader();
  const output: string[] = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    output.push(decoder.decode(value));
  }

  return output;
}

test('createAnthropicSSETranslator translates text stream to OpenAI choices[0].delta.content format', async () => {
  const translator = createAnthropicSSETranslator({
    requestedModel: 'claude-3-5-sonnet-20241022',
    requestId: 'req-test-123',
  });

  const inputEvents = [
    'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_123","type":"message","role":"assistant","model":"claude-3-5-sonnet-20241022","usage":{"input_tokens":25}}}\n\n',
    'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
    'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n\n',
    'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world!"}}\n\n',
    'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
    'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":10}}\n\n',
    'event: message_stop\ndata: {"type":"message_stop"}\n\n',
  ];

  const results = await pump(translator, inputEvents);
  const joined = results.join('');

  // Should have assistant role frame
  assert.match(joined, /"role":"assistant"/);
  // Should have text deltas
  assert.match(joined, /"content":"Hello"/);
  assert.match(joined, /"content":" world!"/);
  // Should map end_turn to stop finish_reason
  assert.match(joined, /"finish_reason":"stop"/);
  // Should have usage chunk with input (25) + output (10) = 35 total
  assert.match(joined, /"usage":{"prompt_tokens":25,"completion_tokens":10,"total_tokens":35}/);
  // Should end with [DONE]
  assert.match(joined, /data: \[DONE\]/);
});

test('createAnthropicSSETranslator handles tool use calls correctly', async () => {
  const translator = createAnthropicSSETranslator({
    requestedModel: 'claude-3-5-sonnet-20241022',
    requestId: 'req-tool-call',
  });

  const inputEvents = [
    'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_456","type":"message","role":"assistant","model":"claude-3-5-sonnet-20241022","usage":{"input_tokens":50}}}\n\n',
    'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"tool_call_abc","name":"get_weather"}}\n\n',
    'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"location\\": "}}\n\n',
    'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"\\"San Francisco\\"}"}}\n\n',
    'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
    'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":30}}\n\n',
    'event: message_stop\ndata: {"type":"message_stop"}\n\n',
  ];

  const results = await pump(translator, inputEvents);
  const joined = results.join('');

  // Initial tool call with id and function name
  assert.match(joined, /"name":"get_weather"/);
  assert.match(joined, /"id":"tool_call_abc"/);
  // Tool argument deltas
  assert.match(joined, /\{\\"location\\": /);
  // finish_reason should be tool_calls
  assert.match(joined, /"finish_reason":"tool_calls"/);
  assert.match(joined, /data: \[DONE\]/);
});

test('createAnthropicSSETranslator passes gateway mid-stream error frame untouched', async () => {
  const translator = createAnthropicSSETranslator({ requestedModel: 'claude-3-haiku' });
  const errorFrame = 'data: {"error":{"type":"guardrail_blocked","message":"Blocked by content policy"}}\n\n';

  const results = await pump(translator, [errorFrame]);
  const joined = results.join('');

  assert.match(joined, /"error":{"type":"guardrail_blocked","message":"Blocked by content policy"}/);
});

test('createAnthropicSSETranslator passes OpenAI-shaped chunk untouched (façade passthrough)', async () => {
  const translator = createAnthropicSSETranslator({ requestedModel: 'gpt-4o' });
  const openAIChunk = 'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hi"}}]}\n\n';

  const results = await pump(translator, [openAIChunk]);
  const joined = results.join('');

  assert.match(joined, /"object":"chat.completion.chunk"/);
  assert.match(joined, /"content":"Hi"/);
});

test('createAnthropicSSETranslator handles split chunks across network buffers', async () => {
  const translator = createAnthropicSSETranslator({ requestedModel: 'claude-3-5-sonnet' });

  // Split right in the middle of JSON data
  const part1 = 'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_';
  const part2 = 'delta","text":"Splitted chunk!"}}\n\n';

  const results = await pump(translator, [part1, part2]);
  const joined = results.join('');

  assert.match(joined, /"content":"Splitted chunk!"/);
});

test('extractNRouterHeaders extracts all x-nr-* headers and normalizes keys to lowercase', () => {
  const mockHeaders = {
    'X-NR-Request-Id': 'req-987',
    'x-nr-request-cost': '0.0025',
    'X-NR-Cost-Status': 'exact',
    'x-nr-model': 'claude-3-5-sonnet-20241022',
    'x-nr-guardrails': 'pass',
    'content-type': 'application/json',
    'authorization': 'Bearer secret',
  };

  const extracted = extractNRouterHeaders(mockHeaders);
  assert.equal(extracted['x-nr-request-id'], 'req-987');
  assert.equal(extracted['x-nr-request-cost'], '0.0025');
  assert.equal(extracted['x-nr-cost-status'], 'exact');
  assert.equal(extracted['x-nr-model'], 'claude-3-5-sonnet-20241022');
  assert.equal(extracted['x-nr-guardrails'], 'pass');
  assert.equal(extracted['content-type'], undefined);
  assert.equal(extracted['authorization'], undefined);
});

test('toFinishReason accurately maps Anthropic stop reasons', () => {
  assert.equal(toFinishReason('max_tokens'), 'length');
  assert.equal(toFinishReason('tool_use'), 'tool_calls');
  assert.equal(toFinishReason('end_turn'), 'stop');
  assert.equal(toFinishReason('stop_sequence'), 'stop');
  assert.equal(toFinishReason('refusal'), 'stop');
  assert.equal(toFinishReason(null), null);
  assert.equal(toFinishReason(undefined), null);
  assert.equal(toFinishReason('unknown_reason'), 'stop');
});

test('toOpenAIUsage calculates prompt tokens including cache reads and writes', () => {
  const usage = toOpenAIUsage({
    input_tokens: 100,
    cache_creation_input_tokens: 20,
    cache_read_input_tokens: 30,
    output_tokens: 50,
  });

  assert.deepEqual(usage, {
    prompt_tokens: 150, // 100 + 20 + 30
    completion_tokens: 50,
    total_tokens: 200,
  });

  // Empty or invalid returns null (Rule #28 never confident zeros)
  assert.equal(toOpenAIUsage(null), null);
  assert.equal(toOpenAIUsage({}), null);
});
