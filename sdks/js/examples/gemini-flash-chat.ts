/**
 * Google Gemini 2.0 Flash Chat Completion Example
 *
 * Demonstrates:
 * 1. Setting and validating NROUTER_API_KEY
 * 2. Initializing the nRouter TypeScript client
 * 3. Calling fast chat completion on Google Gemini 2.0 Flash (google/gemini-2.0-flash)
 * 4. Tracking request metadata, tokens, latency, and exact list-price FinOps spend
 * 5. Referencing Gemini 2.0 Flash Lite and Gemini 1.5 model constants
 *
 * Usage:
 *   export NROUTER_API_KEY="sk-nrouter-your-key-here"
 *   npx tsx sdks/js/examples/gemini-flash-chat.ts
 */

import {
  nRouter,
  MODEL_GOOGLE_GEMINI_2_0_FLASH,
  MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE,
  MODEL_GOOGLE_GEMINI_1_5_PRO_002,
  MODEL_GOOGLE_GEMINI_1_5_FLASH_002,
} from '../dist/index.mjs';

// 1. Setting and reading NROUTER_API_KEY
const apiKey = process.env.NROUTER_API_KEY;
if (!apiKey) {
  console.log('Notice: NROUTER_API_KEY not found in environment.');
  console.log('To run against the live gateway: export NROUTER_API_KEY="sk-nrouter-..."\n');
}

// 2. Initialize nRouter client
const client = new nRouter({
  apiKey: apiKey ?? 'sk-nrouter-demo-virtual-key',
  baseURL: process.env.NROUTER_BASE_URL ?? 'https://api.nrouter.ai/v1',
});

async function runGeminiFlashChat() {
  console.log('======================================================');
  console.log(`Model: ${MODEL_GOOGLE_GEMINI_2_0_FLASH}`);
  console.log('Available Gemini 2.0 / 1.5 Family:');
  console.log(` - ${MODEL_GOOGLE_GEMINI_2_0_FLASH}`);
  console.log(` - ${MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE}`);
  console.log(` - ${MODEL_GOOGLE_GEMINI_1_5_PRO_002}`);
  console.log(` - ${MODEL_GOOGLE_GEMINI_1_5_FLASH_002}`);
  console.log('======================================================\n');

  try {
    // 3. Call chat completion on Google Gemini 2.0 Flash
    console.log('Sending chat request to Google Gemini 2.0 Flash...');
    const response = await client.nr.chat({
      model: MODEL_GOOGLE_GEMINI_2_0_FLASH,
      prompt: 'Compare edge computing vs cloud centralized computing in two concise bullet points.',
      maxTokens: 512,
      temperature: 0.2,
    });

    // 4. Output response text
    console.log('\n--- Assistant Response ---');
    console.log(client.nr.text(response));

    // 5. Inspect request metadata and exact list-price FinOps tracking
    console.log('\n--- Request Observability & FinOps ---');
    console.log(`Request ID:      ${response.meta.requestId ?? 'unknown'}`);
    console.log(`Served Model:    ${response.meta.model ?? MODEL_GOOGLE_GEMINI_2_0_FLASH}`);
    console.log(`Gateway Latency: ${response.meta.latencyMs ?? 'n/a'} ms`);
    console.log(
      `Token Usage:     ${response.meta.inputTokens ?? 0} prompt + ` +
      `${response.meta.outputTokens ?? 0} completion = ` +
      `${response.meta.totalTokens ?? 0} total`
    );
    if (response.meta.costStatus === 'exact' && response.meta.cost !== null) {
      console.log(`Settled Spend:   $${response.meta.cost.toFixed(6)} USD (Exact list price, 0% markup)`);
    } else {
      console.log(`Cost Status:     ${response.meta.costStatus ?? 'unpriced'}`);
    }
  } catch (error) {
    console.error('Inference error:', error);
  }
}

runGeminiFlashChat().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
