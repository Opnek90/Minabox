#!/usr/bin/env node
// Prueft t()-Aufrufe mit statischem Key-Argument gegen die echten Keys in
// public/locales/de/*.json - eine Textsuche, kein Typsystem.
//
// Warum kein TypeScript-CustomTypeOptions-Ansatz: admin.json hat 560+ Keys,
// von hunderten t()-Aufrufstellen im Projekt referenziert. Jede Kombination
// aus "mind. ein Namespace strikt typisiert" liess tsc --noEmit auf der Ziel-
// Hardware (Raspberry Pi, 3.7 GB RAM) ueber zwei Minuten laufen oder den
// Speicher sprengen - unabhaengig davon, ob die Keys als verschachtelter
// `typeof json`- oder als flacher Record-Typ eingebracht wurden. Nur eine
// generische `Record<string, string>`-Signatur (= keine echte Pruefung) blieb
// schnell. Diese Textsuche leistet denselben Fang von Tippfehlern/toten Keys
// in t()-Aufrufen ohne den Compiler zu belasten.
//
// Erkennt: t('key'), t("key"), t(`key`) (ohne ${}-Interpolation), auch mit
// zweitem Options-Argument. Ueberspringt dynamische Keys (t(`foo.${bar}`),
// t(variable)) - die kann nur eine Typpruefung oder Laufzeit abdecken, siehe
// die Kommentare in i18n/index.ts zum failedLoading-Handler als Netz dafuer.

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

// Erkennt useTranslation('ns') oder useTranslation(['ns', ...]) - das erste
// Element gilt als Default-Namespace fuer unpraefixierte Keys in der Datei.
const USE_TRANSLATION_RE = /useTranslation\(\s*\[?\s*['"]([a-z]+)['"]/;

// t('key') / t("key") / t(`key`) als erstes Argument, ohne ${...} darin.
const T_CALL_RE = /\bt\(\s*(['"`])((?:(?!\1)[^\\]|\\.)*)\1/g;

// { ns: 'xxx' } als (Teil eines) zweiten Arguments - explizite Namespace-
// Ueberschreibung, wie an vielen Stellen fuer gemeinsame Labels ('save' etc.)
// aus common.json genutzt.
const NS_OPTION_RE = /ns:\s*['"]([a-z]+)['"]/;

// Ein "_one"/"_other"-Paar wird ueber den Basisnamen aufgerufen (t('x.y',
// {count})); der Basisname selbst ist dann kein eigener Key in der JSON.
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
    if (raw.includes('${')) continue; // dynamischer Key, nicht statisch pruefbar
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
      // Rest der Zeile nach dem Key-Argument auf { ns: '...' } absuchen -
      // reicht fuer den ueblichen Fall "t('key', { ns: 'xxx' })" auf einer Zeile.
      const lineEnd = text.indexOf('\n', m.index);
      const window = text.slice(m.index, lineEnd === -1 ? m.index + 200 : lineEnd);
      const nsOption = NS_OPTION_RE.exec(window);
      if (nsOption && namespaces.includes(nsOption[1])) {
        ns = nsOption[1];
      }
    }

    if (!namespaces.includes(ns)) continue; // unbekannter Namespace -> nicht unser Fall
    if (!existsAsKey(ns, key)) {
      const line = text.slice(0, m.index).split('\n').length;
      const rel = path.slice(ROOT.length + 1);
      console.error(`FEHLER ${rel}:${line} - Key "${raw}" existiert nicht in ${ns}.json`);
      errorCount++;
    }
  }
}

if (errorCount > 0) {
  console.error(`\n${errorCount} t()-Aufruf(e) mit nicht existierendem Key.`);
  process.exit(1);
}

console.log(`i18n-Aufruf-Pruefung ok: ${files.length} Dateien, keine toten Keys in statischen t()-Aufrufen.`);
