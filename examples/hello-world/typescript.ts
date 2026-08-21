// nRouter — TypeScript hello world
// npm install openai

import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.NROUTER_API_KEY,
  baseURL: "https://api.nrouter.ai/v1",
});

const response = await client.chat.completions.create({
  model: "claude-sonnet-4-20250514",
  messages: [{ role: "user", content: "Hello, nRouter!" }],
});

console.log(response.choices[0].message.content);
