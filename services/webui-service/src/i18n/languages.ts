import { STORAGE_KEYS } from '@/utils/storageKeys';

export interface SupportedLanguage {
  code: string;
  /** Eigenbezeichnung der Sprache, in jeder Sprache gleich dargestellt (kein Uebersetzungsaufwand pro Sprachpaar). */
  nativeName: string;
}

// Einzige Quelle fuer unterstuetzte Sprachen. Eine neue Sprache ist ein
// Eintrag hier - i18n.ts, der Setup-Wizard und die Admin-Einstellungen lesen
// alle von dieser Liste, statt sie an drei Stellen einzeln zu pflegen.
export const SUPPORTED_LANGUAGES: readonly SupportedLanguage[] = [
  { code: 'de', nativeName: 'Deutsch' },
  { code: 'en', nativeName: 'English' },
];

export const DEFAULT_LANGUAGE = 'en';
export const LANGUAGE_STORAGE_KEY = STORAGE_KEYS.LANGUAGE;

const SUPPORTED_CODES = new Set(SUPPORTED_LANGUAGES.map((l) => l.code));

/** Bildet z. B. "de-DE" auf den unterstuetzten Basis-Code ab, sonst Fallback. */
export function resolveSupportedLanguage(lng: string | null | undefined): string {
  if (!lng) return DEFAULT_LANGUAGE;
  if (SUPPORTED_CODES.has(lng)) return lng;
  const base = lng.split('-')[0];
  return SUPPORTED_CODES.has(base) ? base : DEFAULT_LANGUAGE;
}
