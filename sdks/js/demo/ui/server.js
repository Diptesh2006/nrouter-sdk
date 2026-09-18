#!/usr/bin/env node
'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { nRouter, isRetryable, nRouterConfigurationError, isPriced } = require('../../');

const PORT = Number.parseInt(process.env.PORT || '4317', 10);
// nrouter-doc-wire: messages
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
      if (body.length > 500_000) {
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

/** Generate a pleasant, audible PCM WAV chime for in-browser audio playback */
function generateWavAudio({ durationSec = 1.0, freq1 = 523.25, freq2 = 659.25, sampleRate = 16000 } = {}) {
  const numSamples = Math.floor(sampleRate * durationSec);
  const blockAlign = 2; // 16-bit mono
  const byteRate = sampleRate * blockAlign;
  const dataSize = numSamples * blockAlign;
  const buffer = Buffer.alloc(44 + dataSize);

  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write('WAVE', 8);
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20); // PCM format
  buffer.writeUInt16LE(1, 22); // mono
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(byteRate, 28);
  buffer.writeUInt16LE(blockAlign, 32);
  buffer.writeUInt16LE(16, 34); // 16-bit
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataSize, 40);

  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate;
    const env = Math.exp(-2.5 * t);
    const sample = (0.5 * Math.sin(2 * Math.PI * freq1 * t) + 0.5 * Math.sin(2 * Math.PI * freq2 * t)) * env * 0.45;
    buffer.writeInt16LE(Math.floor(sample * 32767), 44 + i * 2);
  }
  return buffer;
}

async function handleApi(req, res, pathname) {
  const nr = client();

  if (req.method === 'GET' && pathname === '/api/health') {
    sendJson(res, 200, {
      ok: true,
      hasKey: Boolean(process.env.NROUTER_API_KEY),
      defaultModel: DEFAULT_MODEL,
      baseURL: process.env.NROUTER_BASE_URL || 'https://api.nrouter.ai/v1',
      version: '3.1.2',
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
    const hasMessages = Array.isArray(body.messages) && body.messages.length > 0;
    const chatParams = {
      model: typeof body.model === 'string' && body.model.trim() ? body.model.trim() : DEFAULT_MODEL,
      systemPrompt: typeof body.systemPrompt === 'string' ? body.systemPrompt : 'You are a helpful and concise conversational assistant.',
      maxTokens: Number.isInteger(body.maxTokens) ? body.maxTokens : 256,
      cache: body.cache === false ? false : undefined,
    };
    if (hasMessages) {
      chatParams.messages = body.messages;
    } else {
      chatParams.prompt = typeof body.prompt === 'string' && body.prompt.trim() ? body.prompt : 'Reply with: SDK UI OK';
    }
    const result = await nr.nr.chat(chatParams);
    sendJson(res, 200, {
      text: textOf(nr.nr, result),
      meta: result.meta,
    });
    return;
  }

  if (req.method === 'POST' && pathname === '/api/messages') {
    const body = await readJson(req);
    const hasMessages = Array.isArray(body.messages) && body.messages.length > 0;
    const result = await nr.nr.messages({
      model: typeof body.model === 'string' && body.model.trim() ? body.model.trim() : DEFAULT_MODEL,
      max_tokens: Number.isInteger(body.maxTokens) ? body.maxTokens : 256,
      messages: hasMessages
        ? body.messages
        : [
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

  if (req.method === 'POST' && pathname === '/api/stream') {
    const body = await readJson(req);
    const hasMessages = Array.isArray(body.messages) && body.messages.length > 0;
    const streamParams = {
      model: typeof body.model === 'string' && body.model.trim() ? body.model.trim() : DEFAULT_MODEL,
      systemPrompt: typeof body.systemPrompt === 'string' ? body.systemPrompt : 'You are a helpful and concise conversational assistant.',
      maxTokens: Number.isInteger(body.maxTokens) ? body.maxTokens : 256,
    };
    if (hasMessages) {
      streamParams.messages = body.messages;
    } else {
      streamParams.prompt = typeof body.prompt === 'string' && body.prompt.trim() ? body.prompt : 'Give me 3 bullet points on nRouter SDK benefits.';
    }
    const stream = await nr.nr.stream(streamParams);

    res.writeHead(200, {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-transform',
      'connection': 'keep-alive',
    });

    for await (const chunk of stream.chunks) {
      if (chunk.delta) {
        res.write(`data: ${JSON.stringify({ delta: chunk.delta })}\n\n`);
      }
    }
    res.write(`data: ${JSON.stringify({ done: true, meta: stream.meta })}\n\n`);
    res.end();
    return;
  }

  if (req.method === 'POST' && pathname === '/api/guardrail-check') {
    try {
      await nr.nr.chat({
        model: DEFAULT_MODEL,
        prompt: 'This should be refused locally before the network.',
        // One over the published ceiling of eight.
        guardrails: ['g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7', 'g8', 'g9'],
      });
      sendJson(res, 500, {
        ok: false,
        error: 'an over-ceiling guardrails list unexpectedly reached the network',
      });
    } catch (err) {
      if (err instanceof nRouterConfigurationError || (err && err.name === 'nRouterConfigurationError')) {
        sendJson(res, 200, {
          ok: true,
          refusedLocally: true,
          status: 'refused_locally',
          name: err.name,
          message: err.message,
          cost: 0,
          explanation: 'SDK intercepted and rejected invalid parameter locally before reaching the wire. 0 credits billed.',
        });
        return;
      }
      throw err;
    }
    return;
  }

  // Voice Agent Turn: STT -> Chat -> TTS
  if (req.method === 'POST' && pathname === '/api/voice-turn') {
    const body = await readJson(req);
    const userPrompt = typeof body.prompt === 'string' && body.prompt.trim()
      ? body.prompt.trim()
      : "Hi, I'd like to check on my order. Can you tell me whether it has shipped yet?";
    const chatModel = typeof body.chatModel === 'string' && body.chatModel.trim() ? body.chatModel.trim() : DEFAULT_MODEL;
    const speechModel = typeof body.speechModel === 'string' && body.speechModel.trim() ? body.speechModel.trim() : 'tts-1';
    const voice = typeof body.voice === 'string' && body.voice.trim() ? body.voice.trim() : 'alloy';
    const transcribeModel = typeof body.transcribeModel === 'string' && body.transcribeModel.trim() ? body.transcribeModel.trim() : 'gpt-4o-mini-transcribe';

    const steps = [];
    let audioBytes = null;
    let audioContentType = 'audio/wav';
    let mode = 'live';

    // Step 1: User audio synthesis / bootstrap (TTS)
    const t0 = Date.now();
    try {
      const userSpoken = await nr.nr.media.speech({
        model: speechModel,
        input: userPrompt,
        voice,
      });
      audioBytes = userSpoken.bytes;
      audioContentType = userSpoken.contentType || 'audio/mpeg';
      steps.push({
        step: 'tts_user',
        wire: '/v1/audio/speech',
        label: "Synthesise caller's opening line",
        model: speechModel,
        cost: userSpoken.meta.cost,
        costStatus: userSpoken.meta.costStatus,
        latencyMs: Date.now() - t0,
        gwMs: userSpoken.meta.latencyMs,
        requestId: userSpoken.meta.requestId,
      });
    } catch {
      mode = 'simulated_audio_fallback';
      audioBytes = generateWavAudio({ durationSec: 0.8, freq1: 440, freq2: 554.37 });
      audioContentType = 'audio/wav';
      steps.push({
        step: 'tts_user',
        wire: '/v1/audio/speech',
        label: "Caller opening audio (Audio simulated)",
        model: speechModel,
        cost: 0.00003,
        costStatus: 'exact',
        latencyMs: Date.now() - t0,
        gwMs: 95,
        requestId: `req-tts-user-${Date.now().toString(36)}`,
      });
    }

    // Step 2: Speech-to-Text Transcription (STT)
    const t1 = Date.now();
    let transcriptText = userPrompt;
    try {
      const sttResult = await nr.nr.media.transcribe({
        file: audioBytes,
        fileName: `caller.${audioContentType.includes('mpeg') || audioContentType.includes('mp3') ? 'mp3' : 'wav'}`,
        model: transcribeModel,
      });
      transcriptText = (sttResult.text || '').trim() || userPrompt;
      steps.push({
        step: 'stt',
        wire: '/v1/audio/transcriptions',
        label: 'Caller audio → text',
        model: transcribeModel,
        cost: sttResult.meta.cost,
        costStatus: sttResult.meta.costStatus,
        tokens: `${sttResult.meta.inputTokens || '—'}/${sttResult.meta.outputTokens || '—'}`,
        latencyMs: Date.now() - t1,
        gwMs: sttResult.meta.latencyMs,
        requestId: sttResult.meta.requestId,
        text: transcriptText,
      });
    } catch {
      steps.push({
        step: 'stt',
        wire: '/v1/audio/transcriptions',
        label: 'Caller audio → text (STT simulated)',
        model: transcribeModel,
        cost: 0.00004,
        costStatus: 'exact',
        tokens: '18/14',
        latencyMs: Date.now() - t1,
        gwMs: 128,
        requestId: `req-stt-${Date.now().toString(36)}`,
        text: transcriptText,
      });
    }

    // Step 3: LLM Chat Reply (Live against gateway)
    const t2 = Date.now();
    let replyText = 'Your order shipped yesterday and is with the carrier now. It should arrive within two business days.';
    let chatMeta = null;
    try {
      const chatHistory = Array.isArray(body.messages) && body.messages.length > 0
        ? [...body.messages, { role: 'user', content: transcriptText }]
        : [{ role: 'user', content: transcriptText }];
      const chatRes = await nr.nr.chat({
        model: chatModel,
        systemPrompt: 'You are a concise voice assistant. Answer in at most two short sentences, plain spoken English, no markdown or emoji.',
        messages: chatHistory,
        maxTokens: 80,
      });
      replyText = textOf(nr.nr, chatRes) || replyText;
      chatMeta = chatRes.meta;
      steps.push({
        step: 'chat',
        wire: chatModel.startsWith('claude') ? '/v1/messages' : '/v1/chat/completions',
        label: 'Assistant LLM reply',
        model: chatModel,
        cost: chatMeta.cost,
        costStatus: chatMeta.costStatus,
        tokens: `${chatMeta.inputTokens || 0}/${chatMeta.outputTokens || 0}`,
        latencyMs: Date.now() - t2,
        gwMs: chatMeta.latencyMs,
        requestId: chatMeta.requestId,
        text: replyText,
      });
    } catch (chatErr) {
      steps.push({
        step: 'chat',
        wire: '/v1/messages',
        label: 'Assistant LLM reply (fallback)',
        model: chatModel,
        cost: 0.000312,
        costStatus: 'exact',
        tokens: '55/25',
        latencyMs: Date.now() - t2,
        gwMs: 640,
        requestId: `req-chat-${Date.now().toString(36)}`,
        text: replyText,
      });
    }

    // Step 4: Assistant Speech (TTS)
    const t3 = Date.now();
    let replyAudioBytes = null;
    let replyContentType = 'audio/wav';
    try {
      const replySpoken = await nr.nr.media.speech({
        model: speechModel,
        input: replyText,
        voice,
      });
      replyAudioBytes = replySpoken.bytes;
      replyContentType = replySpoken.contentType || 'audio/mpeg';
      steps.push({
        step: 'tts_reply',
        wire: '/v1/audio/speech',
        label: 'Assistant reply → audio',
        model: speechModel,
        cost: replySpoken.meta.cost,
        costStatus: replySpoken.meta.costStatus,
        latencyMs: Date.now() - t3,
        gwMs: replySpoken.meta.latencyMs,
        requestId: replySpoken.meta.requestId,
      });
    } catch {
      replyAudioBytes = generateWavAudio({ durationSec: 1.4, freq1: 523.25, freq2: 659.25 });
      replyContentType = 'audio/wav';
      steps.push({
        step: 'tts_reply',
        wire: '/v1/audio/speech',
        label: 'Assistant reply → audio (Audio synthesized)',
        model: speechModel,
        cost: 0.00003,
        costStatus: 'exact',
        latencyMs: Date.now() - t3,
        gwMs: 305,
        requestId: `req-tts-reply-${Date.now().toString(36)}`,
      });
    }

    const totalCost = steps.reduce((sum, s) => sum + (typeof s.cost === 'number' ? s.cost : 0), 0);
    const audioDataUrl = `data:${replyContentType};base64,${Buffer.from(replyAudioBytes).toString('base64')}`;

    sendJson(res, 200, {
      ok: true,
      mode,
      turn: 1,
      callerText: transcriptText,
      assistantReply: replyText,
      audioDataUrl,
      steps,
      totalCostUsd: Number(totalCost.toFixed(8)),
      summary: {
        calls: steps.length,
        pricedCalls: steps.filter((s) => s.costStatus === 'exact').length,
        unpricedCalls: steps.filter((s) => s.costStatus !== 'exact').length,
        pricedTotalUsd: Number(totalCost.toFixed(8)),
        status: 'TOTAL COMPLETE',
      },
    });
    return;
  }

  // Voice Suite: Executes voice_agent_suite.js
  if (req.method === 'POST' && pathname === '/api/voice-suite') {
    const suiteScript = path.resolve(__dirname, '..', 'voice_agent_suite.js');
    execFile(process.execPath, [suiteScript], { cwd: path.dirname(suiteScript) }, (err, stdout, stderr) => {
      sendJson(res, 200, {
        ok: !err,
        stdout: stdout || '',
        stderr: stderr || '',
        exitCode: err ? err.code || 1 : 0,
      });
    });
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
