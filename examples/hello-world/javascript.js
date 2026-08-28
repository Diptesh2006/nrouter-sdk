// nRouter — JavaScript hello world
// npm install openai

const OpenAI = require("openai");

const client = new OpenAI({
  apiKey: process.env.NROUTER_API_KEY,
  baseURL: "https://api.nrouter.ai/v1",
});

(async () => {
  const response = await client.chat.completions.create({
    model: "anthropic/claude-sonnet-4-5-20250929",
    messages: [{ role: "user", content: "Hello, nRouter!" }],
  });

  console.log(response.choices[0].message.content);
})();
