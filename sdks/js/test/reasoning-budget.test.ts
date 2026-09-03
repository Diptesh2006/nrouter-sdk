// DIPTESH-094 — a reasoning model can spend its entire output-token budget
// thinking and hand back EMPTY visible text.
//
// The observation: `gpt-5` returned `outputTokens: 128` with `text: ""`. The
// request succeeded, the spend was real, and the caller had no way to tell
// that from "the model genuinely had nothing to say". Re-running the same
// prompt with more headroom returned the answer.
//
// `chatText()` answers `''` for both, and that stays true — `chat.test.ts`
// pins it and callers depend on it. The distinction is surfaced ADDITIVELY by
// `chatTextDiagnostic()`, which reads the two signals already sitting in the
// body the SDK holds:
//
//   * `choices[0].finish_reason === 'length'` — the budget was hit. On the
//     Anthropic wire the same signal arrives as `stop_reason: "max_tokens"`
//     and `toOpenAIChatCompletion` has already mapped it to `length`.
//   * `usage.completion_tokens_details.reasoning_tokens` — invisible output.
//     The gateway does not rewrite the provider's usage block (it only READS
//     it to price the request: `src/sdk/providers/usage.rs::openai_shape`
//     keeps `completion_tokens` whole and treats `reasoning_tokens` as a
//     subset of it), so the OpenAI-shaped detail block reaches the SDK intact.
//
// Nothing here may change what `chatText()` returns, so every case asserts
// that too.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { chatText, chatTextDiagnostic } = require('../dist/chat');
const { EMPTY_META } = require('../dist/meta');

/** A response whose meta is empty unless a case needs a header count. */
function res(body: Record<string, unknown>, meta: Record<string, unknown> = {}) {
  return { body, meta: { ...EMPTY_META, ...meta } };
}

test('the gpt-5 signature: empty text, a full output budget, all of it reasoning', () => {
  const r = res({
    choices: [{ index: 0, message: { role: 'assistant', content: '' }, finish_reason: 'length' }],
    usage: {
      prompt_tokens: 40,
      completion_tokens: 128,
      total_tokens: 168,
      completion_tokens_details: { reasoning_tokens: 128 },
    },
  });

  assert.equal(chatText(r), '', 'the pinned accessor is unchanged');

  const d = chatTextDiagnostic(r);
  assert.equal(d.text, '');
  assert.equal(d.empty, true);
  assert.equal(d.condition, 'reasoning_budget_exhausted_possible');
  assert.equal(d.finishReason, 'length');
  assert.equal(d.outputTokens, 128);
  assert.equal(d.reasoningTokens, 128);
  assert.ok(d.warning, 'the condition the card is about must carry a warning');
  assert.match(String(d.warning), /budget/i, 'the warning must name the remedy');
  assert.match(String(d.warning), /128/, 'the warning must carry the count it measured');
});

test('reasoning tokens alone are enough, even when the turn stopped normally', () => {
  const r = res({
    choices: [{ index: 0, message: { content: null }, finish_reason: 'stop' }],
    usage: { completion_tokens: 96, completion_tokens_details: { reasoning_tokens: 96 } },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(chatText(r), '');
  assert.equal(d.condition, 'reasoning_budget_exhausted_possible');
  assert.equal(d.reasoningTokens, 96);
});

test('the Anthropic wire reaches the same verdict through the converted body', () => {
  // What `toOpenAIChatCompletion` produces from `stop_reason: "max_tokens"`
  // and a response whose content was entirely `thinking` blocks: content '',
  // finish_reason 'length', and a usage block with NO detail sub-object,
  // because Anthropic counts thinking inside `output_tokens`.
  const r = res({
    choices: [{ index: 0, message: { role: 'assistant', content: '' }, finish_reason: 'length' }],
    usage: { prompt_tokens: 12, completion_tokens: 200, total_tokens: 212 },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(chatText(r), '');
  assert.equal(d.condition, 'reasoning_budget_exhausted_possible');
  assert.equal(d.outputTokens, 200);
  assert.equal(d.reasoningTokens, null, 'never invent a count the provider did not report');
});

test('the header count is the fallback when the body carries no usage block', () => {
  const r = res(
    { choices: [{ index: 0, message: { content: '' }, finish_reason: 'length' }] },
    { outputTokens: 128 },
  );
  const d = chatTextDiagnostic(r);
  assert.equal(d.outputTokens, 128, 'x-nr-output-tokens is the same measurement');
  assert.equal(d.condition, 'reasoning_budget_exhausted_possible');
});

// REVIEW FINDING (HIGH) — a provider that explicitly reports
// `reasoning_tokens: 0` has told us no tokens went on reasoning. Calling that
// turn a reasoning-budget failure, and rendering "(0 of them reasoning)" into
// the warning, contradicts the provider's own evidence. The output budget was
// still exhausted — the remedy is the same — so it gets its own honest name.
test('a reported ZERO reasoning tokens is never diagnosed as a reasoning failure', () => {
  const r = res({
    choices: [{ index: 0, message: { content: '' }, finish_reason: 'length' }],
    usage: { completion_tokens: 64, completion_tokens_details: { reasoning_tokens: 0 } },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(d.condition, 'output_budget_exhausted');
  assert.equal(d.reasoningTokens, 0, 'a reported 0 is a measurement, not a missing value');
  assert.ok(d.warning, 'the budget still ran out; the remedy still needs saying');
  assert.doesNotMatch(
    String(d.warning),
    /reasoning/i,
    'the provider said no reasoning happened — do not claim it did',
  );
  assert.match(String(d.warning), /budget/i);
});

// REVIEW FINDING (MEDIUM) — positive reasoning tokens are THEMSELVES evidence
// that output was spent invisibly. Gating that arm on a separately reported
// `completion_tokens` threw the finding away whenever the provider reported
// the detail block but no total, which is the case the counts are least
// reliable in.
test('positive reasoning tokens stand alone when no total was reported', () => {
  const r = res({
    choices: [{ index: 0, message: { content: '' }, finish_reason: 'stop' }],
    usage: { completion_tokens_details: { reasoning_tokens: 77 } },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(d.outputTokens, null, 'never invent the total the provider withheld');
  assert.equal(d.reasoningTokens, 77);
  assert.equal(d.condition, 'reasoning_budget_exhausted_possible');
  assert.match(String(d.warning), /unreported/, 'say the count is unknown rather than printing null');
});

test('a tool-call-only turn is NOT a budget failure', () => {
  const r = res({
    choices: [
      {
        index: 0,
        message: {
          content: null,
          tool_calls: [{ id: 'c1', type: 'function', function: { name: 'f', arguments: '{}' } }],
        },
        finish_reason: 'tool_calls',
      },
    ],
    usage: { completion_tokens: 31 },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(chatText(r), '');
  assert.equal(d.condition, 'tool_calls_only');
  assert.equal(d.warning, null, 'a legitimate empty content must not warn');
});

test('a genuinely empty answer that spent nothing stays a plain empty completion', () => {
  const r = res({
    choices: [{ index: 0, message: { content: '' }, finish_reason: 'stop' }],
    usage: { prompt_tokens: 9, completion_tokens: 0, total_tokens: 9 },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(d.condition, 'empty_completion');
  assert.equal(d.warning, null);
  assert.equal(d.outputTokens, 0);
});

test('empty text with tokens billed and no budget signal is reported, not guessed', () => {
  const r = res({
    choices: [{ index: 0, message: { content: '' }, finish_reason: 'stop' }],
    usage: { completion_tokens: 17 },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(d.condition, 'empty_but_billed');
  assert.ok(d.warning, 'invisible spend is still worth saying out loud');
  assert.doesNotMatch(
    String(d.warning),
    /reasoning/i,
    'never name a cause the response did not evidence',
  );
});

test('a normal answer diagnoses as ok and carries no warning', () => {
  const r = res({
    choices: [{ index: 0, message: { content: 'SDK UI OK' }, finish_reason: 'stop' }],
    usage: { completion_tokens: 4 },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(d.text, 'SDK UI OK');
  assert.equal(d.empty, false);
  assert.equal(d.condition, 'ok');
  assert.equal(d.warning, null);
});

test('content PARTS are read the same way chatText reads them', () => {
  const r = res({
    choices: [{ index: 0, message: { content: [{ text: 'a' }, { text: 'b' }] } }],
    usage: { completion_tokens: 2 },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(d.text, chatText(r));
  assert.equal(d.condition, 'ok');
});

test('an unexpected shape never throws — the caller already paid for the body', () => {
  for (const body of [{}, { choices: [] }, { choices: [{}] }, { usage: 'nonsense' }]) {
    const d = chatTextDiagnostic(res(body as Record<string, unknown>));
    assert.equal(d.text, '');
    assert.equal(d.empty, true);
    assert.equal(typeof d.condition, 'string');
  }
});

test('a malformed count is dropped rather than reported as a number', () => {
  const r = res({
    choices: [{ index: 0, message: { content: '' }, finish_reason: 'length' }],
    usage: { completion_tokens: 'lots', completion_tokens_details: { reasoning_tokens: NaN } },
  });
  const d = chatTextDiagnostic(r);
  assert.equal(d.outputTokens, null);
  assert.equal(d.reasoningTokens, null);
  // `length` still means the budget was hit, whatever the counts did.
  assert.equal(d.condition, 'reasoning_budget_exhausted_possible');
  assert.doesNotMatch(String(d.warning), /null|NaN|undefined/, 'no placeholder in the message');
});
