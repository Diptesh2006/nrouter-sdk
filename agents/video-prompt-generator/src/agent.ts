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

  const instructions = fs.readFileSync(path.join(_dirname, '../skills/instructions.md'), 'utf-8');
  const brand = fs.readFileSync(path.join(_dirname, '../skills/brand.md'), 'utf-8');
  
  // Normalize model name for file lookup (e.g., "Google Veo" -> "google-veo")
  const modelSlug = options.videoModel.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  let modelSpecifics = '';
  try {
    modelSpecifics = fs.readFileSync(path.join(_dirname, '../skills/models/' + modelSlug + '.md'), 'utf-8');
  } catch (e) {
    modelSpecifics = 'Target Model: ' + options.videoModel; // Fallback if no specific markdown exists
  }

  const messages = [
    ...(options.conversation ?? []),
    { role: 'user' as const, content: options.query },
  ];

  const response = await client.nr.messages({
    model: process.env.NROUTER_MODEL || 'claude-haiku-4-5-20251001',
    system: instructions + '\n\n' + brand + '\n\n' + modelSpecifics,
    messages,
    max_tokens: 1024,
  });

  const body = response.body as any;
  const textBlock = body.content?.find((c: any) => c.type === 'text');
  return textBlock ? textBlock.text : '';
}
