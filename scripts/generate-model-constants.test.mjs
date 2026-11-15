import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  DEFAULT_LANGUAGE_TARGETS,
  deriveConstantName,
  generateModelConstants,
  syncSnapshotFromCatalogPayload,
} from './generate-model-constants.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const SCRIPT_PATH = path.join(ROOT, 'scripts', 'generate-model-constants.mjs');
const SNAPSHOT_PATH = path.join(ROOT, 'spec', 'model-catalog-snapshot.json');
const JS_MODELS_PATH = DEFAULT_LANGUAGE_TARGETS.js;
const PY_MODELS_PATH = DEFAULT_LANGUAGE_TARGETS.py;

// The compatibility baseline is FROZEN: the two files exactly as published before
// constants were generated. Reading the live branch instead would compare the
// generated files with themselves and could never detect a removed or changed value.
const BASELINES = {
  'sdks/js/src/models.ts': path.join(ROOT, 'spec', 'baselines', 'models.ts.before-generation.txt'),
  'sdks/python/nroutersdk/models.py': path.join(ROOT, 'spec', 'baselines', 'models.py.before-generation.txt'),
};

function gitShowHead(relPath) {
  const baseline = BASELINES[relPath];
  assert.ok(baseline, `no frozen baseline for ${relPath}`);
  return fs.readFileSync(baseline, 'utf8');
}

function parseJsConstants(source) {
  const entries = [];
  const re = /^export const (MODEL_[A-Z0-9_]+)\s*=\s*'([^']+)';$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parsePyConstants(source) {
  const entries = [];
  const re = /^(MODEL_[A-Z0-9_]+)\s*=\s*"([^"]+)"$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseRustConstants(source) {
  const entries = [];
  const re = /^pub const (MODEL_[A-Z0-9_]+):\s*&str\s*=\s*"([^"]+)";$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseJavaConstants(source) {
  const entries = [];
  const re = /^\s*public static final String (MODEL_[A-Z0-9_]+)\s*=\s*"([^"]+)";$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseGoConstants(source) {
  const entries = [];
  const re = /^\t(MODEL_[A-Z0-9_]+)\s*=\s*"([^"]+)"$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseKotlinConstants(source) {
  const entries = [];
  const re = /^\s*public const val (MODEL_[A-Z0-9_]+):\s*String\s*=\s*"([^"]+)"$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseSwiftConstants(source) {
  const entries = [];
  const re = /^\s*public static let (MODEL_[A-Z0-9_]+):\s*String\s*=\s*"([^"]+)"$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseDartConstants(source) {
  const entries = [];
  const re = /^\s*static const String (MODEL_[A-Z0-9_]+)\s*=\s*'([^']+)';$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseRConstants(source) {
  const entries = [];
  const re = /^(MODEL_[A-Z0-9_]+)\s*<-\s*"([^"]+)"$/gm;
  for (const m of source.matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseJsModelsMap(source) {
  const constants = Object.fromEntries(parseJsConstants(source));
  const blockMatch = source.match(/export const MODELS\s*=\s*\{([\s\S]*?)\}\s*as const;/);
  assert.ok(blockMatch, 'Expected export const MODELS = { ... } as const; block');
  const entries = [];
  const re = /^\s*([A-Z0-9_]+):\s*(?:(MODEL_[A-Z0-9_]+)|'([^']+)'),\s*$/gm;
  for (const m of blockMatch[1].matchAll(re)) {
    const key = m[1];
    const value = m[2] ? constants[m[2]] : m[3];
    assert.equal(typeof value, 'string', `Unresolved JS MODELS entry for ${key}`);
    entries.push([key, value]);
  }
  return entries;
}

function parsePyModelsMap(source) {
  const constants = Object.fromEntries(parsePyConstants(source));
  const blockMatch = source.match(/MODELS:\s*dict\[str,\s*str\]\s*=\s*\{([\s\S]*?)\}/);
  assert.ok(blockMatch, 'Expected MODELS: dict[str, str] = { ... } block');
  const entries = [];
  const re = /^\s*"([A-Z0-9_]+)":\s*(?:(MODEL_[A-Z0-9_]+)|"([^"]+)"),\s*$/gm;
  for (const m of blockMatch[1].matchAll(re)) {
    const key = m[1];
    const value = m[2] ? constants[m[2]] : m[3];
    assert.equal(typeof value, 'string', `Unresolved Python MODELS entry for ${key}`);
    entries.push([key, value]);
  }
  return entries;
}

function parseRustModelsMap(source) {
  const constants = Object.fromEntries(parseRustConstants(source));
  const blockMatch = source.match(/pub const MODELS:\s*&\[\(&str,\s*&str\)\]\s*=\s*&\[([\s\S]*?)\];/);
  assert.ok(blockMatch, 'Expected pub const MODELS: &[(&str, &str)] block');
  const entries = [];
  const re = /\(\s*"([A-Z0-9_]+)",\s*(?:(MODEL_[A-Z0-9_]+)|"([^"]+)"),?\s*\),/g;
  for (const m of blockMatch[1].matchAll(re)) {
    const key = m[1];
    const value = m[2] ? constants[m[2]] : m[3];
    assert.equal(typeof value, 'string', `Unresolved Rust MODELS entry for ${key}`);
    entries.push([key, value]);
  }
  return entries;
}

function parseJavaModelsMap(source) {
  const constants = Object.fromEntries(parseJavaConstants(source));
  const entries = [];
  const re = /^\s*map\.put\("([A-Z0-9_]+)",\s*(?:(MODEL_[A-Z0-9_]+)|"([^"]+)")\);$/gm;
  for (const m of source.matchAll(re)) {
    const key = m[1];
    const value = m[2] ? constants[m[2]] : m[3];
    assert.equal(typeof value, 'string', `Unresolved Java MODELS entry for ${key}`);
    entries.push([key, value]);
  }
  return entries;
}

function parseGoModelsMap(source) {
  const blockMatch = source.match(/var MODELS = map\[string\]string\{([\s\S]*?)\}/);
  assert.ok(blockMatch, 'Expected var MODELS = map[string]string block');
  const entries = [];
  const re = /^\t"([A-Z0-9_]+)":\s*"([^"]+)",$/gm;
  for (const m of blockMatch[1].matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseKotlinModelsMap(source) {
  const constants = Object.fromEntries(parseKotlinConstants(source));
  const blockMatch = source.match(/public val MODELS:\s*Map<String,\s*String>\s*=\s*mapOf\(([\s\S]*?)\)/);
  assert.ok(blockMatch, 'Expected public val MODELS = mapOf(...) block');
  const entries = [];
  const re = /^\s*"([A-Z0-9_]+)"\s+to\s+(?:(MODEL_[A-Z0-9_]+)|"([^"]+)"),$/gm;
  for (const m of blockMatch[1].matchAll(re)) {
    const key = m[1];
    const value = m[2] ? constants[m[2]] : m[3];
    assert.equal(typeof value, 'string', `Unresolved Kotlin MODELS entry for ${key}`);
    entries.push([key, value]);
  }
  return entries;
}

function parseSwiftModelsMap(source) {
  const blockMatch = source.match(/public static let MODELS:\s*\[String:\s*String\]\s*=\s*\[([\s\S]*?)\]/);
  assert.ok(blockMatch, 'Expected public static let MODELS = [...] block');
  const entries = [];
  const re = /^\s*"([A-Z0-9_]+)":\s*"([^"]+)",$/gm;
  for (const m of blockMatch[1].matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseDartModelsMap(source) {
  const blockMatch = source.match(/static const Map<String,\s*String> MODELS\s*=\s*<String,\s*String>\{([\s\S]*?)\};/);
  assert.ok(blockMatch, 'Expected static const Map<String, String> MODELS block');
  const entries = [];
  const re = /^\s*'([A-Z0-9_]+)':\s*'([^']+)',$/gm;
  for (const m of blockMatch[1].matchAll(re)) entries.push([m[1], m[2]]);
  return entries;
}

function parseRModelsMap(source) {
  const constants = Object.fromEntries(parseRConstants(source));
  const blockMatch = source.match(/NROUTER_MODELS\s*<-\s*list\(([\s\S]*?)\)/);
  assert.ok(blockMatch, 'Expected NROUTER_MODELS <- list(...) block');
  const entries = [];
  const re = /^\s*([A-Z0-9_]+)\s*=\s*(?:(MODEL_[A-Z0-9_]+)|"([^"]+)"),?$/gm;
  for (const m of blockMatch[1].matchAll(re)) {
    const key = m[1];
    const value = m[2] ? constants[m[2]] : m[3];
    assert.equal(typeof value, 'string', `Unresolved R NROUTER_MODELS entry for ${key}`);
    entries.push([key, value]);
  }
  return entries;
}

function withTempDir(fn) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nrouter-sdk-models-'));
  try {
    return fn(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function runCli(args) {
  return spawnSync(process.execPath, [SCRIPT_PATH, ...args], { encoding: 'utf8' });
}

test('pinned snapshot has versioned catalog shape (schema_version, catalog_revision, maker_key, namespace, retired, compat)', () => {
  const raw = JSON.parse(fs.readFileSync(SNAPSHOT_PATH, 'utf8'));
  assert.equal(raw.schema_version, 1);
  assert.equal(typeof raw.catalog_revision, 'number');
  assert.equal(raw.source, '/api/public/models');
  assert.match(raw.version, /^\d{4}-\d{2}-\d{2}$/);
  assert.ok(Array.isArray(raw.models) && raw.models.length >= 27);
  for (const item of raw.models) {
    assert.deepEqual(Object.keys(item).sort(), ['id', 'maker_key', 'namespace', 'retired']);
    assert.equal(typeof item.id, 'string');
    assert.ok(item.namespace === 'canonical' || item.namespace === 'moving');
    assert.equal(typeof item.maker_key, 'string');
    assert.equal(typeof item.retired, 'boolean');
  }
  assert.ok(Array.isArray(raw.compat) && raw.compat.length > 0, 'Expected explicit compat list in snapshot');
  for (const item of raw.compat) {
    assert.deepEqual(Object.keys(item).sort(), ['deprecated', 'name', 'value']);
    assert.equal(typeof item.name, 'string');
    assert.equal(typeof item.value, 'string');
    assert.equal(item.deprecated, true);
  }
  assert.ok(
    raw.compat.some((c) => c.name === 'GEMINI_2_5_FLASH' && c.value === 'gemini-2.5-flash' && c.deprecated === true),
    'compat list must retain GEMINI_2_5_FLASH -> gemini-2.5-flash',
  );
  assert.ok(
    raw.compat.some((c) => c.name === 'GEMINI_2_5_PRO' && c.value === 'gemini-2.5-pro' && c.deprecated === true),
    'compat list must retain GEMINI_2_5_PRO -> gemini-2.5-pro',
  );
});

test('output is deterministic and sorted regardless of input model order', () => {
  const snapshot = JSON.parse(fs.readFileSync(SNAPSHOT_PATH, 'utf8'));
  const existingJs = fs.readFileSync(JS_MODELS_PATH, 'utf8');
  const reversed = {
    schema_version: snapshot.schema_version,
    catalog_revision: snapshot.catalog_revision,
    source: snapshot.source,
    version: snapshot.version,
    models: [...snapshot.models].reverse(),
    compat: [...(snapshot.compat ?? [])].reverse(),
  };

  const first = generateModelConstants(snapshot, { existingJsSource: existingJs });
  const second = generateModelConstants(reversed, { existingJsSource: existingJs });

  assert.equal(first.jsContent, second.jsContent);
  assert.equal(first.pyContent, second.pyContent);
  assert.equal(first.rustContent, second.rustContent);
  assert.equal(first.javaContent, second.javaContent);
  const versionRe = new RegExp(`snapshot version:\\s*${snapshot.version.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`, 'i');
  assert.match(first.jsContent, versionRe);
  assert.match(first.pyContent, versionRe);
  assert.match(first.rustContent, versionRe);
  assert.match(first.javaContent, versionRe);

  const names = parseJsConstants(first.jsContent).map(([k]) => k);
  const sortedNames = [...names].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  assert.deepEqual(names, sortedNames);
});

test('all SDK language targets (JS, Python, Rust, Java, Go, Kotlin, Android, Swift, Dart, R) receive identical constants and MODELS maps', () => {
  const jsSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.js, 'utf8');
  const pySource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.py, 'utf8');
  const rustSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.rust, 'utf8');
  const javaSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.java, 'utf8');
  const goSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.go, 'utf8');
  const kotlinSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.kotlin, 'utf8');
  const androidSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.android, 'utf8');
  const swiftSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.swift, 'utf8');
  const dartSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.dart, 'utf8');
  const rSource = fs.readFileSync(DEFAULT_LANGUAGE_TARGETS.r, 'utf8');

  const snapshot = JSON.parse(fs.readFileSync(SNAPSHOT_PATH, 'utf8'));
  const jsEntries = parseJsConstants(jsSource);
  const jsModels = parseJsModelsMap(jsSource);

  assert.ok(jsEntries.length >= snapshot.models.length, 'JS MODEL_* count must cover snapshot models');
  assert.equal(jsModels.length, jsEntries.length);

  const parsedConstants = {
    py: parsePyConstants(pySource),
    rust: parseRustConstants(rustSource),
    java: parseJavaConstants(javaSource),
    go: parseGoConstants(goSource),
    kotlin: parseKotlinConstants(kotlinSource),
    android: parseKotlinConstants(androidSource),
    swift: parseSwiftConstants(swiftSource),
    dart: parseDartConstants(dartSource),
    r: parseRConstants(rSource),
  };

  const parsedMaps = {
    py: parsePyModelsMap(pySource),
    rust: parseRustModelsMap(rustSource),
    java: parseJavaModelsMap(javaSource),
    go: parseGoModelsMap(goSource),
    kotlin: parseKotlinModelsMap(kotlinSource),
    android: parseKotlinModelsMap(androidSource),
    swift: parseSwiftModelsMap(swiftSource),
    dart: parseDartModelsMap(dartSource),
    r: parseRModelsMap(rSource),
  };

  for (const [lang, entries] of Object.entries(parsedConstants)) {
    assert.deepEqual(entries, jsEntries, `${lang} MODEL_* constants drifted from JS`);
  }
  for (const [lang, mapEntries] of Object.entries(parsedMaps)) {
    assert.deepEqual(mapEntries, jsModels, `${lang} MODELS map drifted from JS`);
  }

  assert.match(jsSource, /export type NRouterModel\b/);
  assert.match(jsSource, /export type NRouterModelList\b/);
  assert.match(jsSource, /export type NRouterCapabilities\b/);
  assert.match(jsSource, /export interface RawRequester\b/);
  assert.match(jsSource, /export class NRouterModels\b/);
  assert.match(jsSource, /export type WellKnownModel\b/);
});

test('constant derivation rule normalizes ids and fails on collisions', () => {
  assert.equal(deriveConstantName('meta/llama-3.3-70b-instruct'), 'MODEL_META_LLAMA_3_3_70B_INSTRUCT');
  assert.equal(deriveConstantName('gpt-5.4-mini'), 'MODEL_GPT_5_4_MINI');

  assert.throws(
    () =>
      generateModelConstants({
        version: '2026-11-11',
        models: [
          { id: 'vendor/alpha-1.0', retired: false },
          { id: 'vendor-alpha_1.0', retired: false },
        ],
      }),
    /collision/i,
  );

  withTempDir((dir) => {
    const snapFile = path.join(dir, 'snap.json');
    fs.writeFileSync(
      snapFile,
      JSON.stringify({
        version: '2026-11-11',
        models: [
          { id: 'acme/x-1', retired: false },
          { id: 'acme_x.1', retired: false },
        ],
      }),
    );
    const res = runCli([
      '--snapshot',
      snapFile,
      '--js-out',
      path.join(dir, 'models.ts'),
      '--py-out',
      path.join(dir, 'models.py'),
    ]);
    assert.notEqual(res.status, 0);
    assert.match(res.stderr, /collision/i);
  });
});

test('retired models carry deprecation markers across JS, Python, Rust, Java, Go, Kotlin, Swift, Dart, and R', () => {
  const out = generateModelConstants({
    schema_version: 1,
    catalog_revision: 42,
    version: '2026-11-11',
    models: [
      { id: 'acme/active-v2', namespace: 'canonical', maker_key: 'acme', retired: false },
      { id: 'acme/retired-v1', namespace: 'canonical', maker_key: 'acme', retired: true },
    ],
  });

  assert.match(out.jsContent, /\/\*\*[^\n]*@deprecated[^\n]*retired[^\n]*\*\/\nexport const MODEL_ACME_RETIRED_V1 = 'acme\/retired-v1';/i);
  assert.doesNotMatch(out.jsContent, /@deprecated[^\n]*\*\/\nexport const MODEL_ACME_ACTIVE_V2/i);

  assert.match(out.pyContent, /#: [^\n]*deprecated[^\n]*retired[^\n]*\nMODEL_ACME_RETIRED_V1 = "acme\/retired-v1"/i);
  assert.doesNotMatch(out.pyContent, /deprecated[^\n]*\nMODEL_ACME_ACTIVE_V2/i);

  assert.match(out.rustContent, /#\[deprecated\(note = "Model 'acme\/retired-v1' is retired\."\)\]\npub const MODEL_ACME_RETIRED_V1: &str = "acme\/retired-v1";/);
  assert.doesNotMatch(out.rustContent, /#\[deprecated[^\n]*\]\npub const MODEL_ACME_ACTIVE_V2/);

  assert.match(out.javaContent, /@Deprecated\n\s+public static final String MODEL_ACME_RETIRED_V1 = "acme\/retired-v1";/);
  assert.doesNotMatch(out.javaContent, /@Deprecated\n\s+public static final String MODEL_ACME_ACTIVE_V2/);

  assert.match(out.goContent, /\/\/ Deprecated: Model 'acme\/retired-v1' is retired\.\n\tMODEL_ACME_RETIRED_V1 = "acme\/retired-v1"/);
  assert.match(out.kotlinContent, /@Deprecated\(message = "Model 'acme\/retired-v1' is retired\."\)\n\s+public const val MODEL_ACME_RETIRED_V1: String = "acme\/retired-v1"/);
  assert.match(out.swiftContent, /@available\(\*, deprecated, message: "Model 'acme\/retired-v1' is retired\."\)\n\s+public static let MODEL_ACME_RETIRED_V1: String = "acme\/retired-v1"/);
  assert.match(out.dartContent, /@Deprecated\('Model \\'acme\/retired-v1\\' is retired\.'\)\n\s+static const String MODEL_ACME_RETIRED_V1 = 'acme\/retired-v1';/);
  assert.match(out.rContent, /# Deprecated: Model 'acme\/retired-v1' is retired\.\nMODEL_ACME_RETIRED_V1 <- "acme\/retired-v1"/);
});

test('syncSnapshotFromCatalogPayload syncs /api/public/models payload, keeps canonical + moving, excludes slug/benchmark, and marks missing entries retired (MCAT-39, MCAT-72)', () => {
  const existing = {
    schema_version: 1,
    catalog_revision: 5,
    source: '/api/public/models',
    version: '2026-11-01',
    models: [
      { id: 'gpt-4o', namespace: 'canonical', maker_key: 'openai', retired: false },
      { id: 'legacy/sunset-v1', namespace: 'canonical', maker_key: 'openai', retired: false },
    ],
    compat: [{ name: 'GPT_4O_LEGACY', value: 'gpt-4o', deprecated: true }],
  };

  const feedPayload = {
    schema_version: 1,
    catalog_revision: 19,
    data: [
      {
        model_id: 'openai/gpt-4o',
        model_name: 'gpt-4o',
        maker: { key: 'openai', name: 'OpenAI' },
        served: true,
        identifiers: [
          { namespace: 'canonical', value: 'gpt-4o' },
          { namespace: 'moving', value: 'gpt-4o-latest' },
          { namespace: 'slug', value: 'openai-gpt-4o-page-slug' },
          { namespace: 'benchmark:lmsys', value: 'gpt-4o-2024-11-20-arena' },
          { namespace: 'listing:openrouter', value: 'openai/gpt-4o-2024' },
        ],
      },
      {
        model_id: 'anthropic/claude-opus-4-8',
        model_name: 'claude-opus-4-8',
        maker_ref: { key: 'anthropic', name: 'Anthropic' },
        served: true,
      },
      {
        model_id: 'nrouter/auto',
        model_name: 'nrouter/auto',
        maker: { key: 'nrouter', name: 'nRouter' },
        served: true,
      },
      {
        model_id: 'openai/unserved-draft',
        model_name: 'gpt-unserved-draft',
        maker: { key: 'openai', name: 'OpenAI' },
        served: false,
      },
    ],
  };

  const synced = syncSnapshotFromCatalogPayload(existing, feedPayload, { version: '2026-11-12' });
  assert.equal(synced.schema_version, 1);
  assert.equal(synced.catalog_revision, 19);
  assert.equal(synced.version, '2026-11-12');
  assert.deepEqual(synced.models, [
    { id: 'claude-opus-4-8', namespace: 'canonical', maker_key: 'anthropic', retired: false },
    { id: 'gpt-4o', namespace: 'canonical', maker_key: 'openai', retired: false },
    { id: 'gpt-4o-latest', namespace: 'moving', maker_key: 'openai', retired: false },
    { id: 'legacy/sunset-v1', namespace: 'canonical', maker_key: 'openai', retired: true },
  ]);
  assert.deepEqual(synced.compat, existing.compat);

  // CLI --sync-from-file writes updated snapshot and regenerates targets cleanly.
  withTempDir((dir) => {
    const snapFile = path.join(dir, 'snapshot.json');
    const feedFile = path.join(dir, 'public-models.json');
    const jsFile = path.join(dir, 'models.ts');
    const pyFile = path.join(dir, 'models.py');
    const rustFile = path.join(dir, 'models.rs');
    const javaFile = path.join(dir, 'NRouterModels.java');

    fs.writeFileSync(snapFile, JSON.stringify(existing, null, 2));
    fs.writeFileSync(feedFile, JSON.stringify(feedPayload, null, 2));
    fs.copyFileSync(JS_MODELS_PATH, jsFile);

    const outArgs = ['--snapshot', snapFile, '--js-out', jsFile, '--py-out', pyFile, '--rust-out', rustFile, '--java-out', javaFile];
    const syncRes = runCli([...outArgs, '--sync-from-file', feedFile, '--version', '2026-11-12']);
    assert.equal(syncRes.status, 0, syncRes.stderr);

    const checkRes = runCli([...outArgs, '--check']);
    assert.equal(checkRes.status, 0, checkRes.stderr);

    const writtenSnap = JSON.parse(fs.readFileSync(snapFile, 'utf8'));
    assert.equal(writtenSnap.catalog_revision, 19);
    assert.ok(writtenSnap.models.some((m) => m.id === 'legacy/sunset-v1' && m.retired === true));
    assert.match(fs.readFileSync(rustFile, 'utf8'), /#\[deprecated\(note = "Model 'legacy\/sunset-v1' is retired\."\)\]/);
    assert.match(fs.readFileSync(javaFile, 'utf8'), /@Deprecated\n\s+public static final String MODEL_LEGACY_SUNSET_V1/);
  });
});

test('syncSnapshotFromCatalogPayload preserves frozen compat constant values when bare canonical ids collide (a208)', () => {
  const existing = {
    schema_version: 1,
    catalog_revision: 1,
    source: '/api/public/models',
    version: '2026-11-11',
    models: [
      { id: 'google/gemini-3.1-flash-lite', namespace: 'canonical', maker_key: 'google', retired: false },
    ],
    compat: [
      { name: 'MODEL_GEMINI_3_1_FLASH_LITE', value: 'google/gemini-3.1-flash-lite', deprecated: true },
    ],
  };

  const feedPayload = {
    catalog_revision: 42,
    data: [
      {
        model_name: 'gemini-3.1-flash-lite',
        maker: { key: 'google', name: 'Google' },
        served: true,
      },
      {
        model_name: 'deepseek-v3.2',
        maker: { key: 'deepseek', name: 'DeepSeek' },
        served: true,
      },
    ],
  };

  const synced = syncSnapshotFromCatalogPayload(existing, feedPayload, { version: '2026-11-14' });
  assert.equal(synced.version, '2026-11-14');
  assert.equal(synced.catalog_revision, 42);
  // Pre-a208 moving alias remains active (not falsely retired) and frozen compat constant never mutates.
  assert.deepEqual(synced.models, [
    { id: 'deepseek-v3.2', namespace: 'canonical', maker_key: 'deepseek', retired: false },
    { id: 'google/gemini-3.1-flash-lite', namespace: 'canonical', maker_key: 'google', retired: false },
  ]);
  assert.deepEqual(synced.compat, existing.compat);
});

test('HEAD constants, MODELS keys, and WellKnownModel literals keep identical values after generation', () => {
  const headJs = gitShowHead('sdks/js/src/models.ts');
  const headPy = gitShowHead('sdks/python/nroutersdk/models.py');
  const genJs = fs.readFileSync(JS_MODELS_PATH, 'utf8');
  const genPy = fs.readFileSync(PY_MODELS_PATH, 'utf8');

  const headJsConsts = Object.fromEntries(parseJsConstants(headJs));
  const headPyConsts = Object.fromEntries(parsePyConstants(headPy));
  const headJsModels = Object.fromEntries(parseJsModelsMap(headJs));
  const headPyModels = Object.fromEntries(parsePyModelsMap(headPy));
  const headWellKnownLiterals = new Set(Object.values(headJsModels));

  const genJsConsts = Object.fromEntries(parseJsConstants(genJs));
  const genPyConsts = Object.fromEntries(parsePyConstants(genPy));
  const genJsModels = Object.fromEntries(parseJsModelsMap(genJs));
  const genPyModels = Object.fromEntries(parsePyModelsMap(genPy));
  const genWellKnownLiterals = new Set(Object.values(genJsModels));

  for (const [name, expectedValue] of Object.entries(headJsConsts)) {
    assert.equal(genJsConsts[name], expectedValue, `JS constant ${name} changed from HEAD`);
    assert.equal(genPyConsts[name], expectedValue, `Python constant ${name} disagrees with JS HEAD`);
  }
  for (const [name, expectedValue] of Object.entries(headPyConsts)) {
    assert.equal(genPyConsts[name], expectedValue, `Python constant ${name} changed from HEAD`);
    assert.equal(genJsConsts[name], expectedValue, `JS constant ${name} disagrees with Python HEAD`);
  }
  for (const [key, expectedValue] of Object.entries(headJsModels)) {
    assert.equal(genJsModels[key], expectedValue, `JS MODELS.${key} changed from HEAD`);
    assert.equal(genPyModels[key], expectedValue, `Python MODELS["${key}"] disagrees with JS HEAD`);
  }
  for (const [key, expectedValue] of Object.entries(headPyModels)) {
    assert.equal(genPyModels[key], expectedValue, `Python MODELS["${key}"] changed from HEAD`);
    assert.equal(genJsModels[key], expectedValue, `JS MODELS.${key} disagrees with Python HEAD`);
  }
  for (const literal of headWellKnownLiterals) {
    assert.ok(
      genWellKnownLiterals.has(literal),
      `WellKnownModel literal "${literal}" from HEAD was dropped after generation`,
    );
  }

  // Rule-derived names exist alongside deprecated compat entries.
  assert.equal(genJsConsts.MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT, 'meta/llama-3.2-11b-vision-instruct');
  assert.equal(genJsConsts.MODEL_CLAUDE_SONNET_4_5_20250929, 'claude-sonnet-4-5-20250929');
  assert.match(genJs, /@deprecated[^\n]*\*\/\nexport const MODEL_META_LLAMA_3_2_11B_VISION\b/);
  assert.match(genJs, /@deprecated[^\n]*\*\/\n\s+GEMINI_2_5_FLASH:\s+'gemini-2\.5-flash',/);
  assert.match(genPy, /#: [^\n]*Deprecated[^\n]*\nMODEL_CLAUDE_SONNET_4_5\b/);
  assert.match(genPy, /#: [^\n]*Deprecated[^\n]*\n\s+"GEMINI_2_5_FLASH":\s+"gemini-2\.5-flash",/);
});

test('--check mode exits 0 when fresh across all SDK targets and exits non-zero when any file is stale', () => {
  const liveCheck = runCli(['--check']);
  assert.equal(liveCheck.status, 0, liveCheck.stderr);

  withTempDir((dir) => {
    const snapFile = path.join(dir, 'snapshot.json');
    const jsFile = path.join(dir, 'models.ts');
    const pyFile = path.join(dir, 'models.py');
    const rustFile = path.join(dir, 'models.rs');
    const javaFile = path.join(dir, 'NRouterModels.java');
    fs.copyFileSync(SNAPSHOT_PATH, snapFile);
    fs.copyFileSync(JS_MODELS_PATH, jsFile);
    fs.copyFileSync(PY_MODELS_PATH, pyFile);
    fs.copyFileSync(DEFAULT_LANGUAGE_TARGETS.rust, rustFile);
    fs.copyFileSync(DEFAULT_LANGUAGE_TARGETS.java, javaFile);

    const args = [
      '--snapshot',
      snapFile,
      '--js-out',
      jsFile,
      '--py-out',
      pyFile,
      '--rust-out',
      rustFile,
      '--java-out',
      javaFile,
    ];
    assert.equal(runCli([...args, '--check']).status, 0);

    const stalePy = fs.readFileSync(pyFile, 'utf8') + '\n# stale edit\n';
    fs.writeFileSync(pyFile, stalePy);
    const staleRes = runCli([...args, '--check']);
    assert.notEqual(staleRes.status, 0);
    assert.equal(fs.readFileSync(pyFile, 'utf8'), stalePy, '--check must not overwrite files');

    fs.copyFileSync(PY_MODELS_PATH, pyFile);
    const staleRust = fs.readFileSync(rustFile, 'utf8') + '\n// stale rust edit\n';
    fs.writeFileSync(rustFile, staleRust);
    assert.notEqual(runCli([...args, '--check']).status, 0);

    fs.copyFileSync(DEFAULT_LANGUAGE_TARGETS.rust, rustFile);
    const currentVersion = JSON.parse(fs.readFileSync(SNAPSHOT_PATH, 'utf8')).version;
    const staleJs = fs.readFileSync(jsFile, 'utf8').replace(currentVersion, '2025-01-01');
    fs.writeFileSync(jsFile, staleJs);
    assert.notEqual(runCli(['--check', ...args]).status, 0);
  });
});

test('generated Go and Rust sources are natively gofmt- and rustfmt-clean', () => {
  const snapshot = JSON.parse(fs.readFileSync(SNAPSHOT_PATH, 'utf8'));
  const existingJs = fs.readFileSync(JS_MODELS_PATH, 'utf8');
  const generated = generateModelConstants(snapshot, { existingJsSource: existingJs });

  const gofmt = spawnSync('gofmt', [], { input: generated.goContent, encoding: 'utf8' });
  if (gofmt.status === 0) {
    assert.equal(generated.goContent, gofmt.stdout, 'renderGoFile must emit exact gofmt column alignment');
  }

  const rustfmt = spawnSync('rustfmt', ['--edition', '2021'], { input: generated.rustContent, encoding: 'utf8' });
  if (rustfmt.status === 0) {
    assert.equal(generated.rustContent, rustfmt.stdout, 'renderRustModule must emit exact rustfmt attribute wrapping');
  }
});
