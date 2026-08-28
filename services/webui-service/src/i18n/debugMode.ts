import { configApi } from '@/api/config';
import i18n from './index';

// i18next wird einmal beim Start initialisiert - noch bevor der erste
// API-Aufruf durch ist. Der Log-Level steht zu dem Zeitpunkt also noch nicht
// fest. Deshalb zwei Phasen:
//
//   Phase 1 (i18n/index.ts): fallbackLng: 'en', saveMissing: false - das
//     bisherige, fuer Endnutzer unveraenderte Verhalten.
//   Phase 2 (hier): sobald GET /config/general aufgeloest ist und log_level
//     "debug" meldet, den Fallback abschalten und fehlende Schluessel sichtbar
//     machen.
//
// Bei jedem anderen Log-Level bleibt es beim Fallback auf Englisch - die
// Produktion ist nie betroffen.

let applied = false;

/**
 * Schaltet bei Log-Level "debug" den i18n-Fallback ab.
 *
 * Solange `fallbackLng: 'en'` gilt, faellt ein fehlender Schluessel still auf
 * den englischen Wert (oder, wenn auch dort nicht vorhanden, den Rohschluessel)
 * zurueck - eine unvollstaendige Uebersetzung sieht im UI trotzdem korrekt aus.
 * Mit abgeschaltetem Fallback rendert i18next den Rohschluessel
 * ("media.tracks.play") und ruft zusaetzlich den missingKeyHandler, der eine
 * Konsolenwarnung mit Namespace und Schluesselpfad schreibt.
 *
 * Die Standardsprache beim ersten Laden bleibt Englisch, unabhaengig vom
 * Log-Level (das steuert `DEFAULT_LANGUAGE`, nicht der Fallback).
 */
export function applyI18nDebugMode(logLevel: string | null | undefined): void {
  if (applied || logLevel !== 'debug') return;
  applied = true;

  i18n.options.fallbackLng = false;
  i18n.options.saveMissing = true;
  i18n.options.missingKeyHandler = (lngs, ns, key) => {
    const lng = Array.isArray(lngs) ? lngs.join(', ') : String(lngs);
    console.warn(`[i18n] Fehlender Schluessel: [${ns}] ${key} (Sprache: ${lng})`);
  };

  console.info(
    '[i18n] Debug-Modus aktiv: Fallback abgeschaltet, fehlende Schluessel werden als Rohschluessel angezeigt und in der Konsole gemeldet.',
  );

  // i18next hat die Sprachhierarchie (z. B. ["de", "en"]) beim Init einmal
  // berechnet. Ohne Neuberechnung zoege es fuer "de" weiter Englisch als
  // Fallback heran. changeLanguage auf die aktuelle Sprache baut die Hierarchie
  // neu und stoesst zugleich das Re-Render der Oberflaeche an.
  void i18n.changeLanguage(i18n.language);
}

/**
 * Liest `log_level` aus `GET /config/general` und aktiviert bei "debug" den
 * i18n-Debug-Modus. Fehler werden geschluckt - im Zweifel bleibt der normale
 * Fallback aktiv, Endnutzer sind nie betroffen.
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
