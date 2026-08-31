#!/usr/bin/env node
// Checks the i18n resources under public/locales against four failure patterns:
//   1. de/en drift: a key is missing in one of the two languages
//   2. incomplete plural forms: `_one` without `_other` (or vice versa) and the
//      dead i18next v3 suffix `_plural`
//   3. keys that are no longer referenced anywhere in the source
//   4. errors/: drift against the error codes the backend actually sends
//
// 1 and 2 are hard errors (exit code 1). 3 can be a false positive due to
// dynamic key construction (t(`foo.${bar}`)) and is therefore only a warning.
//
// On 4: the errors namespace is exempt from check 3. Its keys are named like
// the `code` fields of the backend errors and are looked up exclusively
// dynamically (translateApiError in utils/apiError.ts) - to check 3 all 120
// look dead, which buried the actually dead keys of the other namespaces under
// 100 lines of noise. Instead this compares against the codes in the Python
// source. That catches the reverse gap too: a backend error without a
// translation shows the user "An error occurred". For actually wrong/mistyped
// keys in t() calls see check-i18n-calls.mjs - the TypeScript type system can
// no longer do that at this codebase size (see the comment there).

import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const LOCALES_DIR = join(ROOT, 'public/locales');
const SRC_DIR = join(ROOT, 'src');
const SERVICES_DIR = join(ROOT, '..');
// Looked up exclusively dynamically, see the header comment.
const DYNAMIC_NS = 'errors';
// Keys that do not come from the backend: the frontend's own or a fallback.
const FRONTEND_ERROR_KEYS = new Set(['generic_error', 'invalid_url']);
const LANGUAGES = ['de', 'en'];
const PLURAL_SUFFIXES = ['_zero', '_one', '_two', '_few', '_many', '_other'];

let hasError = false;
const warnings = [];

function flatten(obj, prefix = '') {
  const out = {};
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(out, flatten(value, path));
    } else {
      out[path] = value;
    }
  }
  return out;
}

function collectSourceFiles(dir) {
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectSourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith('.test.tsx') && !entry.name.endsWith('.test.ts')) {
      files.push(full);
    }
  }
  return files;
}

function collectPythonFiles(dir) {
  const files = [];
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return files;
  }
  for (const entry of entries) {
    // tests/ stays out: it holds invented codes (test_failed) as placeholders
    // that never reach a user.
    if (
      entry.name === 'node_modules' ||
      entry.name === '.venv' ||
      entry.name === 'tests' ||
      entry.name.startsWith('.')
    ) {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectPythonFiles(full));
    } else if (entry.name.endsWith('.py')) {
      files.push(full);
    }
  }
  return files;
}

const namespaces = readdirSync(join(LOCALES_DIR, LANGUAGES[0]))
  .filter((f) => f.endsWith('.json'))
  .map((f) => f.replace(/\.json$/, ''))
  .sort();

const resources = {};
for (const ns of namespaces) {
  resources[ns] = {};
  for (const lng of LANGUAGES) {
    const path = join(LOCALES_DIR, lng, `${ns}.json`);
    resources[ns][lng] = flatten(JSON.parse(readFileSync(path, 'utf-8')));
  }
}

// ── 1. de/en-Drift ───────────────────────────────────────────────────────
for (const ns of namespaces) {
  const [a, b] = LANGUAGES;
  const keysA = new Set(Object.keys(resources[ns][a]));
  const keysB = new Set(Object.keys(resources[ns][b]));
  const onlyA = [...keysA].filter((k) => !keysB.has(k));
  const onlyB = [...keysB].filter((k) => !keysA.has(k));
  for (const k of onlyA) {
    console.error(`ERROR [${ns}] key "${k}" missing in ${b}.json`);
    hasError = true;
  }
  for (const k of onlyB) {
    console.error(`ERROR [${ns}] key "${k}" missing in ${a}.json`);
    hasError = true;
  }
}

// ── 2. Plural forms ─────────────────────────────────────────────────────
for (const ns of namespaces) {
  for (const lng of LANGUAGES) {
    const keys = resources[ns][lng];
    for (const key of Object.keys(keys)) {
      if (key.endsWith('_plural')) {
        console.error(`ERROR [${ns}/${lng}] key "${key}" uses the dead i18next v3 suffix "_plural" (since i18next v4: "_one"/"_other")`);
        hasError = true;
      }
    }
    // For every "_one" key there must be an "_other" counterpart, and vice versa
    const bases = new Set();
    for (const key of Object.keys(keys)) {
      for (const suffix of PLURAL_SUFFIXES) {
        if (key.endsWith(suffix)) {
          bases.add(key.slice(0, -suffix.length));
        }
      }
    }
    for (const base of bases) {
      const hasOne = `${base}_one` in keys;
      const hasOther = `${base}_other` in keys;
      if (hasOne !== hasOther) {
        console.error(`ERROR [${ns}/${lng}] plural base "${base}" has only ${hasOne ? '"_one"' : '"_other"'}, the other one is missing`);
        hasError = true;
      }
    }
  }
}

// ── 3. Dead keys (warning, not a hard error) ───────────────────────────
const sourceFiles = collectSourceFiles(SRC_DIR);
const sourceBlob = sourceFiles.map((f) => readFileSync(f, 'utf-8')).join('\n');

for (const ns of namespaces) {
  if (ns === DYNAMIC_NS) continue;
  const keys = Object.keys(resources[ns][LANGUAGES[0]]);
  for (const key of keys) {
    if (sourceBlob.includes(key)) continue;
    // Dynamische Keys (t(`foo.${bar}`)) referenzieren nur ein Praefix -
    // ein Treffer auf irgendeiner Ebene zaehlt als "in Benutzung".
    const parts = key.split('.');
    const prefixHit = parts.some((_, i) => sourceBlob.includes(parts.slice(0, i + 1).join('.')));
    if (!prefixHit) {
      warnings.push(`[${ns}] key "${key}" is no longer referenced in the source`);
    }
  }
}

// ── 4. errors/ gegen die Codes des Backends ─────────────────────────────
const backendCodes = new Set();
for (const file of collectPythonFiles(SERVICES_DIR)) {
  const text = readFileSync(file, 'utf-8');
  for (const m of text.matchAll(/\b(?:code|error_code)\s*=\s*"([a-z0-9_]+)"/g)) {
    backendCodes.add(m[1]);
  }
}

if (backendCodes.size === 0) {
  // Without the services alongside (e.g. a partial checkout) every key would
  // be "unknown" - then better to report nothing than everything.
  console.warn('\nNote: no Python sources found, errors/ was not checked against the backend.');
} else {
  const errorKeys = Object.keys(resources[DYNAMIC_NS][LANGUAGES[0]]);
  for (const key of errorKeys) {
    if (backendCodes.has(key) || FRONTEND_ERROR_KEYS.has(key)) continue;
    warnings.push(`[${DYNAMIC_NS}] key "${key}" no longer belongs to any backend error code`);
  }
  for (const code of [...backendCodes].sort()) {
    if (!(code in resources[DYNAMIC_NS][LANGUAGES[0]])) {
      console.error(`ERROR [${DYNAMIC_NS}] the backend sends "${code}" but there is no translation - the user sees "generic_error"`);
      hasError = true;
    }
  }
}

if (warnings.length > 0) {
  console.warn(`\n${warnings.length} possibly unused keys (please check, dynamic keys produce false positives):`);
  for (const w of warnings) console.warn('  ' + w);
}

if (hasError) {
  console.error('\ni18n check failed.');
  process.exit(1);
}

console.log(`i18n check ok: ${namespaces.length} namespaces, ${LANGUAGES.join('/')} in sync, plural forms complete.`);
