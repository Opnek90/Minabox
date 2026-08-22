#!/usr/bin/env node
// Prueft die i18n-Ressourcen unter public/locales gegen drei Fehlerbilder:
//   1. de/en-Drift: ein Key fehlt in einer der beiden Sprachen
//   2. unvollstaendige Pluralformen: `_one` ohne `_other` (oder umgekehrt)
//      und das tote i18next-v3-Suffix `_plural`
//   3. Keys, die im Quellcode nirgends mehr referenziert werden
//
// 1 und 2 sind harte Fehler (Exit-Code 1). 3 kann durch dynamische
// Key-Konstruktion (t(`foo.${bar}`)) falsch-positiv sein und wird deshalb nur
// als Warnung ausgegeben.

import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const LOCALES_DIR = join(ROOT, 'public/locales');
const SRC_DIR = join(ROOT, 'src');
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
    console.error(`FEHLER [${ns}] Key "${k}" fehlt in ${b}.json`);
    hasError = true;
  }
  for (const k of onlyB) {
    console.error(`FEHLER [${ns}] Key "${k}" fehlt in ${a}.json`);
    hasError = true;
  }
}

// ── 2. Pluralformen ──────────────────────────────────────────────────────
for (const ns of namespaces) {
  for (const lng of LANGUAGES) {
    const keys = resources[ns][lng];
    for (const key of Object.keys(keys)) {
      if (key.endsWith('_plural')) {
        console.error(`FEHLER [${ns}/${lng}] Key "${key}" nutzt das tote i18next-v3-Suffix "_plural" (seit i18next v4: "_one"/"_other")`);
        hasError = true;
      }
    }
    // Fuer jeden "_one"-Key muss ein "_other"-Pendant existieren, und umgekehrt
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
        console.error(`FEHLER [${ns}/${lng}] Plural-Basis "${base}" hat nur ${hasOne ? '"_one"' : '"_other"'}, das jeweils andere fehlt`);
        hasError = true;
      }
    }
  }
}

// ── 3. Tote Keys (Warnung, kein harter Fehler) ──────────────────────────
const sourceFiles = collectSourceFiles(SRC_DIR);
const sourceBlob = sourceFiles.map((f) => readFileSync(f, 'utf-8')).join('\n');

for (const ns of namespaces) {
  const keys = Object.keys(resources[ns][LANGUAGES[0]]);
  for (const key of keys) {
    if (sourceBlob.includes(key)) continue;
    // Dynamische Keys (t(`foo.${bar}`)) referenzieren nur ein Praefix -
    // ein Treffer auf irgendeiner Ebene zaehlt als "in Benutzung".
    const parts = key.split('.');
    const prefixHit = parts.some((_, i) => sourceBlob.includes(parts.slice(0, i + 1).join('.')));
    if (!prefixHit) {
      warnings.push(`[${ns}] Key "${key}" wird im Quellcode nicht mehr referenziert`);
    }
  }
}

if (warnings.length > 0) {
  console.warn(`\n${warnings.length} moeglicherweise ungenutzte Keys (bitte pruefen, dynamische Keys erzeugen falsch-positive Treffer):`);
  for (const w of warnings) console.warn('  ' + w);
}

if (hasError) {
  console.error('\ni18n-Pruefung fehlgeschlagen.');
  process.exit(1);
}

console.log(`i18n-Pruefung ok: ${namespaces.length} Namespaces, ${LANGUAGES.join('/')} synchron, Pluralformen vollstaendig.`);
