#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const { nRouter, nRouterConfigurationError, isRetryable } = require('../dist/index.js');

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

function costOf(result) {
  return typeof result.meta.cost === 'number' && Number.isFinite(result.meta.cost)
    ? result.meta.cost
    : 0;
}

async function runOne(name, fn) {
  const started = Date.now();
  try {
    const result = await fn();
    const cost = result && result.meta ? costOf(result) : 0;
    return { name, ok: true, ms: Date.now() - started, cost, result };
  } catch (error) {
    return {
      name,
      ok: false,
      ms: Date.now() - started,
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
  let spent = 0;
  let requests = 0;

  const models = await client.nrouterModels.list();
  checks.push({ name: 'models.list', ok: Array.isArray(models.data), count: models.data.length });
  assert.ok(Array.isArray(models.data), 'models list must return a data array');

  await assert.rejects(
    () => client.nr.chat({ model: DEFAULT_MODEL, prompt: 'do not send', guardrailIds: ['demo'] }),
    nRouterConfigurationError,
  );
  checks.push({ name: 'guardrailIds local refusal', ok: true });

  assert.throws(
    () => new nRouter({ apiKey: 'sk-openai-not-an-nrouter-key' }),
    nRouterConfigurationError,
  );
  checks.push({ name: 'foreign API key local refusal', ok: true });

  const tokenCheck = await runOne('countTokens', () =>
    client.nr.countTokens({
      model: DEFAULT_MODEL,
      messages: [{ role: 'user', content: 'Count this short sentence.' }],
    }),
  );
  checks.push({
    name: tokenCheck.name,
    ok: tokenCheck.ok,
    ms: tokenCheck.ms,
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
      check = await runOne('nr.stream', async () => {
        const stream = await client.nr.stream({
          model: DEFAULT_MODEL,
          prompt,
          maxTokens: MAX_TOKENS,
          cache: false,
        });
        const text = await stream.text();
        assert.ok(text.trim().length > 0, 'stream should return text');
        return { meta: stream.meta };
      });
    }

    requests += 1;
    spent += check.cost || 0;
    checks.push({
      name: `${check.name} #${requests}`,
      ok: check.ok,
      ms: check.ms,
      cost: check.cost,
      retryable: check.retryable,
      error: check.error,
    });

    if (!check.ok && !check.retryable) {
      disabledModes.add(mode);
    }

    console.log(
      JSON.stringify({
        request: requests,
        check: check.name,
        ok: check.ok,
        cost: check.cost,
        totalCost: Number(spent.toFixed(8)),
        targetCost: TARGET_USD,
        error: check.error,
      }),
    );

  }

  const failed = checks.filter((check) => !check.ok);
  const summary = {
    model: DEFAULT_MODEL,
    targetUsd: TARGET_USD,
    requests,
    estimatedObservedCostUsd: Number(spent.toFixed(8)),
    passedChecks: checks.length - failed.length,
    failedChecks: failed.length,
    failures: failed,
  };

  console.log(JSON.stringify(summary, null, 2));
  if (failed.length > 0) process.exit(1);
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error && error.message ? error.message : error);
  process.exit(1);
});
