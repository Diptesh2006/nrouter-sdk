/**
 * Meta Llama 3.3 70B Instruct Chat Completion Example
 *
 * Demonstrates:
 * 1. Setting and validating NROUTER_API_KEY
 * 2. Initializing the nRouter TypeScript client
 * 3. Calling chat completion on Meta Llama (meta/llama-3.3-70b-instruct)
 * 4. Tracking request metadata, tokens, and settled cost
 *
 * Usage:
 *   export NROUTER_API_KEY="sk-nrouter-your-key-here"
 *   npx tsx examples/meta-llama-chat.ts
 */

import { nRouter, MODEL_META_LLAMA_3_3_70B_INSTRUCT } from '../sdks/js/dist/index.mjs';

// 1. Setting and reading NROUTER_API_KEY
const apiKey = process.env.NROUTER_API_KEY;
if (!apiKey) {
  console.log('Notice: NROUTER_API_KEY not found in environment.');
  console.log('To run against the live gateway: export NROUTER_API_KEY="sk-nrouter-..."\n');
}

// 2. Initialize nRouter client
const client = new nRouter({
  apiKey: apiKey ?? 'sk-nrouter-demo-virtual-key',
  // Optionally customize base URL (defaults to https://api.nrouter.ai/v1)
  baseURL: process.env.NROUTER_BASE_URL ?? 'https://api.nrouter.ai/v1',
});

async function runMetaLlamaChat() {
  console.log('======================================================');
  console.log(`Model: ${MODEL_META_LLAMA_3_3_70B_INSTRUCT}`);
  console.log('======================================================\n');

  try {
    // 3. Call chat completion on Meta Llama
    console.log('Sending chat request to Meta Llama 3.3 70B Instruct...');
    const response = await client.nr.chat({
      model: MODEL_META_LLAMA_3_3_70B_INSTRUCT,
      prompt: 'Explain the core principles of zero-trust security in three concise bullet points.',
      maxTokens: 512,
      temperature: 0.7,
    });

    // 4. Output response text
    console.log('\n--- Assistant Response ---');
    console.log(client.nr.text(response));

    // 5. Inspect request metadata and exact list-price FinOps tracking
    console.log('\n--- Request Observability & FinOps ---');
    console.log(`Request ID:      ${response.meta.requestId ?? 'unknown'}`);
    console.log(`Served Model:    ${response.meta.model ?? MODEL_META_LLAMA_3_3_70B_INSTRUCT}`);
    console.log(`Gateway Latency: ${response.meta.latencyMs ?? 'n/a'} ms`);
    console.log(
      `Token Usage:     ${response.meta.inputTokens ?? 0} prompt + ` +
      `${response.meta.outputTokens ?? 0} completion = ` +
      `${response.meta.totalTokens ?? 0} total`
    );
    if (response.meta.costStatus === 'exact' && response.meta.cost !== null) {
      console.log(`Settled Spend:   $${response.meta.cost.toFixed(6)} USD (Exact list price)`);
    } else {
      console.log(`Cost Status:     ${response.meta.costStatus ?? 'unpriced'}`);
    }
  } catch (error) {
    console.error('Inference error:', error);
  }
}

runMetaLlamaChat().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
