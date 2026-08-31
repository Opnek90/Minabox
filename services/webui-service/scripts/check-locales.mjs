#!/usr/bin/env node
// Prueft die i18n-Ressourcen unter public/locales gegen drei Fehlerbilder:
//   1. de/en-Drift: ein Key fehlt in einer der beiden Sprachen
//   2. unvollstaendige Pluralformen: `_one` ohne `_other` (oder umgekehrt)
//      und das tote i18next-v3-Suffix `_plural`
//   3. Keys, die im Quellcode nirgends mehr referenziert werden
//   4. errors/: Drift gegen die Fehlercodes, die das Backend tatsaechlich sendet
//
// 1 und 2 sind harte Fehler (Exit-Code 1). 3 kann durch dynamische
// Key-Konstruktion (t(`foo.${bar}`)) falsch-positiv sein und wird deshalb nur
// als Warnung ausgegeben.
//
// Zu 4: Der errors-Namensraum wird von Pruefung 3 ausgenommen. Seine Keys
// heissen wie die `code`-Felder der Backend-Fehler und werden ausschliesslich
// dynamisch nachgeschlagen (translateApiError in utils/apiError.ts) - fuer
// Pruefung 3 sehen alle 120 tot aus, was die tatsaechlich toten Keys der
// anderen Namensraeume unter 100 Zeilen Rauschen begraben hat. Stattdessen
// wird hier gegen die Codes im Python-Quelltext verglichen. Das findet die
// umgekehrte Luecke gleich mit: ein Backend-Fehler ohne Uebersetzung erscheint
// dem Nutzer als "Ein Fehler ist aufgetreten". Fuer tatsaechlich falsche/getippte Keys in t()-
// Aufrufen siehe check-i18n-calls.mjs - das TypeScript-Typsystem kann das auf
// dieser Codebase-Groesse nicht mehr leisten (siehe dortiger Kommentar).

import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const LOCALES_DIR = join(ROOT, 'public/locales');
const SRC_DIR = join(ROOT, 'src');
const SERVICES_DIR = join(ROOT, '..');
// Ausschliesslich dynamisch nachgeschlagen, siehe Kopfkommentar.
const DYNAMIC_NS = 'errors';
// Keys, die nicht vom Backend kommen: Eigenbau des Frontends oder Rueckfall.
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
    // tests/ bleibt draussen: dort stehen erfundene Codes (test_failed) als
    // Platzhalter, die nie einen Nutzer erreichen.
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
  if (ns === DYNAMIC_NS) continue;
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

// ── 4. errors/ gegen die Codes des Backends ─────────────────────────────
const backendCodes = new Set();
for (const file of collectPythonFiles(SERVICES_DIR)) {
  const text = readFileSync(file, 'utf-8');
  for (const m of text.matchAll(/\b(?:code|error_code)\s*=\s*"([a-z0-9_]+)"/g)) {
    backendCodes.add(m[1]);
  }
}

if (backendCodes.size === 0) {
  // Ohne die Dienste daneben (z. B. ein ausgecheckter Teilbaum) waere jeder
  // Key "unbekannt" - dann lieber gar nichts melden als alles.
  console.warn('\nHinweis: keine Python-Quellen gefunden, errors/ wurde nicht gegen das Backend geprueft.');
} else {
  const errorKeys = Object.keys(resources[DYNAMIC_NS][LANGUAGES[0]]);
  for (const key of errorKeys) {
    if (backendCodes.has(key) || FRONTEND_ERROR_KEYS.has(key)) continue;
    warnings.push(`[${DYNAMIC_NS}] Key "${key}" gehoert zu keinem Fehlercode des Backends mehr`);
  }
  for (const code of [...backendCodes].sort()) {
    if (!(code in resources[DYNAMIC_NS][LANGUAGES[0]])) {
      console.error(`FEHLER [${DYNAMIC_NS}] Backend sendet "${code}", es gibt aber keine Uebersetzung - der Nutzer sieht "generic_error"`);
      hasError = true;
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
