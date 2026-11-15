#!/usr/bin/env node
/**
 * Generate multi-language SDK model constants from `spec/model-catalog-snapshot.json`,
 * and sync `spec/model-catalog-snapshot.json` from the versioned `/api/public/models`
 * catalog snapshot format (`MCAT-39`, `Decision 6=A`).
 *
 * Constant naming rule: `MODEL_` + uppercase model `id` with non-alphanumerics -> `_`.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..');
const DEFAULT_SNAPSHOT_PATH = path.join(REPO_ROOT, 'spec', 'model-catalog-snapshot.json');

export const DEFAULT_LANGUAGE_TARGETS = Object.freeze({
  js: path.join(REPO_ROOT, 'sdks', 'js', 'src', 'models.ts'),
  py: path.join(REPO_ROOT, 'sdks', 'python', 'nroutersdk', 'models.py'),
  rust: path.join(REPO_ROOT, 'sdks', 'rust', 'src', 'models.rs'),
  java: path.join(REPO_ROOT, 'sdks', 'java', 'src', 'main', 'java', 'ai', 'nrouter', 'sdk', 'NRouterModels.java'),
  go: path.join(REPO_ROOT, 'sdks', 'go', 'models.go'),
  kotlin: path.join(REPO_ROOT, 'sdks', 'kotlin', 'src', 'main', 'kotlin', 'ai', 'nrouter', 'sdk', 'Models.kt'),
  android: path.join(REPO_ROOT, 'sdks', 'android', 'src', 'main', 'kotlin', 'ai', 'nrouter', 'sdk', 'android', 'Models.kt'),
  swift: path.join(REPO_ROOT, 'sdks', 'swift', 'Sources', 'NRouter', 'Models.swift'),
  dart: path.join(REPO_ROOT, 'sdks', 'dart', 'lib', 'src', 'models.dart'),
  r: path.join(REPO_ROOT, 'sdks', 'r', 'R', 'models_catalog.R'),
});

const JS_BEGIN_MARKER = '// BEGIN GENERATED: model-catalog-snapshot';
const JS_END_MARKER = '// END GENERATED: model-catalog-snapshot';

const VALID_CALLABLE_NAMESPACES = new Set(['canonical', 'moving']);
const MAKER_KEY_RE = /^[a-z0-9][a-z0-9_-]*$/;

const compareAscii = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

function assertSafeValue(value, label) {
  if (typeof value !== 'string' || value.trim() === '' || value.trim() !== value) {
    throw new Error(`Invalid ${label}: ${JSON.stringify(value)}`);
  }
  if (/[\x00-\x1f\x7f]/.test(value) || value.includes('*/')) {
    throw new Error(`Unsafe characters in ${label}: ${JSON.stringify(value)}`);
  }
}

/** Derive `MODEL_*` from a model id: uppercase, non-alphanumerics -> `_`, `MODEL_` prefix. */
export function deriveConstantName(id) {
  assertSafeValue(id, 'model id');
  const stem = id.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  if (!stem) throw new Error(`Model id ${JSON.stringify(id)} contains no alphanumeric characters`);
  return `MODEL_${stem}`;
}

export function validateSnapshot(snapshot) {
  if (typeof snapshot !== 'object' || snapshot === null || Array.isArray(snapshot)) {
    throw new Error('Snapshot must be a JSON object.');
  }
  if (typeof snapshot.version !== 'string' || !/^[A-Za-z0-9._-]+$/.test(snapshot.version)) {
    throw new Error(`Invalid snapshot version: ${JSON.stringify(snapshot.version)}`);
  }
  if (snapshot.schema_version !== undefined) {
    if (!Number.isInteger(snapshot.schema_version) || snapshot.schema_version < 1) {
      throw new Error(`Invalid snapshot schema_version: ${JSON.stringify(snapshot.schema_version)}`);
    }
  }
  if (snapshot.catalog_revision !== undefined) {
    const revOk =
      (Number.isInteger(snapshot.catalog_revision) && snapshot.catalog_revision >= 0) ||
      (typeof snapshot.catalog_revision === 'string' && /^[A-Za-z0-9._-]+$/.test(snapshot.catalog_revision));
    if (!revOk) {
      throw new Error(`Invalid snapshot catalog_revision: ${JSON.stringify(snapshot.catalog_revision)}`);
    }
  }
  if (snapshot.source !== undefined) {
    assertSafeValue(snapshot.source, 'snapshot source');
  }
  if (!Array.isArray(snapshot.models)) throw new Error('Snapshot "models" field must be an array.');
  const seenIds = new Set();
  for (const entry of snapshot.models) {
    if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
      throw new Error('Each snapshot model entry must be an object.');
    }
    assertSafeValue(entry.id, 'model id');
    if (typeof entry.retired !== 'boolean') {
      throw new Error(`Snapshot model "${entry.id}" must have a boolean "retired" field.`);
    }
    if (entry.namespace !== undefined && !VALID_CALLABLE_NAMESPACES.has(entry.namespace)) {
      throw new Error(
        `Snapshot model "${entry.id}" has invalid callable namespace ${JSON.stringify(entry.namespace)}; expected "canonical" or "moving".`,
      );
    }
    if (entry.maker_key !== undefined && entry.maker_key !== null) {
      if (typeof entry.maker_key !== 'string' || !MAKER_KEY_RE.test(entry.maker_key)) {
        throw new Error(`Snapshot model "${entry.id}" has invalid maker_key ${JSON.stringify(entry.maker_key)}.`);
      }
    }
    if (seenIds.has(entry.id)) throw new Error(`Duplicate model id in snapshot (collision): "${entry.id}"`);
    seenIds.add(entry.id);
  }
  if (snapshot.compat !== undefined) {
    if (!Array.isArray(snapshot.compat)) throw new Error('Snapshot "compat" field must be an array when provided.');
    const seenCompatNames = new Set();
    for (const item of snapshot.compat) {
      if (typeof item !== 'object' || item === null || Array.isArray(item)) {
        throw new Error('Each snapshot compat entry must be an object.');
      }
      if (typeof item.name !== 'string' || !/^[A-Z][A-Z0-9_]*$/.test(item.name)) {
        throw new Error(`Invalid compat entry name: ${JSON.stringify(item.name)}`);
      }
      assertSafeValue(item.value, `compat value for ${item.name}`);
      if (typeof item.deprecated !== 'boolean') {
        throw new Error(`Compat entry "${item.name}" must have a boolean "deprecated" field.`);
      }
      if (seenCompatNames.has(item.name)) throw new Error(`Duplicate compat entry name (collision): "${item.name}"`);
      seenCompatNames.add(item.name);
    }
  }
}

function normalizeMakerKey(row) {
  const raw =
    (row?.maker && typeof row.maker === 'object' ? row.maker.key : null) ??
    (row?.maker_ref && typeof row.maker_ref === 'object' ? row.maker_ref.key : null) ??
    (typeof row?.maker_key === 'string' ? row.maker_key : null);
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim().toLowerCase();
  return MAKER_KEY_RE.test(trimmed) ? trimmed : null;
}

function isInternalRouterId(id) {
  const lower = id.toLowerCase();
  return lower === 'nrouter/auto' || lower.startsWith('nrouter/');
}

/**
 * Sync a pinned `model-catalog-snapshot.json` object from a `/api/public/models`
 * catalog payload (`MCAT-39`, `MCAT-72`, `Decision 6=A`).
 *
 * Rules:
 *  - Preserves `schema_version`, `catalog_revision`, `version`, and `compat`.
 *  - Admits ONLY callable identifiers (`canonical` and `moving`); `slug` and
 *    external association identifiers (`benchmark:*`, `listing:*`) are excluded.
 *  - Preserves every previously-published model in `existingSnapshot.models` that
 *    is missing from the live feed by marking it `retired: true`, so existing SDK
 *    constants become `@deprecated` / `Deprecated` instead of breaking callers.
 */
export function syncSnapshotFromCatalogPayload(existingSnapshot, payload, options = {}) {
  const base = existingSnapshot ?? { schema_version: 1, catalog_revision: 1, version: '2026-11-11', models: [], compat: [] };
  validateSnapshot(base);

  if (typeof payload !== 'object' || payload === null) {
    throw new Error('Catalog payload must be a JSON object or array.');
  }
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload.data)
      ? payload.data
      : Array.isArray(payload.models)
        ? payload.models
        : null;
  if (!rows) {
    throw new Error('Catalog payload must carry a "data" or "models" array.');
  }

  const compatModelValuesByConst = new Map();
  for (const item of base.compat ?? []) {
    if (item && typeof item.name === 'string' && item.name.startsWith('MODEL_') && typeof item.value === 'string') {
      compatModelValuesByConst.set(item.name, item.value);
    }
  }

  const byId = new Map();
  for (const prev of base.models) {
    byId.set(prev.id, {
      id: prev.id,
      namespace: prev.namespace ?? 'canonical',
      maker_key: prev.maker_key ?? null,
      retired: true,
    });
  }

  for (const row of rows) {
    if (typeof row !== 'object' || row === null) continue;
    if (row.served === false) continue;

    const makerKey = normalizeMakerKey(row);
    const rowRetired = Boolean(row.retired === true || row.lifecycle === 'retired');

    const canonicalId =
      (typeof row.canonical_model_name === 'string' && row.canonical_model_name.trim()) ||
      (typeof row.model_name === 'string' && row.model_name.trim()) ||
      (typeof row.id === 'string' && (!row.namespace || row.namespace === 'canonical') ? row.id.trim() : '');

    const candidateEntries = [];
    if (canonicalId && (options.includeRouterIds === true || !isInternalRouterId(canonicalId))) {
      candidateEntries.push({ id: canonicalId, namespace: 'canonical' });
    } else if (typeof row.id === 'string' && row.namespace === 'moving') {
      const movingId = row.id.trim();
      if (movingId && (options.includeRouterIds === true || !isInternalRouterId(movingId))) {
        candidateEntries.push({ id: movingId, namespace: 'moving' });
      }
    }

    if (Array.isArray(row.moving_aliases)) {
      for (const alias of row.moving_aliases) {
        if (typeof alias === 'string' && alias.trim() !== '') {
          const trimmed = alias.trim();
          if (options.includeRouterIds === true || !isInternalRouterId(trimmed)) {
            candidateEntries.push({ id: trimmed, namespace: 'moving' });
          }
        }
      }
    }

    if (Array.isArray(row.identifiers)) {
      for (const ident of row.identifiers) {
        if (typeof ident !== 'object' || ident === null) continue;
        // MCAT-72: only canonical and moving namespaces are callable SDK constants.
        if (!VALID_CALLABLE_NAMESPACES.has(ident.namespace)) continue;
        const value = typeof ident.value === 'string' ? ident.value.trim() : typeof ident.id === 'string' ? ident.id.trim() : '';
        if (!value) continue;
        if (options.includeRouterIds !== true && isInternalRouterId(value)) continue;
        candidateEntries.push({ id: value, namespace: ident.namespace });
      }
    }

    for (const candidate of candidateEntries) {
      assertSafeValue(candidate.id, 'catalog model id');
      const derivedConst = deriveConstantName(candidate.id);
      const frozenCompatValue = compatModelValuesByConst.get(derivedConst);
      if (frozenCompatValue && frozenCompatValue !== candidate.id) {
        // Semver compatibility (a208): when a frozen compat `MODEL_*` constant already binds
        // `derivedConst` to its pre-a208 moving alias (`google/gemini-*`), never mutate the
        // published constant's string value; keep the moving alias active alongside it.
        const compatModel = byId.get(frozenCompatValue);
        if (compatModel) {
          byId.set(frozenCompatValue, {
            ...compatModel,
            maker_key: makerKey ?? compatModel.maker_key ?? null,
            retired: rowRetired,
          });
        }
        continue;
      }
      const prev = byId.get(candidate.id);
      byId.set(candidate.id, {
        id: candidate.id,
        namespace: candidate.namespace === 'canonical' || prev?.namespace === 'canonical' ? 'canonical' : 'moving',
        maker_key: makerKey ?? prev?.maker_key ?? null,
        retired: rowRetired,
      });
    }
  }

  const schemaVersion =
    !Array.isArray(payload) && Number.isInteger(payload.schema_version) && payload.schema_version >= 1
      ? payload.schema_version
      : base.schema_version ?? 1;

  const catalogRevision =
    !Array.isArray(payload) &&
    ((Number.isInteger(payload.catalog_revision) && payload.catalog_revision >= 0) ||
      (typeof payload.catalog_revision === 'string' && /^[A-Za-z0-9._-]+$/.test(payload.catalog_revision)))
      ? payload.catalog_revision
      : base.catalog_revision ?? 1;

  const version =
    options.version ??
    (!Array.isArray(payload) && typeof payload.version === 'string' && /^[A-Za-z0-9._-]+$/.test(payload.version)
      ? payload.version
      : base.version);

  const synced = {
    schema_version: schemaVersion,
    catalog_revision: catalogRevision,
    source: '/api/public/models',
    version,
    models: [...byId.values()].sort((a, b) => compareAscii(a.id, b.id)),
    ...(base.compat ? { compat: [...base.compat].sort((a, b) => compareAscii(a.name, b.name)) } : {}),
  };

  validateSnapshot(synced);
  // Also prove no constant-name collisions were introduced by the sync.
  buildConstantEntries(synced);
  return synced;
}

export function buildConstantEntries(snapshot) {
  validateSnapshot(snapshot);
  const sortedModels = [...snapshot.models].sort((a, b) => compareAscii(a.id, b.id));
  const sortedCompat = [...(snapshot.compat ?? [])].sort((a, b) => compareAscii(a.name, b.name));

  const canonicalByModelId = new Map();
  const constantsByName = new Map();
  const mapEntriesByKey = new Map();

  const registerConstant = (entry) => {
    const existing = constantsByName.get(entry.constantName);
    if (existing) {
      throw new Error(`Constant name collision: "${existing.id}" and "${entry.id}" both map to ${entry.constantName}`);
    }
    constantsByName.set(entry.constantName, entry);
  };

  for (const model of sortedModels) {
    const constantName = deriveConstantName(model.id);
    const keyName = constantName.slice('MODEL_'.length);
    registerConstant({
      constantName,
      keyName,
      id: model.id,
      namespace: model.namespace ?? 'canonical',
      makerKey: model.maker_key ?? null,
      retired: model.retired,
      deprecated: model.retired,
      canonicalName: null,
    });
    canonicalByModelId.set(model.id, { constantName, keyName, retired: model.retired });
    mapEntriesByKey.set(keyName, {
      keyName,
      constantName,
      value: model.id,
      retired: model.retired,
      deprecated: false,
      canonicalKeyName: null,
    });
  }

  for (const item of sortedCompat) {
    if (!item.name.startsWith('MODEL_')) continue;
    const constantName = item.name;
    const keyName = constantName.slice('MODEL_'.length);
    const canonical = canonicalByModelId.get(item.value) ?? null;
    const retired = canonical ? canonical.retired : false;
    registerConstant({
      constantName,
      keyName,
      id: item.value,
      namespace: 'compat',
      makerKey: null,
      retired,
      deprecated: Boolean(item.deprecated || retired),
      canonicalName: canonical ? canonical.constantName : null,
    });
    if (!mapEntriesByKey.has(keyName)) {
      mapEntriesByKey.set(keyName, {
        keyName,
        constantName,
        value: item.value,
        retired,
        deprecated: false,
        canonicalKeyName: canonical ? canonical.keyName : null,
      });
    }
  }

  for (const item of sortedCompat) {
    if (item.name.startsWith('MODEL_')) continue;
    const keyName = item.name;
    const prefixed = `MODEL_${keyName}`;
    const existingConst = constantsByName.get(prefixed) ?? null;
    const canonical =
      canonicalByModelId.get(item.value) ??
      (existingConst?.canonicalName ? { keyName: existingConst.canonicalName.slice('MODEL_'.length) } : null);
    const matchesConst = existingConst !== null && existingConst.id === item.value;
    mapEntriesByKey.set(keyName, {
      keyName,
      constantName: matchesConst ? prefixed : null,
      value: item.value,
      retired: existingConst ? existingConst.retired : false,
      deprecated: Boolean(item.deprecated),
      canonicalKeyName: canonical ? canonical.keyName : null,
    });
  }

  return {
    constants: [...constantsByName.values()].sort((a, b) => compareAscii(a.constantName, b.constantName)),
    mapEntries: [...mapEntriesByKey.values()].sort((a, b) => compareAscii(a.keyName, b.keyName)),
  };
}

function snapshotHeaderMeta(snapshot) {
  const parts = [`snapshot version: ${snapshot.version}`];
  if (snapshot.schema_version !== undefined) parts.push(`schema_version: ${snapshot.schema_version}`);
  if (snapshot.catalog_revision !== undefined) parts.push(`catalog_revision: ${snapshot.catalog_revision}`);
  return parts.join(', ');
}

function deprecationMessage(e) {
  if (e.retired && e.canonicalName) {
    return `Model '${e.id}' is retired; compatibility alias for ${e.canonicalName}.`;
  }
  if (e.retired) {
    return `Model '${e.id}' is retired.`;
  }
  if (e.deprecated && e.canonicalName) {
    return `Compatibility alias; use ${e.canonicalName} instead.`;
  }
  if (e.deprecated) {
    return `Compatibility alias for '${e.id}'.`;
  }
  return null;
}

const escapeSingleQuote = (v) => v.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
const escapeDoubleQuote = (v) => v.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
const formatJsKey = (k) => (/^[A-Z_$][A-Z0-9_$]*$/i.test(k) ? k : `'${escapeSingleQuote(k)}'`);

function renderJsBlock(snapshot, { constants, mapEntries }) {
  const lines = [
    JS_BEGIN_MARKER,
    `// Generated from spec/model-catalog-snapshot.json (${snapshotHeaderMeta(snapshot)}).`,
    '// Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.',
    '// Naming rule: `MODEL_` + uppercase model id with non-alphanumeric runs replaced by `_`.',
    '',
  ];
  for (const e of constants) {
    if (e.retired && e.canonicalName) {
      lines.push(`/** @deprecated Model \`${e.id}\` is retired; compatibility alias for \`${e.canonicalName}\`. */`);
    } else if (e.retired) {
      lines.push(`/** @deprecated Model \`${e.id}\` is retired. */`);
    } else if (e.deprecated && e.canonicalName) {
      lines.push(`/** @deprecated Compatibility alias; use \`${e.canonicalName}\` instead. */`);
    } else if (e.deprecated) {
      lines.push(`/** @deprecated Compatibility alias for \`${e.id}\`. */`);
    }
    lines.push(`export const ${e.constantName} = '${escapeSingleQuote(e.id)}';`);
  }
  lines.push('', 'export const MODELS = {');
  for (const e of mapEntries) {
    if (e.deprecated) {
      const hint = e.canonicalKeyName
        ? `Compatibility alias; use \`${e.canonicalKeyName}\` instead.`
        : `Compatibility alias for \`${e.value}\`.`;
      lines.push(`  /** @deprecated ${hint} */`);
    }
    lines.push(`  ${formatJsKey(e.keyName)}: ${e.constantName ?? `'${escapeSingleQuote(e.value)}'`},`);
  }
  lines.push('} as const;', '', 'export type WellKnownModel = (typeof MODELS)[keyof typeof MODELS];', JS_END_MARKER);
  return lines.join('\n');
}

function injectJsBlock(existingJsSource, generatedBlock) {
  if (!existingJsSource) return `${generatedBlock}\n`;
  const beginIdx = existingJsSource.indexOf(JS_BEGIN_MARKER);
  const endIdx = existingJsSource.indexOf(JS_END_MARKER);
  if (beginIdx !== -1 && endIdx !== -1 && beginIdx < endIdx) {
    return `${existingJsSource.slice(0, beginIdx)}${generatedBlock}${existingJsSource.slice(endIdx + JS_END_MARKER.length)}`;
  }
  throw new Error('Cannot locate generated model constants markers in TypeScript target file.');
}

function renderPythonModule(snapshot, { constants, mapEntries }) {
  const lines = [
    `"""Model constants generated from spec/model-catalog-snapshot.json (${snapshotHeaderMeta(snapshot)}).`,
    '',
    'Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.',
    'Naming rule: `MODEL_` + uppercase model id with non-alphanumeric runs replaced by `_`.',
    '"""',
    '',
    'from __future__ import annotations',
    '',
  ];
  for (const e of constants) {
    if (e.retired && e.canonicalName) {
      lines.push(`#: Deprecated: model '${e.id}' is retired; compatibility alias for ${e.canonicalName}.`);
    } else if (e.retired) {
      lines.push(`#: Deprecated: model '${e.id}' is retired.`);
    } else if (e.deprecated && e.canonicalName) {
      lines.push(`#: Deprecated compatibility alias; use ${e.canonicalName} instead.`);
    } else if (e.deprecated) {
      lines.push(`#: Deprecated compatibility alias for '${e.id}'.`);
    }
    lines.push(`${e.constantName} = ${JSON.stringify(e.id)}`);
  }
  lines.push('', 'MODELS: dict[str, str] = {');
  for (const e of mapEntries) {
    if (e.deprecated) {
      const hint = e.canonicalKeyName
        ? `Deprecated compatibility alias; use ${e.canonicalKeyName} instead.`
        : `Deprecated compatibility alias for '${e.value}'.`;
      lines.push(`    #: ${hint}`);
    }
    lines.push(`    ${JSON.stringify(e.keyName)}: ${e.constantName ?? JSON.stringify(e.value)},`);
  }
  lines.push('}', '', '__all__ = [', '    "MODELS",');
  for (const e of constants) lines.push(`    ${JSON.stringify(e.constantName)},`);
  lines.push(']', '');
  return lines.join('\n');
}

function renderRustModule(snapshot, { constants, mapEntries }) {
  const lines = [
    `//! Model constants generated from \`spec/model-catalog-snapshot.json\` (${snapshotHeaderMeta(snapshot)}).`,
    '//!',
    '//! Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.',
    '//! Naming rule: `MODEL_` + uppercase model id with non-alphanumeric runs replaced by `_`.',
    '',
  ];
  for (const e of constants) {
    const msg = deprecationMessage(e);
    if (msg) {
      lines.push(`/// Deprecated: ${msg}`);
      const singleLineAttr = `#[deprecated(note = "${escapeDoubleQuote(msg)}")]`;
      if (singleLineAttr.length > 100) {
        lines.push('#[deprecated(', `    note = "${escapeDoubleQuote(msg)}"`, ')]');
      } else {
        lines.push(singleLineAttr);
      }
    } else {
      lines.push(`/// Canonical identifier \`${e.id}\`.`);
    }
    const singleLineConst = `pub const ${e.constantName}: &str = "${escapeDoubleQuote(e.id)}";`;
    if (singleLineConst.length > 100) {
      lines.push(`pub const ${e.constantName}: &str =`, `    "${escapeDoubleQuote(e.id)}";`);
    } else {
      lines.push(singleLineConst);
    }
  }
  lines.push(
    '',
    '/// Sorted `(key, model_id)` directory matching `MODELS` across every nRouter SDK.',
    '#[allow(deprecated)]',
    'pub const MODELS: &[(&str, &str)] = &[',
  );
  for (const e of mapEntries) {
    const rhs = e.constantName ?? `"${escapeDoubleQuote(e.value)}"`;
    const tupleExpr = `("${escapeDoubleQuote(e.keyName)}", ${rhs})`;
    if (tupleExpr.length > 62) {
      lines.push('    (', `        "${escapeDoubleQuote(e.keyName)}",`, `        ${rhs},`, '    ),');
    } else {
      lines.push(`    ${tupleExpr},`);
    }
  }
  lines.push(
    '];',
    '',
    '/// Look up a model identifier in [`MODELS`] by short key (for example `"GPT_5_4_MINI"`).',
    'pub fn model_id(key: &str) -> Option<&\'static str> {',
    '    MODELS',
    '        .binary_search_by_key(&key, |(k, _)| *k)',
    '        .ok()',
    '        .map(|idx| MODELS[idx].1)',
    '}',
    '',
  );
  return lines.join('\n');
}

function renderJavaClass(snapshot, { constants, mapEntries }) {
  const lines = [
    'package ai.nrouter.sdk;',
    '',
    'import java.util.Collections;',
    'import java.util.LinkedHashMap;',
    'import java.util.Map;',
    '',
    '/**',
    ` * Model constants generated from {@code spec/model-catalog-snapshot.json} (${snapshotHeaderMeta(snapshot)}).`,
    ' *',
    ' * <p>Do not edit by hand; run {@code node scripts/generate-model-constants.mjs} to regenerate.',
    ' * Naming rule: {@code MODEL_} + uppercase model id with non-alphanumeric runs replaced by {@code _}.',
    ' */',
    'public final class NRouterModels {',
    '',
    '    private NRouterModels() {',
    '    }',
    '',
  ];
  for (const e of constants) {
    const msg = deprecationMessage(e);
    if (msg) {
      lines.push(`    /** @deprecated ${msg} */`);
      lines.push('    @Deprecated');
    }
    lines.push(`    public static final String ${e.constantName} = "${escapeDoubleQuote(e.id)}";`);
  }
  lines.push(
    '',
    '    /** Unmodifiable map of well-known model keys matching {@code MODELS} across all nRouter SDKs. */',
    '    public static final Map<String, String> MODELS = buildModels();',
    '',
    '    @SuppressWarnings("deprecation")',
    '    private static Map<String, String> buildModels() {',
    '        Map<String, String> map = new LinkedHashMap<>();',
  );
  for (const e of mapEntries) {
    const rhs = e.constantName ?? `"${escapeDoubleQuote(e.value)}"`;
    lines.push(`        map.put("${escapeDoubleQuote(e.keyName)}", ${rhs});`);
  }
  lines.push('        return Collections.unmodifiableMap(map);', '    }', '}', '');
  return lines.join('\n');
}

function renderGoFile(snapshot, { constants, mapEntries }) {
  const lines = [
    `// Code generated from spec/model-catalog-snapshot.json (${snapshotHeaderMeta(snapshot)}); DO NOT EDIT.`,
    '// Run `node scripts/generate-model-constants.mjs` to regenerate.',
    '',
    'package nrouter',
    '',
    'const (',
  ];
  let constGroup = [];
  const flushConstGroup = () => {
    if (constGroup.length === 0) return;
    const maxNameLen = Math.max(...constGroup.map((item) => item.constantName.length));
    for (const item of constGroup) {
      lines.push(`\t${item.constantName.padEnd(maxNameLen, ' ')} = "${escapeDoubleQuote(item.id)}"`);
    }
    constGroup = [];
  };
  for (const e of constants) {
    const msg = deprecationMessage(e);
    if (msg) {
      flushConstGroup();
      lines.push(`\t// ${e.constantName} is retained for compatibility.`);
      lines.push('\t//');
      lines.push(`\t// Deprecated: ${msg}`);
    }
    constGroup.push(e);
  }
  flushConstGroup();
  lines.push(')', '', '// MODELS maps each short constant key to its wire model identifier.', 'var MODELS = map[string]string{');
  const log2ish = (x) => {
    const e = Math.floor(Math.log2(x)) + 1;
    const f = x / 2 ** e;
    return e + 2 * (f - 1);
  };
  const exp2ish = (x) => {
    const n = Math.floor(x);
    return (1 + (x - n)) * 2 ** n;
  };
  let mapGroup = [];
  const flushMapGroup = () => {
    if (mapGroup.length === 0) return;
    const maxMapLhsLen = Math.max(...mapGroup.map((p) => p.lhs.length));
    for (const p of mapGroup) {
      lines.push(`\t${p.lhs.padEnd(maxMapLhsLen + 1, ' ')}${p.rhs}`);
    }
    mapGroup = [];
  };
  let prevSize = 0;
  let log2sum = 0;
  let count = 0;
  for (let i = 0; i < mapEntries.length; i += 1) {
    const e = mapEntries[i];
    const keyLit = `"${escapeDoubleQuote(e.keyName)}"`;
    const size = keyLit.length;
    if (i > 0) {
      const smallSize = 40;
      let useFF = true;
      if (count === 0 || (prevSize <= smallSize && size <= smallSize)) {
        useFF = false;
      } else {
        const r = 2.5;
        const geomean = exp2ish(log2sum / count);
        const ratio = size / geomean;
        useFF = r * ratio <= 1 || r <= ratio;
      }
      if (useFF) flushMapGroup();
    }
    mapGroup.push({ lhs: `${keyLit}:`, rhs: `"${escapeDoubleQuote(e.value)}",` });
    log2sum += log2ish(size);
    count += 1;
    prevSize = size;
  }
  flushMapGroup();
  lines.push('}', '');
  return lines.join('\n');
}

function renderKotlinFile(snapshot, { constants, mapEntries }, pkgName) {
  const lines = [
    `// Generated from spec/model-catalog-snapshot.json (${snapshotHeaderMeta(snapshot)}).`,
    '// Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.',
    `package ${pkgName}`,
    '',
    '/** Generated well-known nRouter model constants. */',
    'public object NRouterModels {',
  ];
  for (const e of constants) {
    const msg = deprecationMessage(e);
    if (msg) {
      if (e.canonicalName) {
        lines.push(`    @Deprecated(message = "${escapeDoubleQuote(msg)}", replaceWith = ReplaceWith("NRouterModels.${e.canonicalName}"))`);
      } else {
        lines.push(`    @Deprecated(message = "${escapeDoubleQuote(msg)}")`);
      }
    }
    lines.push(`    public const val ${e.constantName}: String = "${escapeDoubleQuote(e.id)}"`);
  }
  lines.push(
    '',
    '    /** Unmodifiable map of well-known model keys matching `MODELS` across all nRouter SDKs. */',
    '    @Suppress("DEPRECATION")',
    '    public val MODELS: Map<String, String> = mapOf(',
  );
  for (const e of mapEntries) {
    const rhs = e.constantName ?? `"${escapeDoubleQuote(e.value)}"`;
    lines.push(`        "${escapeDoubleQuote(e.keyName)}" to ${rhs},`);
  }
  lines.push('    )', '}', '');
  return lines.join('\n');
}

function renderSwiftFile(snapshot, { constants, mapEntries }) {
  const lines = [
    `// Generated from spec/model-catalog-snapshot.json (${snapshotHeaderMeta(snapshot)}).`,
    '// Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.',
    '',
    '/// Generated well-known nRouter model constants.',
    'public enum NRouterModels {',
  ];
  for (const e of constants) {
    const msg = deprecationMessage(e);
    if (msg) {
      if (e.canonicalName) {
        lines.push(`    @available(*, deprecated, renamed: "${e.canonicalName}", message: "${escapeDoubleQuote(msg)}")`);
      } else {
        lines.push(`    @available(*, deprecated, message: "${escapeDoubleQuote(msg)}")`);
      }
    }
    lines.push(`    public static let ${e.constantName}: String = "${escapeDoubleQuote(e.id)}"`);
  }
  lines.push(
    '',
    '    /// Map of well-known model keys matching `MODELS` across all nRouter SDKs.',
    '    public static let MODELS: [String: String] = [',
  );
  for (const e of mapEntries) {
    lines.push(`        "${escapeDoubleQuote(e.keyName)}": "${escapeDoubleQuote(e.value)}",`);
  }
  lines.push('    ]', '}', '');
  return lines.join('\n');
}

function renderDartFile(snapshot, { constants, mapEntries }) {
  const lines = [
    '// ignore_for_file: constant_identifier_names',
    `// Generated from spec/model-catalog-snapshot.json (${snapshotHeaderMeta(snapshot)}).`,
    '// Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.',
    '',
    '/// Generated well-known nRouter model constants.',
    'class NRouterModels {',
    '  const NRouterModels._();',
    '',
  ];
  for (const e of constants) {
    const msg = deprecationMessage(e);
    if (msg) {
      lines.push(`  @Deprecated('${escapeSingleQuote(msg)}')`);
    }
    lines.push(`  static const String ${e.constantName} = '${escapeSingleQuote(e.id)}';`);
  }
  lines.push(
    '',
    '  /// Constant map of well-known model keys matching `MODELS` across all nRouter SDKs.',
    '  static const Map<String, String> MODELS = <String, String>{',
  );
  for (const e of mapEntries) {
    lines.push(`    '${escapeSingleQuote(e.keyName)}': '${escapeSingleQuote(e.value)}',`);
  }
  lines.push('  };', '}', '');
  return lines.join('\n');
}

function renderRFile(snapshot, { constants, mapEntries }) {
  const lines = [
    `# Generated from spec/model-catalog-snapshot.json (${snapshotHeaderMeta(snapshot)}).`,
    '# Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.',
    '',
  ];
  for (const e of constants) {
    const msg = deprecationMessage(e);
    if (msg) {
      lines.push(`# Deprecated: ${msg}`);
    }
    lines.push(`${e.constantName} <- "${escapeDoubleQuote(e.id)}"`);
  }
  lines.push('', 'NROUTER_MODELS <- list(');
  mapEntries.forEach((e, idx) => {
    const comma = idx + 1 < mapEntries.length ? ',' : '';
    if (e.deprecated) {
      const hint = e.canonicalKeyName
        ? `Deprecated compatibility alias; use ${e.canonicalKeyName} instead.`
        : `Deprecated compatibility alias for '${e.value}'.`;
      lines.push(`  # ${hint}`);
    }
    lines.push(`  ${e.keyName} = ${e.constantName ?? `"${escapeDoubleQuote(e.value)}"`}${comma}`);
  });
  lines.push(')', '');
  return lines.join('\n');
}

export function generateModelConstants(snapshot, options = {}) {
  const built = buildConstantEntries(snapshot);
  const jsBlock = renderJsBlock(snapshot, built);
  const jsContent = injectJsBlock(options.existingJsSource ?? '', jsBlock);
  const pyContent = renderPythonModule(snapshot, built);
  const rustContent = renderRustModule(snapshot, built);
  const javaContent = renderJavaClass(snapshot, built);
  const goContent = renderGoFile(snapshot, built);
  const kotlinContent = renderKotlinFile(snapshot, built, 'ai.nrouter.sdk');
  const androidContent = renderKotlinFile(snapshot, built, 'ai.nrouter.sdk.android');
  const swiftContent = renderSwiftFile(snapshot, built);
  const dartContent = renderDartFile(snapshot, built);
  const rContent = renderRFile(snapshot, built);
  return {
    entries: built.constants,
    mapEntries: built.mapEntries,
    jsContent,
    pyContent,
    rustContent,
    javaContent,
    goContent,
    kotlinContent,
    androidContent,
    swiftContent,
    dartContent,
    rContent,
  };
}

const TARGET_CONTENT_KEYS = Object.freeze({
  js: 'jsContent',
  py: 'pyContent',
  rust: 'rustContent',
  java: 'javaContent',
  go: 'goContent',
  kotlin: 'kotlinContent',
  android: 'androidContent',
  swift: 'swiftContent',
  dart: 'dartContent',
  r: 'rContent',
});

const OUT_FLAG_TO_LANG = Object.freeze({
  '--js-out': 'js',
  '--py-out': 'py',
  '--rust-out': 'rust',
  '--java-out': 'java',
  '--go-out': 'go',
  '--kotlin-out': 'kotlin',
  '--android-out': 'android',
  '--swift-out': 'swift',
  '--dart-out': 'dart',
  '--r-out': 'r',
});

function parseArgs(argv) {
  const explicitTargets = {};
  const opts = {
    snapshotPath: DEFAULT_SNAPSHOT_PATH,
    targets: null,
    check: false,
    syncFromFile: null,
    syncFromUrl: null,
    version: null,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--check') {
      opts.check = true;
    } else if (arg === '--snapshot' && argv[i + 1]) {
      opts.snapshotPath = path.resolve(argv[++i]);
    } else if (arg === '--sync-from-file' && argv[i + 1]) {
      opts.syncFromFile = path.resolve(argv[++i]);
    } else if (arg === '--sync-from-url' && argv[i + 1]) {
      opts.syncFromUrl = argv[++i];
    } else if (arg === '--version' && argv[i + 1]) {
      opts.version = argv[++i];
    } else if (Object.prototype.hasOwnProperty.call(OUT_FLAG_TO_LANG, arg) && argv[i + 1]) {
      explicitTargets[OUT_FLAG_TO_LANG[arg]] = path.resolve(argv[++i]);
    } else {
      throw new Error(`Unknown or incomplete CLI argument: ${arg}`);
    }
  }
  opts.targets = Object.keys(explicitTargets).length > 0 ? explicitTargets : { ...DEFAULT_LANGUAGE_TARGETS };
  return opts;
}

export async function run(argv) {
  const opts = parseArgs(argv);
  let snapshot = JSON.parse(fs.readFileSync(opts.snapshotPath, 'utf8'));

  if (opts.syncFromFile || opts.syncFromUrl) {
    if (opts.check) {
      throw new Error('Cannot combine --check with --sync-from-file or --sync-from-url.');
    }
    let payload;
    if (opts.syncFromFile) {
      payload = JSON.parse(fs.readFileSync(opts.syncFromFile, 'utf8'));
    } else {
      const response = await fetch(opts.syncFromUrl, { headers: { Accept: 'application/json' } });
      if (!response.ok) {
        throw new Error(`Failed to fetch catalog payload from ${opts.syncFromUrl}: HTTP ${response.status}`);
      }
      payload = await response.json();
    }
    snapshot = syncSnapshotFromCatalogPayload(snapshot, payload, {
      ...(opts.version ? { version: opts.version } : {}),
    });
    fs.writeFileSync(opts.snapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`, 'utf8');
  }

  const jsPath = opts.targets.js;
  const existingJs = jsPath && fs.existsSync(jsPath) ? fs.readFileSync(jsPath, 'utf8') : '';
  const generated = generateModelConstants(snapshot, { existingJsSource: existingJs });

  if (opts.check) {
    const stale = [];
    for (const [lang, targetPath] of Object.entries(opts.targets)) {
      const expected = generated[TARGET_CONTENT_KEYS[lang]];
      const current = fs.existsSync(targetPath) ? fs.readFileSync(targetPath, 'utf8') : null;
      if (current === null || current !== expected) {
        stale.push(targetPath);
      }
    }
    if (stale.length > 0) {
      process.stderr.write(
        `Stale generated model constants (${stale.join(', ')}); run node scripts/generate-model-constants.mjs\n`,
      );
      return 1;
    }
    return 0;
  }

  for (const [lang, targetPath] of Object.entries(opts.targets)) {
    const content = generated[TARGET_CONTENT_KEYS[lang]];
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.writeFileSync(targetPath, content, 'utf8');
  }
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = await run(process.argv.slice(2));
  } catch (err) {
    process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
    process.exitCode = 1;
  }
}
