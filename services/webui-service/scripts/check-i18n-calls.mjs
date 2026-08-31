#!/usr/bin/env node
// Checks t() calls with a static key argument against the real keys in
// public/locales/de/*.json - a text search, not a type system.
//
// Why not a TypeScript CustomTypeOptions approach: admin.json has 560+ keys,
// referenced from hundreds of t() call sites in the project. Every combination
// of "at least one namespace strictly typed" made tsc --noEmit run for over
// two minutes on the target hardware (Raspberry Pi, 3.7 GB RAM) or blow the
// memory - regardless of whether the keys were brought in as a nested
// `typeof json` type or a flat record type. Only a generic
// `Record<string, string>` signature (= no real check) stayed fast. This text
// search achieves the same catch of typos/dead keys in t() calls without
// loading the compiler.
//
// Recognises: t('key'), t("key"), t(`key`) (without ${} interpolation), also
// with a second options argument. Skips dynamic keys (t(`foo.${bar}`),
// t(variable)) - those can only be covered by a type check or at runtime, see
// the comments in i18n/index.ts on the failedLoading handler as the net for
// that.

import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const LOCALES_DIR = join(ROOT, 'public/locales/de');
const SRC_DIR = join(ROOT, 'src');

function flatten(obj, prefix = '') {
  const out = new Set();
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const k of flatten(value, path)) out.add(k);
    } else {
      out.add(path);
    }
  }
  return out;
}

const namespaces = readdirSync(LOCALES_DIR)
  .filter((f) => f.endsWith('.json'))
  .map((f) => f.replace(/\.json$/, ''))
  .sort();

const keysByNs = {};
for (const ns of namespaces) {
  keysByNs[ns] = flatten(JSON.parse(readFileSync(join(LOCALES_DIR, `${ns}.json`), 'utf-8')));
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

// Recognises useTranslation('ns') or useTranslation(['ns', ...]) - the first
// element counts as the default namespace for unprefixed keys in the file.
const USE_TRANSLATION_RE = /useTranslation\(\s*\[?\s*['"]([a-z]+)['"]/;

// t('key') / t("key") / t(`key`) as the first argument, without ${...} in it.
const T_CALL_RE = /\bt\(\s*(['"`])((?:(?!\1)[^\\]|\\.)*)\1/g;

// { ns: 'xxx' } as (part of) a second argument - an explicit namespace
// override, as used in many places for shared labels ('save' etc.) from
// common.json.
const NS_OPTION_RE = /ns:\s*['"]([a-z]+)['"]/;

// An "_one"/"_other" pair is called via the base name (t('x.y', {count}));
// the base name itself is then not a key of its own in the JSON.
const PLURAL_SUFFIXES = ['_zero', '_one', '_two', '_few', '_many', '_other'];
function existsAsKey(ns, key) {
  if (keysByNs[ns].has(key)) return true;
  return PLURAL_SUFFIXES.some((s) => keysByNs[ns].has(`${key}${s}`));
}

let errorCount = 0;
const files = collectSourceFiles(SRC_DIR);

for (const path of files) {
  const text = readFileSync(path, 'utf-8');
  const nsMatch = USE_TRANSLATION_RE.exec(text);
  const defaultNs = nsMatch ? nsMatch[1] : 'common';

  let m;
  T_CALL_RE.lastIndex = 0;
  while ((m = T_CALL_RE.exec(text))) {
    const raw = m[2];
    if (raw.includes('${')) continue; // dynamic key, not statically checkable
    if (raw === '') continue;

    let ns = defaultNs;
    let key = raw;
    if (raw.includes(':')) {
      const idx = raw.indexOf(':');
      const maybeNs = raw.slice(0, idx);
      if (namespaces.includes(maybeNs)) {
        ns = maybeNs;
        key = raw.slice(idx + 1);
      }
    } else {
      // Scan the rest of the line after the key argument for { ns: '...' } -
      // enough for the usual case "t('key', { ns: 'xxx' })" on one line.
      const lineEnd = text.indexOf('\n', m.index);
      const window = text.slice(m.index, lineEnd === -1 ? m.index + 200 : lineEnd);
      const nsOption = NS_OPTION_RE.exec(window);
      if (nsOption && namespaces.includes(nsOption[1])) {
        ns = nsOption[1];
      }
    }

    if (!namespaces.includes(ns)) continue; // unknown namespace -> not our case
    if (!existsAsKey(ns, key)) {
      const line = text.slice(0, m.index).split('\n').length;
      const rel = path.slice(ROOT.length + 1);
      console.error(`ERROR ${rel}:${line} - key "${raw}" does not exist in ${ns}.json`);
      errorCount++;
    }
  }
}

if (errorCount > 0) {
  console.error(`\n${errorCount} t() call(s) with a non-existent key.`);
  process.exit(1);
}

console.log(`i18n call check ok: ${files.length} files, no dead keys in static t() calls.`);
