#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { nRouter, isRetryable } = require('../dist/index.js');

const DEFAULTS = {
  embeddingModel: process.env.NROUTER_EMBEDDING_MODEL || 'text-embedding-3-small',
  imageModel: process.env.NROUTER_IMAGE_MODEL || 'gemini-2.5-flash-image',
  speechModel: process.env.NROUTER_SPEECH_MODEL || '',
  transcribeModel: process.env.NROUTER_TRANSCRIBE_MODEL || '',
  videoModel: process.env.NROUTER_VIDEO_MODEL || '',
};
const EMBEDDING_REPEAT = Number.parseInt(process.env.NROUTER_EMBEDDING_REPEAT || '1', 10);

function loadRootEnv() {
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

function observedCost(result) {
  if (!result || !result.meta) return 0;
  return typeof result.meta.cost === 'number' && Number.isFinite(result.meta.cost) ? result.meta.cost : 0;
}

async function run(name, fn) {
  const started = Date.now();
  try {
    const value = await fn();
    return {
      name,
      ok: true,
      ms: Date.now() - started,
      cost: observedCost(value),
      details: summarize(value),
    };
  } catch (error) {
    return {
      name,
      ok: false,
      ms: Date.now() - started,
      retryable: isRetryable(error),
      errorName: error && error.name ? error.name : 'Error',
      message: error && error.message ? error.message : String(error),
    };
  }
}

function summarize(value) {
  if (!value) return {};
  if (value.bytes instanceof Uint8Array) {
    return { bytes: value.bytes.length, contentType: value.contentType, requestId: value.meta.requestId };
  }
  if (value.kind === 'text' || value.kind === 'json') {
    return {
      kind: value.kind,
      format: value.format,
      textPreview: typeof value.text === 'string' ? value.text.slice(0, 120) : null,
      requestId: value.meta.requestId,
    };
  }
  const body = value.body || {};
  return {
    requestId: value.meta && value.meta.requestId,
    costStatus: value.meta && value.meta.costStatus,
    bodyKeys: Object.keys(body).slice(0, 8),
    dataCount: Array.isArray(body.data) ? body.data.length : undefined,
    firstDataKeys: Array.isArray(body.data) && body.data[0] ? Object.keys(body.data[0]).slice(0, 8) : undefined,
    id: typeof body.id === 'string' ? body.id : undefined,
    status: typeof body.status === 'string' ? body.status : undefined,
  };
}

function tinyWav() {
  const sampleRate = 8000;
  const samples = sampleRate / 4;
  const dataSize = samples * 2;
  const bytes = new Uint8Array(44 + dataSize);
  const view = new DataView(bytes.buffer);
  const write = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) bytes[offset + i] = text.charCodeAt(i);
  };
  write(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  write(8, 'WAVE');
  write(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, 'data');
  view.setUint32(40, dataSize, true);
  return bytes;
}

async function main() {
  loadRootEnv();
  const client = new nRouter({
    apiKey: process.env.NROUTER_API_KEY,
    baseURL: process.env.NROUTER_BASE_URL || 'https://api.nrouter.ai/v1',
    maxRetries: 0,
  });

  const ids = await client.nrouterModels.ids();
  const results = [];

  if (ids.includes(DEFAULTS.embeddingModel)) {
    for (let i = 0; i < Math.max(1, EMBEDDING_REPEAT); i += 1) {
      results.push(
        await run(`embeddings #${i + 1}`, () =>
          client.nr.media.embeddings({
            model: DEFAULTS.embeddingModel,
            input: [
              `nRouter SDK feature spend test ${i + 1}`,
              'Embeddings convert text into vectors for search and retrieval.',
            ],
          }),
        ),
      );
    }
  } else {
    results.push({ name: 'embeddings', ok: false, skipped: true, message: `${DEFAULTS.embeddingModel} not listed` });
  }

  if (ids.includes(DEFAULTS.imageModel)) {
    results.push(
      await run('image', () =>
        client.nr.media.image({
          model: DEFAULTS.imageModel,
          prompt: 'A clean product-style image of the words nRouter SDK on a simple white desk, high quality',
          size: process.env.NROUTER_IMAGE_SIZE || '1024x1024',
          n: 1,
        }),
      ),
    );
  } else {
    results.push({ name: 'image', ok: false, skipped: true, message: `${DEFAULTS.imageModel} not listed` });
  }

  if (DEFAULTS.speechModel) {
    results.push(
      await run('speech', () =>
        client.nr.media.speech({
          model: DEFAULTS.speechModel,
          voice: process.env.NROUTER_SPEECH_VOICE || 'alloy',
          input: 'Hello from the nRouter JavaScript SDK feature test.',
          response_format: 'mp3',
        }),
      ),
    );
  } else {
    results.push({ name: 'speech', ok: false, skipped: true, message: 'set NROUTER_SPEECH_MODEL to run speech' });
  }

  if (DEFAULTS.transcribeModel) {
    results.push(
      await run('transcribe', () =>
        client.nr.media.transcribe({
          model: DEFAULTS.transcribeModel,
          file: tinyWav(),
          fileName: 'tiny.wav',
          response_format: 'text',
        }),
      ),
    );
  } else {
    results.push({ name: 'transcribe', ok: false, skipped: true, message: 'set NROUTER_TRANSCRIBE_MODEL to run transcription' });
  }

  if (DEFAULTS.videoModel) {
    results.push(
      await run('video', () =>
        client.nr.media.video({
          model: DEFAULTS.videoModel,
          prompt: 'A three second abstract animation of the nRouter letters on a white background.',
          seconds: process.env.NROUTER_VIDEO_SECONDS || '3',
          size: process.env.NROUTER_VIDEO_SIZE || '720p',
        }),
      ),
    );
  } else {
    results.push({ name: 'video', ok: false, skipped: true, message: 'set NROUTER_VIDEO_MODEL to run video generation' });
  }

  const totalObservedCost = results.reduce((sum, result) => sum + (result.cost || 0), 0);
  console.log(JSON.stringify({ models: DEFAULTS, totalObservedCost: Number(totalObservedCost.toFixed(8)), results }, null, 2));
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error && error.message ? error.message : error);
  process.exit(1);
});
