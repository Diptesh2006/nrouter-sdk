import http from 'node:http';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { generateVideoPrompt } from '../dist/agent.js';

const apiKey = process.env.NROUTER_API_KEY;
const port = process.env.PORT ? parseInt(process.env.PORT, 10) : 4174;
const sessions = new Map();

function conversationFor(req, res) {
  const cookie = req.headers.cookie || '';
  const sessionId = cookie.match(/(?:^|;\s*)nrouter_video_session=([^;]+)/)?.[1];
  if (sessionId && sessions.has(sessionId)) return sessions.get(sessionId);

  const newSessionId = randomUUID();
  const conversation = [];
  sessions.set(newSessionId, conversation);
  res.setHeader('Set-Cookie', `nrouter_video_session=${newSessionId}; Path=/; HttpOnly; SameSite=Lax`);
  return conversation;
}

const server = http.createServer(async (req, res) => {
  const host = req.headers.host || '127.0.0.1';
  const parsedUrl = new URL(req.url || '/', `http://${host}`);
  const { pathname } = parsedUrl;

  if (req.method === 'GET' && pathname === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('ok');
    return;
  }

  if (req.method === 'GET' && pathname === '/favicon.ico') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === 'GET' && pathname === '/') {
    const indexPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'index.html');
    const html = await fs.promises.readFile(indexPath, 'utf-8');
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
    return;
  }

  if (req.method === 'POST' && pathname === '/api/reset') {
    const conversation = conversationFor(req, res);
    conversation.length = 0;
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: [] }));
    return;
  }

  if (req.method === 'POST' && pathname === '/api/generate') {
    const conversation = conversationFor(req, res);
    let rawBody = '';
    req.on('data', chunk => rawBody += chunk);
    req.on('end', async () => {
      try {
        const body = JSON.parse(rawBody);
        const result = await generateVideoPrompt({
          apiKey,
          query: body.query,
          conversation,
          ...{"videoModel":"Google Veo"}
        });
        conversation.push(
          { role: 'user', content: body.query },
          { role: 'assistant', content: result },
        );
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ result, messages: conversation }));
      } catch (err) {
        const status = Number.isInteger(err.status) ? err.status : 500;
        const requestId = err.requestId ?? err.request_id ?? err.headers?.['x-nr-request-id'];
        res.writeHead(status, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message, requestId }));
      }
    });
    return;
  }
  res.writeHead(404);
  res.end();
});

const host = process.env.HOST || '127.0.0.1';
server.listen(port, host, () => {
  console.log(`Demo server listening on http://${host}:${port}`);
});
