import { nRouter } from '@nrouter_ai/sdk';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export interface VideoPromptOptions {
  apiKey?: string;
  query: string;
  videoModel: string;
  conversation?: Array<{ role: 'user' | 'assistant'; content: string }>;
}

export async function generateVideoPrompt(options: VideoPromptOptions): Promise<string> {
  const client = new nRouter({ apiKey: options.apiKey || process.env.NROUTER_API_KEY });
  const _dirname = path.dirname(fileURLToPath(import.meta.url));

  // Detailed guides remain packaged for reference; keep the live system payload compact.
  const runtimeSystem = fs.readFileSync(path.join(_dirname, '../skills/runtime-system.md'), 'utf-8');
  
  // Keep the browser transcript complete, but send only a compact continuity hint upstream.
  // Guardrail scoring is currently sensitive to large multi-turn payloads.
  const conversation = (options.conversation ?? []).slice(-2).map((message) => ({
    role: message.role,
    content: message.content.slice(0, 120),
  }));
  const messages = [
    ...conversation,
    { role: 'user' as const, content: options.query },
  ];

  const response = await client.nr.messages({
    model: process.env.NROUTER_MODEL || 'claude-haiku-4-5-20251001',
    system: runtimeSystem,
    messages,
    max_tokens: 1024,
  });

  const body = response.body as any;
  const textBlock = body.content?.find((c: any) => c.type === 'text');
  return textBlock?.text ?? '';
}
