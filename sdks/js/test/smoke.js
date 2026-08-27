// `npm test` entry point.
//
// package.json runs `tsc && node test/smoke.js`, so this file is what turns
// one command into the whole suite. It discovers every `*.test.ts` beside it
// and hands them to Node's built-in test runner, which strips the type
// annotations natively (Node >= 22.18 / 23; no loader, no ts-node, no new
// dependency — `openai` stays the only one).
//
// The suite runs against the COMPILED output in `dist/`, not against `src/`.
// That is deliberate: `dist/` is what npm publishes, so a downlevelling bug —
// the `class X extends Error` emit that quietly breaks every `instanceof` — is
// visible here rather than only to a consumer.
//
// The connection assertions this file used to carry inline now live in
// `test/client.test.ts`, where a failure names the case instead of the file.

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const files = fs
  .readdirSync(__dirname)
  .filter((name) => name.endsWith(".test.ts") || name.endsWith(".test.js"))
  .sort()
  .map((name) => path.join(__dirname, name));

if (files.length === 0) {
  console.error("no test files found beside test/smoke.js");
  process.exit(1);
}

if (!fs.existsSync(path.join(__dirname, "..", "dist", "index.js"))) {
  console.error("dist/ is missing — run `npm run build` first (npm test does this for you).");
  process.exit(1);
}

const result = spawnSync(process.execPath, ["--test", ...files], {
  stdio: "inherit",
  cwd: path.join(__dirname, ".."),
});

if (result.error) {
  console.error(result.error);
  process.exit(1);
}
process.exit(result.status === null ? 1 : result.status);
