const { test } = require('node:test');
const assert = require('node:assert');
const { diagnoseReasoningExhaustion } = require('../dist/diagnostics');

test('diagnoseReasoningExhaustion detects reasoning exhaustion when finish_reason is length and content is empty', () => {
  const report = diagnoseReasoningExhaustion('length', 1000, 1000, '');
  assert.strictEqual(report.exhausted, true);
  assert.strictEqual(report.reasoningTokens, 1000);
  assert.ok(report.message && report.message.includes('Reasoning consumed the entire token budget'));
});

test('diagnoseReasoningExhaustion reports not exhausted when completion text was produced', () => {
  const report = diagnoseReasoningExhaustion('length', 1000, 200, 'Here is the answer');
  assert.strictEqual(report.exhausted, false);
});

test('diagnoseReasoningExhaustion reports not exhausted on normal stop', () => {
  const report = diagnoseReasoningExhaustion('stop', 50, 10, 'Hello');
  assert.strictEqual(report.exhausted, false);
});
