#!/usr/bin/env node
/**
 * Merge public/locales/<lng>/admin/*.json into public/locales/<lng>/admin.json
 * (deep merge). Run before build so the app still loads a single admin.json.
 */
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');
const localesDir = join(root, 'public', 'locales');

function deepMerge(target, source) {
  for (const key of Object.keys(source)) {
    if (
      source[key] &&
      typeof source[key] === 'object' &&
      !Array.isArray(source[key]) &&
      target[key] &&
      typeof target[key] === 'object' &&
      !Array.isArray(target[key])
    ) {
      deepMerge(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

for (const lng of ['de', 'en']) {
  const adminDir = join(localesDir, lng, 'admin');
  if (!existsSync(adminDir)) continue;
  const files = readdirSync(adminDir).filter((f) => f.endsWith('.json'));
  const merged = {};
  for (const f of files.sort()) {
    const path = join(adminDir, f);
    const data = JSON.parse(readFileSync(path, 'utf8'));
    deepMerge(merged, data);
  }
  const outPath = join(localesDir, lng, 'admin.json');
  writeFileSync(outPath, JSON.stringify(merged, null, 2) + '\n', 'utf8');
  console.log(`Merged ${lng}/admin/*.json -> ${lng}/admin.json`);
}
console.log('Merge done.');
