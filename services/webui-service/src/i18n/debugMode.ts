import { configApi } from '@/api/config';
import i18n from './index';

// i18next is initialised once at startup - before the first API call is
// through. So the log level is not known at that point yet. Hence two phases:
//
//   Phase 1 (i18n/index.ts): fallbackLng: 'en', saveMissing: false - the
//     existing behaviour, unchanged for end users.
//   Phase 2 (here): as soon as GET /config/general has resolved and log_level
//     reports "debug", turn off the fallback and make missing keys visible.
//
// For any other log level it stays with the English fallback - production is
// never affected.

let applied = false;

/**
 * Turns off the i18n fallback at log level "debug".
 *
 * While `fallbackLng: 'en'` applies, a missing key silently falls back to the
 * English value (or, if not there either, the raw key) - an incomplete
 * translation still looks correct in the UI. With the fallback off, i18next
 * renders the raw key ("media.tracks.play") and additionally calls the
 * missingKeyHandler, which writes a console warning with the namespace and key
 * path.
 *
 * The default language on first load stays English, independent of the log
 * level (that controls `DEFAULT_LANGUAGE`, not the fallback).
 */
export function applyI18nDebugMode(logLevel: string | null | undefined): void {
  if (applied || logLevel !== 'debug') return;
  applied = true;

  i18n.options.fallbackLng = false;
  i18n.options.saveMissing = true;
  i18n.options.missingKeyHandler = (lngs, ns, key) => {
    const lng = Array.isArray(lngs) ? lngs.join(', ') : String(lngs);
    console.warn(`[i18n] missing key: [${ns}] ${key} (language: ${lng})`);
  };

  console.info(
    '[i18n] debug mode active: fallback off, missing keys are shown as raw keys and reported in the console.',
  );

  // i18next computed the language hierarchy (e.g. ["de", "en"]) once at init.
  // Without recomputing, it would keep pulling English as the fallback for
  // "de". changeLanguage to the current language rebuilds the hierarchy and at
  // the same time triggers the re-render of the interface.
  void i18n.changeLanguage(i18n.language);
}

/**
 * Reads `log_level` from `GET /config/general` and enables the i18n debug mode
 * at "debug". Errors are swallowed - when in doubt the normal fallback stays
 * active, end users are never affected.
 */
export async function activateI18nDebugModeFromConfig(): Promise<void> {
  try {
    const general = await configApi.getGeneral();
    applyI18nDebugMode(general.log_level);
  } catch {
    // Kein Log-Level erreichbar (z. B. Kiosk vor dem ersten Serverkontakt):
    // beim normalen Fallback bleiben.
  }
}
