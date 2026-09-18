#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const { nRouter, nRouterConfigurationError, isRetryable } = require('../dist/index.js');
const { classify, summarize, summaryLines } = require('./lib/accounting.js');

const DEFAULT_MODEL = process.env.NROUTER_DEMO_MODEL || 'claude-haiku-4-5-20251001';
const TARGET_USD = Number(process.env.NROUTER_TARGET_USD || '0.05');
const MAX_REQUESTS = Number.parseInt(process.env.NROUTER_MAX_REQUESTS || '50', 10);
const MAX_TOKENS = Number.parseInt(process.env.NROUTER_MAX_TOKENS || '256', 10);

function loadRootEnv() {
  const fs = require('node:fs');
  const path = require('node:path');
  const envPath = path.resolve(__dirname, '..', '..', '..', '.env');
  if (!fs.existsSync(envPath)) return;
  for (const rawLine of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim().replace(/^['"]|['"]$/g, '');
    if (!(key in process.env)) process.env[key] = value;
  }
}

function textOf(client, result) {
  const text = client.nr.text(result).trim();
  if (text) return text;
  const content = result.body && result.body.content;
  if (!Array.isArray(content)) return '';
  return content
    .map((part) => (part && typeof part.text === 'string' ? part.text : ''))
    .join('')
    .trim();
}

/**
 * Run one billed call and CLASSIFY what it cost, rather than coercing it.
 *
 * This used to be `meta.cost` with a `: 0` fallback, and the caller then did
 * `spent += check.cost || 0`. Two separate places turning "the gateway could
 * not price this" into "this was free" — and the streamed mode hits it on every
 * single request, because a stream's headers are written before a token exists
 * and report `unpriced` permanently (`sdks/js/docs/cost.md`). The printed total
 * was therefore structurally too low and said so nowhere.
 *
 * `options.streamed` and `options.free` are the caller's claim about the wire it
 * used; `classify` checks each against what actually arrived and warns on a
 * contradiction.
 */
async function runOne(name, fn, options = {}) {
  const started = Date.now();
  try {
    const result = await fn();
    return { name, ms: Date.now() - started, ...classify(result && result.meta, options), result };
  } catch (error) {
    return {
      name,
      ms: Date.now() - started,
      // A failed call still has a request id and may still have been billed, so
      // its metadata is carried rather than dropped.
      ...classify(error && error.meta, { ...options, ok: false }),
      retryable: isRetryable(error),
      error: error && error.message ? error.message : String(error),
    };
  }
}

async function main() {
  loadRootEnv();
  const client = new nRouter({
    apiKey: process.env.NROUTER_API_KEY,
    baseURL: process.env.NROUTER_BASE_URL || 'https://api.nrouter.ai/v1',
    maxRetries: 0,
  });

  const checks = [];
  // Two lists on purpose. `checks` is every assertion this probe makes,
  // including the local refusals that never touch the network; `records` is only
  // the calls that could have cost money, which is what may be accounted for.
  const records = [];
  let spent = 0;
  let requests = 0;

  const models = await client.nrouterModels.list();
  checks.push({ name: 'models.list', ok: Array.isArray(models.data), count: models.data.length });
  assert.ok(Array.isArray(models.data), 'models list must return a data array');

  // Five fallbacks is one over the published ceiling of four, so the whole
  // request is refused here rather than at the gateway.
  await assert.rejects(
    () =>
      client.nr.chat({
        model: DEFAULT_MODEL,
        prompt: 'do not send',
        fallbacks: ['a', 'b', 'c', 'd', 'e'],
      }),
    nRouterConfigurationError,
  );
  checks.push({ name: 'fallbacks ceiling refused locally', ok: true });

  assert.throws(
    () => new nRouter({ apiKey: 'sk-openai-not-an-nrouter-key' }),
    nRouterConfigurationError,
  );
  checks.push({ name: 'foreign API key local refusal', ok: true });

  const tokenCheck = await runOne(
    'countTokens',
    () =>
      client.nr.countTokens({
        model: DEFAULT_MODEL,
        messages: [{ role: 'user', content: 'Count this short sentence.' }],
      }),
    // `POST /v1/messages/count_tokens` is one of the routes documented as free:
    // its missing cost header means zero, not unknown. Leaving it in the
    // `unpriced` bucket would report a permanent hole in every run's total and
    // send the reader looking for a pricing bug that is not there.
    { free: true },
  );
  records.push(tokenCheck);
  checks.push({
    name: tokenCheck.name,
    ok: tokenCheck.ok,
    ms: tokenCheck.ms,
    bucket: tokenCheck.bucket,
    cost: tokenCheck.cost,
    error: tokenCheck.error,
  });

  const prompts = [
    'Return a JSON object with keys status and reason. Keep it tiny.',
    'Write one concise sentence explaining API gateway routing.',
    'Summarize why SDKs should redact API keys.',
    'Give three short bullet points about retry safety.',
    'Explain prompt templates to a beginner in two sentences.',
  ];
  const disabledModes = new Set();

  // The loop advances on the PRICED total, which is the only figure that means
  // anything. A run whose calls all come back unpriced — every streamed one
  // does — therefore stops at MAX_REQUESTS rather than at TARGET_USD, and the
  // summary says why. Advancing on a coerced zero would have spun to the request
  // cap while reporting a spend of $0.00000000.
  while (spent < TARGET_USD && requests < MAX_REQUESTS) {
    const prompt = prompts[requests % prompts.length];
    const availableModes = [0, 1, 2, 3].filter((mode) => !disabledModes.has(mode));
    if (availableModes.length === 0) break;
    const mode = availableModes[requests % availableModes.length];
    let check;

    if (mode === 0) {
      check = await runOne('nr.chat', () =>
        client.nr.chat({
          model: DEFAULT_MODEL,
          systemPrompt: 'You are a strict SDK test agent. Keep answers compact.',
          prompt,
          maxTokens: MAX_TOKENS,
          cache: false,
        }),
      );
      if (check.ok) assert.ok(textOf(client, check.result).length > 0, 'chat should return text');
    } else if (mode === 1) {
      check = await runOne('nr.messages', () =>
        client.nr.messages({
          model: DEFAULT_MODEL,
          max_tokens: MAX_TOKENS,
          messages: [{ role: 'user', content: prompt }],
        }),
      );
      if (check.ok) assert.ok(textOf(client, check.result).length > 0, 'messages should return text');
    } else if (mode === 2) {
      check = await runOne('nr.responses', () =>
        client.nr.responses({
          model: DEFAULT_MODEL,
          input: prompt,
          max_output_tokens: MAX_TOKENS,
        }),
      );
    } else {
      check = await runOne(
        'nr.stream',
        async () => {
          const stream = await client.nr.stream({
            model: DEFAULT_MODEL,
            prompt,
            maxTokens: MAX_TOKENS,
            cache: false,
          });
          const text = await stream.text();
          assert.ok(text.trim().length > 0, 'stream should return text');
          return { meta: stream.meta };
        },
        // Unpriced BY CONSTRUCTION, not by failure: the headers were written
        // before the first token. The settled figure is on the spend row, joined
        // on requestId.
        { streamed: true },
      );
    }

    requests += 1;
    // `check.cost` is a number only in the `priced` bucket; it is null
    // everywhere else. Never `|| 0` — that is the coercion this file existed to
    // demonstrate and now exists to refuse.
    spent += check.bucket === 'priced' ? check.cost : 0;
    records.push(check);
    checks.push({
      name: `${check.name} #${requests}`,
      ok: check.ok,
      ms: check.ms,
      bucket: check.bucket,
      cost: check.cost,
      retryable: check.retryable,
      error: check.error,
    });
    if (check.warning) console.warn(`  ! ${check.name}: ${check.warning}`);

    if (!check.ok && !check.retryable) {
      disabledModes.add(mode);
    }

    console.log(
      JSON.stringify({
        request: requests,
        check: check.name,
        ok: check.ok,
        // `null`, not 0, when this call carried no exact price. The bucket says
        // which of the four reasons it was.
        cost: check.cost,
        bucket: check.bucket,
        pricedTotalCost: Number(spent.toFixed(8)),
        targetCost: TARGET_USD,
        error: check.error,
      }),
    );

  }

  const failed = checks.filter((check) => !check.ok);
  const spend = summarize(records);
  const summary = {
    model: DEFAULT_MODEL,
    targetUsd: TARGET_USD,
    requests,
    // Renamed from `estimatedObservedCostUsd`, which was neither an estimate
    // nor the run's cost: it was the priced subset with every unpriced call
    // silently added as zero. The name now says what the number is, and
    // `spend.complete` says whether it is the whole story.
    pricedTotalUsd: Number(spend.pricedTotalUsd.toFixed(8)),
    spend,
    passedChecks: checks.length - failed.length,
    failedChecks: failed.length,
    failures: failed,
  };

  console.log(JSON.stringify(summary, null, 2));
  console.log('');
  for (const line of summaryLines(spend)) console.log(line);
  if (failed.length > 0) process.exit(1);
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error && error.message ? error.message : error);
  process.exit(1);
});
