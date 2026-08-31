#!/usr/bin/env node
/**
 * nRouter TypeScript/Node.js SDK Demo E2E Certification Script
 */

const http = require('node:http');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { nRouter, createMemory, promptTemplate, buildSamplingParams } = require('../sdks/js/dist/index');

async function main() {
  console.log('======================================================================');
  console.log('nRouter JS/TS SDK End-to-End Demo Certification');
  console.log('======================================================================');

  // 1. Local mock gateway server
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      const auth = req.headers['authorization'] || '';
      if (!auth.startsWith('Bearer sk-nrouter-')) {
        res.writeHead(401, {
          'content-type': 'application/json',
          'x-nr-request-id': 'req-demo-ts-auth-err',
        });
        res.end(JSON.stringify({ error: { message: 'unauthorized' } }));
        return;
      }

      res.writeHead(200, {
        'content-type': 'application/json',
        'x-nr-request-id': 'req-demo-ts-001',
        'x-nr-request-cost': '0.003120',
        'x-nr-cost-status': 'exact',
        'x-nr-model': 'anthropic/claude-sonnet-4-5',
        'x-nr-input-tokens': '55',
        'x-nr-output-tokens': '25',
        'x-nr-total-tokens': '80',
        'x-nr-response-cache': 'miss',
      });

      res.end(JSON.stringify({
        id: 'chatcmpl-demo-ts-001',
        choices: [
          {
            message: {
              role: 'assistant',
              content: 'Hello from TypeScript SDK demo!',
            },
          },
        ],
        usage: { prompt_tokens: 55, completion_tokens: 25, total_tokens: 80 },
      }));
    });
  });

  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const baseUrl = `http://127.0.0.1:${port}/v1`;
  const demoKey = 'sk-nrouter-demo0000000000000000000000000000000000';

  console.log('\n[1/3] Initializing TypeScript client...');
  console.log(`      Endpoint : ${baseUrl}`);

  const client = new nRouter({
    apiKey: demoKey,
    baseURL: baseUrl,
  });

  console.log('\n[2/3] Calling client.chat() with prompt template and sampling...');
  const promptSel = promptTemplate('support-bot', { email: 'demo@example.com' });
  const sampling = buildSamplingParams({
    model: 'anthropic/claude-sonnet-4-5',
    temperature: 0.7,
    top_p: 0.8,
    advanced: true,
  });

  const response = await client.nr.chat({
    model: 'anthropic/claude-sonnet-4-5',
    messages: [{ role: 'user', content: 'Demo test query' }],
    promptTemplateId: promptSel.templateId,
    promptVariables: promptSel.variables,
    ...sampling,
  });

  const content = response.body?.choices?.[0]?.message?.content || '';
  console.log(`      Response : "${content}"`);
  console.log('\n[3/3] Validating response metadata...');
  console.log(`      Request ID : ${response.meta.requestId}`);
  console.log(`      Cost USD   : $${response.meta.cost} (${response.meta.costStatus})`);
  console.log(`      Tokens     : ${response.meta.inputTokens} in / ${response.meta.outputTokens} out (Total: ${response.meta.totalTokens})`);

  assert.equal(response.meta.requestId, 'req-demo-ts-001');
  assert.equal(response.meta.cost, 0.00312);
  assert.equal(response.meta.totalTokens, 80);

  const mem = createMemory();
  await mem.add({ role: 'user', content: 'Demo prompt' });
  const msgs = await mem.messages();
  assert.equal(msgs.length, 1);

  server.close();

  console.log('\n======================================================================');
  console.log('Result: PASS (TypeScript demo execution verified)');
  console.log('======================================================================');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
