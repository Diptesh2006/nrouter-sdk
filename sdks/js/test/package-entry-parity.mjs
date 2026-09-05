// The ESM entry must export EXACTLY what the CommonJS entry exports.
//
// PR #12 added `src/index.mjs` so that `import` resolves to a real ES module
// instead of the CJS build, which is the right fix — but it is a HAND-WRITTEN
// re-export list of 65 names. Nothing regenerates it and nothing compared it to
// the source of truth, so the failure mode is silent and one-directional: add
// an export to the TypeScript entry, ship it, and every CommonJS consumer sees
// it while every ESM consumer gets `undefined`. `npm test` stayed green,
// because `package-entry.mjs` checks the default export and one named one.
//
// That is the same shape as a stale doc count or a hardcoded ban list: a
// derived value restated by hand. The fix is not to hand-check it more
// carefully, it is to compare it against what it is derived FROM.
//
// Deliberately compares the BUILT artifacts, not the sources. `dist/index.js`
// and `dist/index.mjs` are what npm actually ships and what a consumer's
// resolver picks between via the `exports` map; a parity proof over `src/`
// would pass while the published package disagreed with itself.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const cjs = require(join(here, '..', 'dist', 'index.js'));
const esm = await import(pathToFileURL(join(here, '..', 'dist', 'index.mjs')).href);

// `default` is compared separately below: CJS carries it as an ordinary key,
// ESM as the module's default binding, so a raw key-set diff always reports it
// missing and would make this test permanently, uselessly red.
const cjsNames = Object.keys(cjs).filter((k) => k !== 'default').sort();
const esmNames = Object.keys(esm).filter((k) => k !== 'default').sort();

const missing = cjsNames.filter((k) => !esmNames.includes(k));
const extra = esmNames.filter((k) => !cjsNames.includes(k));

assert.deepEqual(
  missing,
  [],
  `dist/index.mjs is missing ${missing.length} export(s) the CommonJS entry ships: ` +
    `${missing.join(', ')}. An ESM consumer gets undefined for each. ` +
    `Add them to src/index.mjs.`,
);

// The other direction matters too: a name only ESM exports is one CJS
// consumers cannot reach, and it means the shim has drifted from the build
// rather than merely lagged it.
assert.deepEqual(
  extra,
  [],
  `dist/index.mjs exports ${extra.length} name(s) the CommonJS entry does not: ${extra.join(', ')}.`,
);

// A zero-length comparison passes vacuously, which is how a parity gate ends up
// proving nothing after a build change empties one side.
assert.ok(
  cjsNames.length > 50,
  `only ${cjsNames.length} CommonJS exports found — the build looks empty, so this ` +
    `parity check would pass without comparing anything.`,
);

// Presence is not parity. A destructured re-export SNAPSHOTS each value at
// import time, so a binding that CJS resolves lazily — a circular dependency
// settling later, or an `Object.defineProperty` getter — can be present in the
// ESM namespace and hold `undefined`, while CJS consumers see the live value. A
// key-set diff passes that. Compare the values too. (claude review, PR #12.)
const mismatched = cjsNames.filter((k) => esm[k] !== cjs[k]);
assert.deepEqual(
  mismatched,
  [],
  `dist/index.mjs re-exports ${mismatched.length} name(s) that are NOT the same value as ` +
    `the CommonJS entry's: ${mismatched.join(', ')}. A destructured re-export snapshots ` +
    `the value at import time, so a lazily-bound export is present and undefined.`,
);

const undef = cjsNames.filter((k) => esm[k] === undefined);
assert.deepEqual(undef, [], `dist/index.mjs exports ${undef.join(', ')} as undefined.`);

assert.equal(esm.default, cjs.nRouter, 'the ESM default export must be the client class');

console.log(`ESM/CJS export parity: PASS (${cjsNames.length} named exports + default)`);
