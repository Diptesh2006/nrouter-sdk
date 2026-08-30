const { test } = require('node:test');
const assert = require('node:assert/strict');

const { nRouter } = require('../dist/index');

test(
  'live Claude Messages request returns billing metadata',
  { skip: process.env.NROUTER_LIVE !== '1' },
  async () => {
    const client = new nRouter({
      apiKey: process.env.NROUTER_API_KEY,
      baseURL: process.env.NROUTER_BASE_URL ?? 'http://127.0.0.1:4000/v1',
      maxRetries: 0,
    });
    const response = await client.nr.messages({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 2,
      messages: [{ role: 'user', content: 'Reply OK' }],
    });

    assert.ok(Array.isArray(response.body.content));
    assert.ok(response.meta.requestId);
    assert.equal(response.meta.costStatus, 'exact');
    assert.ok(response.meta.cost !== null && response.meta.cost > 0);
  },
);
