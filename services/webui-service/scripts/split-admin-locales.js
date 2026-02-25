#!/usr/bin/env node
/**
 * One-time migration: read public/locales/<lng>/admin.json and split into
 * public/locales/<lng>/admin/*.json (tabs, auth, design, stats, system, general, audio, leds, buttons, display, rfid).
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');
const localesDir = join(root, 'public', 'locales');

const sections = [
  { file: 'tabs', keys: ['title', 'tabs'] },
  { file: 'auth', keys: ['auth'] },
  { file: 'design', keys: ['design'] },
  { file: 'stats', keys: ['stats'] },
  { file: 'system', keys: ['system'] },
  { file: 'general', keys: ['general'] },
  { file: 'audio', keys: ['audio'] },
  { file: 'leds', keys: ['leds'] },
  { file: 'buttons', keys: ['buttons'] },
  { file: 'display', keys: ['display'] },
  { file: 'rfid', keys: ['rfid'] },
];

for (const lng of ['de', 'en']) {
  const adminPath = join(localesDir, lng, 'admin.json');
  if (!existsSync(adminPath)) continue;
  const admin = JSON.parse(readFileSync(adminPath, 'utf8'));
  const adminDir = join(localesDir, lng, 'admin');
  mkdirSync(adminDir, { recursive: true });

  for (const { file, keys } of sections) {
    const obj = {};
    for (const k of keys) {
      if (admin[k] !== undefined) obj[k] = admin[k];
    }
    const outPath = join(adminDir, `${file}.json`);
    writeFileSync(outPath, JSON.stringify(obj, null, 2) + '\n', 'utf8');
    console.log(`Wrote ${lng}/admin/${file}.json`);
  }
}
console.log('Split done.');
