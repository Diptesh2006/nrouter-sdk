// Case 7 — the sampling truth table.
//
// The policy is PORTED from the hosted playground's single source of truth, so
// a snippet copied out of the dashboard must produce the SAME body from npm.
// Each row below is a request the gateway or the provider treats differently:
//
//   * default mode sends NOTHING, so every provider's own tuned defaults win
//     (filling in a "sensible" 0.7 silently overrides all of them);
//   * Claude is temperature XOR top_p — Anthropic 400s a request carrying both
//     with "Please use only one", which the caller cannot act on because they
//     never set both explicitly;
//   * top_p === 1 is the neutral value and is NEVER sent — zero behavioural
//     gain, and on Claude it is enough to trigger that 400.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { buildSamplingParams, isClaudeModel } = require('../dist/sampling');

test('the Claude family is matched by FAMILY, not by host cloud', () => {
  // The same weights are served by Anthropic direct, by Bedrock and by Vertex,
  // and all three enforce the XOR. A provider allowlist of "anthropic" would
  // let every Bedrock/Vertex Claude request through into the 400.
  for (const model of [
    'claude-sonnet-4-5',
    'claude-haiku-4-5-20251001',
    'us.anthropic.claude-sonnet-4-6-v1:0',
    'publishers/anthropic/models/claude-3-7-sonnet',
    'CLAUDE-OPUS-4',
  ]) {
    assert.equal(isClaudeModel(model), true, `${model} must be recognised as Claude`);
  }
  for (const model of ['gpt-4o', 'gemini-2.5-pro', 'qwen-max', 'llama-3.1-70b']) {
    assert.equal(isClaudeModel(model), false, `${model} must NOT be recognised as Claude`);
  }
  // A private alias that hides the family name, with provider attribution.
  assert.equal(isClaudeModel('acme-internal-fast', 'anthropic'), true);
  assert.equal(isClaudeModel('acme-internal-fast', 'openai'), false);
  assert.equal(isClaudeModel('acme-internal-fast', null), false);
  assert.equal(isClaudeModel('acme-internal-fast'), false);
});

// name | advanced | model | temperature | topP | expected body subset
const TABLE: [string, boolean, string, number | undefined, number | undefined, Record<string, number>][] = [
  ['default mode sends nothing (non-Claude)',        false, 'gpt-4o',            0.2, 0.4,       {}],
  ['default mode sends nothing (Claude)',            false, 'claude-sonnet-4-5', 0.2, 0.4,       {}],
  ['default mode sends nothing even with both set',  false, 'gpt-4o',            0.9, 0.9,       {}],

  ['Claude + neutral top_p sends temperature only',  true,  'claude-sonnet-4-5', 0.3, 1,         { temperature: 0.3 }],
  ['Claude + absent top_p sends temperature only',   true,  'claude-sonnet-4-5', 0.3, undefined, { temperature: 0.3 }],
  ['Claude + non-neutral top_p sends top_p ONLY',    true,  'claude-sonnet-4-5', 0.3, 0.4,       { top_p: 0.4 }],
  ['Bedrock Claude also drops temperature',          true,  'us.anthropic.claude-sonnet-4-6-v1:0', 0.3, 0.4, { top_p: 0.4 }],
  ['Claude + top_p, no temperature',                 true,  'claude-sonnet-4-5', undefined, 0.4, { top_p: 0.4 }],
  ['Claude + neither knob sends nothing',            true,  'claude-sonnet-4-5', undefined, undefined, {}],

  ['non-Claude sends BOTH',                          true,  'gpt-4o',            0.3, 0.4,       { temperature: 0.3, top_p: 0.4 }],
  ['non-Claude + neutral top_p sends temperature',   true,  'gpt-4o',            0.3, 1,         { temperature: 0.3 }],
  ['non-Claude + top_p only',                        true,  'gpt-4o',            undefined, 0.4, { top_p: 0.4 }],
  ['non-Claude + neither sends nothing',             true,  'gpt-4o',            undefined, undefined, {}],
  ['temperature 0 is a real value, not absent',      true,  'gpt-4o',            0,   undefined, { temperature: 0 }],
  ['top_p 0 is a real value, not neutral',           true,  'gpt-4o',            undefined, 0,   { top_p: 0 }],
];

for (const [name, advanced, model, temperature, topP, expected] of TABLE) {
  test(`sampling: ${name}`, () => {
    const params = buildSamplingParams({ advanced, model, temperature, topP });
    assert.deepEqual(params, expected);
    // deepEqual on `{}` would pass against `{temperature: undefined}` in some
    // assertion libraries; pin the key set explicitly so an undefined-valued
    // property — which a transport may still serialize — cannot slip through.
    assert.deepEqual(Object.keys(params).sort(), Object.keys(expected).sort());
  });
}

test('top_p === 1 is NEVER sent, on any model, in any mode', () => {
  for (const model of ['gpt-4o', 'claude-sonnet-4-5', 'gemini-2.5-pro']) {
    for (const temperature of [undefined, 0, 0.7]) {
      const params = buildSamplingParams({ advanced: true, model, temperature, topP: 1 });
      assert.equal(
        'top_p' in params,
        false,
        `${model} with temperature ${String(temperature)} sent the neutral top_p`
      );
    }
  }
});

test('Claude never receives temperature and top_p together', () => {
  // The single request shape Anthropic refuses. If this ever goes green with
  // both keys present, every advanced-sampling Claude call 400s.
  for (const topP of [0, 0.1, 0.5, 0.99]) {
    const params = buildSamplingParams({
      advanced: true,
      model: 'claude-sonnet-4-5',
      temperature: 0.7,
      topP,
    });
    assert.equal(
      'temperature' in params && 'top_p' in params,
      false,
      `Claude got both knobs at top_p=${topP}`
    );
    assert.deepEqual(params, { top_p: topP }, 'on Claude a chosen top_p WINS');
  }
});
