/**
 * TypeSafe Jev System One Decision Model Example
 *
 * Demonstrates:
 * 1. Setting and validating NROUTER_API_KEY
 * 2. Initializing the nRouter TypeScript client
 * 3. Calling System One rapid classification/decision on TypeSafe Jev (typesafe/jev)
 * 4. Structured JSON output for deterministic policy decision-making
 * 5. Low-latency performance and exact cost settlement
 *
 * Usage:
 *   export NROUTER_API_KEY="sk-nrouter-your-key-here"
 *   npx tsx sdks/js/examples/typesafe-jev-decision.ts
 */

import { nRouter, MODEL_TYPESAFE_JEV } from '../dist/index.mjs';

// 1. Setting and reading NROUTER_API_KEY
const apiKey = process.env.NROUTER_API_KEY;
if (!apiKey) {
  console.error('Set NROUTER_API_KEY before running this live example.');
  process.exit(1);
}

// 2. Initialize nRouter client
const client = new nRouter({
  apiKey,
  baseURL: process.env.NROUTER_BASE_URL ?? 'https://api.nrouter.ai/v1',
});

interface DecisionResult {
  action: 'ALLOW' | 'FLAG' | 'BLOCK';
  riskScore: number;
  category: string;
  rationale: string;
}

async function runTypeSafeJevDecision() {
  console.log('======================================================');
  console.log(`Model: ${MODEL_TYPESAFE_JEV} (TypeSafe AI Jev System One)`);
  console.log('======================================================\n');

  const incomingEvent = {
    eventType: 'WIRE_TRANSFER_REQUEST',
    accountId: 'act_94ad8dcd',
    amountUSD: 45000,
    destinationCountry: 'CH',
    isNewBeneficiary: true,
    userTenureDays: 3,
  };

  console.log('Evaluating transaction event for real-time risk decision:');
  console.log(JSON.stringify(incomingEvent, null, 2));

  try {
    // 3. Call System One decision on TypeSafe Jev
    const systemPrompt = `You are TypeSafe Jev System One, an ultra-fast deterministic risk classifier.
Analyze the transaction and output a single JSON object with schema:
{
  "action": "ALLOW" | "FLAG" | "BLOCK",
  "riskScore": number (0.0 to 1.0),
  "category": string,
  "rationale": string
}
Output raw JSON only.`;

    const response = await client.chat.completions.create({
      model: MODEL_TYPESAFE_JEV,
      messages: [
        { role: 'system', content: systemPrompt },
        {
          role: 'user',
          content: `Evaluate transaction: ${JSON.stringify(incomingEvent)}`,
        },
      ],
      temperature: 0.0, // System One decisions prioritize zero temperature for deterministic output
      max_tokens: 256,
      response_format: { type: 'json_object' },
    });

    const content = response.choices[0]?.message?.content ?? '{}';
    const decision: DecisionResult = JSON.parse(content);

    // 4. Output decision verdict
    console.log('\n--- System One Decision Verdict ---');
    console.log(`Action:     ${decision.action}`);
    console.log(`Risk Score: ${decision.riskScore}`);
    console.log(`Category:   ${decision.category}`);
    console.log(`Rationale:  ${decision.rationale}`);

    // 5. Inspect request metadata
    const meta = client.lastResponse;
    if (meta) {
      console.log('\n--- Request Observability & FinOps ---');
      console.log(`Request ID:      ${meta.requestId ?? 'unknown'}`);
      console.log(`Served Model:    ${meta.model ?? MODEL_TYPESAFE_JEV}`);
      console.log(`Gateway Latency: ${meta.latencyMs ?? 'n/a'} ms`);
      console.log(
        `Token Usage:     ${meta.inputTokens ?? 0} prompt + ` +
        `${meta.outputTokens ?? 0} completion = ` +
        `${meta.totalTokens ?? 0} total`
      );
      if (meta.costStatus === 'exact' && meta.cost !== null) {
        console.log(`Settled Spend:   $${meta.cost.toFixed(6)} USD`);
      } else {
        console.log(`Cost Status:     ${meta.costStatus ?? 'unpriced'}`);
      }
    }
  } catch (error) {
    console.error('Decision error:', error);
  }
}

runTypeSafeJevDecision().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
