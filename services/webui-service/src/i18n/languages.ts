import { STORAGE_KEYS } from '@/utils/storageKeys';

export interface SupportedLanguage {
  code: string;
  /** The language's own name, shown the same in every language (no per-pair translation effort). */
  nativeName: string;
}

// The single source for supported languages. A new language is an entry here -
// i18n.ts, the setup wizard and the admin settings all read from this list
// instead of maintaining it separately in three places.
export const SUPPORTED_LANGUAGES: readonly SupportedLanguage[] = [
  { code: 'de', nativeName: 'Deutsch' },
  { code: 'en', nativeName: 'English' },
];

export const DEFAULT_LANGUAGE = 'en';
export const LANGUAGE_STORAGE_KEY = STORAGE_KEYS.LANGUAGE;

const SUPPORTED_CODES = new Set(SUPPORTED_LANGUAGES.map((l) => l.code));

/** Maps e.g. "de-DE" to the supported base code, otherwise the fallback. */
export function resolveSupportedLanguage(lng: string | null | undefined): string {
  if (!lng) return DEFAULT_LANGUAGE;
  if (SUPPORTED_CODES.has(lng)) return lng;
  const base = lng.split('-')[0];
  return SUPPORTED_CODES.has(base) ? base : DEFAULT_LANGUAGE;
}
