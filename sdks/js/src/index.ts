/**
 * nRouter SDK — OpenAI-compatible client for the nRouter LLM gateway.
 *
 * Usage:
 *   import { nRouter } from "nroutersdk";
 *
 *   const client = new nRouter(); // reads NROUTER_API_KEY from env
 *   const response = await client.chat.completions.create({
 *     model: "claude-sonnet-4-20250514",
 *     messages: [{ role: "user", content: "Hello!" }],
 *   });
 */

import { nRouter } from "./client";

export { nRouter };
export default nRouter;
