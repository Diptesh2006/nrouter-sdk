#!/usr/bin/env node
'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { nRouter, isRetryable } = require('../..');

const PORT = Number.parseInt(process.env.PORT || '4317', 10);
const DEFAULT_MODEL = process.env.NROUTER_DEMO_MODEL || 'claude-haiku-4-5-20251001';

function loadRootEnv() {
  const envPath = path.resolve(__dirname, '..', '..', '..', '..', '.env');
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

function client() {
  return new nRouter({
    apiKey: process.env.NROUTER_API_KEY,
    baseURL: process.env.NROUTER_BASE_URL || 'https://api.nrouter.ai/v1',
    maxRetries: 0,
  });
}

function sendJson(res, status, body) {
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  });
  res.end(JSON.stringify(body));
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > 100_000) {
        reject(new Error('request body too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch {
        reject(new Error('request body must be JSON'));
      }
    });
    req.on('error', reject);
  });
}

function publicError(error) {
  return {
    message: error && error.message ? error.message : String(error),
    name: error && error.name ? error.name : 'Error',
    retryable: isRetryable(error),
  };
}

function textOf(nr, result) {
  const text = nr.text(result).trim();
  if (text) return text;
  const content = result.body && result.body.content;
  if (!Array.isArray(content)) return '';
  return content
    .map((part) => (part && typeof part.text === 'string' ? part.text : ''))
    .join('')
    .trim();
}

async function handleApi(req, res, pathname) {
  const nr = client();

  if (req.method === 'GET' && pathname === '/api/health') {
    sendJson(res, 200, {
      ok: true,
      hasKey: Boolean(process.env.NROUTER_API_KEY),
      defaultModel: DEFAULT_MODEL,
      baseURL: process.env.NROUTER_BASE_URL || 'https://api.nrouter.ai/v1',
    });
    return;
  }

  if (req.method === 'GET' && pathname === '/api/models') {
    const models = await nr.nrouterModels.list();
    sendJson(res, 200, {
      count: models.data.length,
      models: models.data.slice(0, 50).map((model) => ({
        id: model.id,
        owned_by: model.owned_by,
      })),
    });
    return;
  }

  if (req.method === 'POST' && pathname === '/api/chat') {
    const body = await readJson(req);
    const result = await nr.nr.chat({
      model: typeof body.model === 'string' && body.model.trim() ? body.model.trim() : DEFAULT_MODEL,
      systemPrompt: typeof body.systemPrompt === 'string' ? body.systemPrompt : 'You are a concise SDK test agent.',
      prompt: typeof body.prompt === 'string' && body.prompt.trim() ? body.prompt : 'Reply with: SDK UI OK',
      maxTokens: Number.isInteger(body.maxTokens) ? body.maxTokens : 128,
      cache: body.cache === false ? false : undefined,
    });
    sendJson(res, 200, {
      text: textOf(nr.nr, result),
      meta: result.meta,
    });
    return;
  }

  if (req.method === 'POST' && pathname === '/api/messages') {
    const body = await readJson(req);
    const result = await nr.nr.messages({
      model: typeof body.model === 'string' && body.model.trim() ? body.model.trim() : DEFAULT_MODEL,
      max_tokens: Number.isInteger(body.maxTokens) ? body.maxTokens : 128,
      messages: [
        {
          role: 'user',
          content: typeof body.prompt === 'string' && body.prompt.trim() ? body.prompt : 'Reply with: SDK UI OK',
        },
      ],
    });
    sendJson(res, 200, {
      text: textOf(nr.nr, result),
      meta: result.meta,
    });
    return;
  }

  if (req.method === 'POST' && pathname === '/api/guardrail-check') {
    await nr.nr.chat({
      model: DEFAULT_MODEL,
      prompt: 'This should be refused locally before the network.',
      guardrailIds: ['demo'],
    });
    sendJson(res, 500, { ok: false, error: 'guardrailIds unexpectedly reached the network' });
    return;
  }

  sendJson(res, 404, { error: 'not found' });
}

function serveStatic(res, pathname) {
  const file = pathname === '/' ? 'index.html' : pathname.slice(1);
  const safe = path.normalize(file).replace(/^(\.\.[/\\])+/, '');
  const full = path.join(__dirname, 'public', safe);
  if (!full.startsWith(path.join(__dirname, 'public')) || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
    sendJson(res, 404, { error: 'not found' });
    return;
  }
  const ext = path.extname(full);
  const type = ext === '.css' ? 'text/css; charset=utf-8' : ext === '.js' ? 'text/javascript; charset=utf-8' : 'text/html; charset=utf-8';
  res.writeHead(200, { 'content-type': type, 'cache-control': 'no-store' });
  fs.createReadStream(full).pipe(res);
}

loadRootEnv();

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
  try {
    if (url.pathname.startsWith('/api/')) {
      await handleApi(req, res, url.pathname);
    } else {
      serveStatic(res, url.pathname);
    }
  } catch (error) {
    sendJson(res, 500, { ok: false, error: publicError(error) });
  }
});

server.listen(PORT, () => {
  console.log(`nRouter JS SDK demo UI: http://127.0.0.1:${PORT}`);
});
