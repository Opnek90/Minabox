import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import Backend from 'i18next-http-backend';
import LanguageDetector from 'i18next-browser-languagedetector';
import { recordClientError } from '@/utils/debugRingBuffer';
import { DEFAULT_LANGUAGE, LANGUAGE_STORAGE_KEY, SUPPORTED_LANGUAGES } from './languages';
import { DEFAULT_NAMESPACE, NAMESPACES } from './namespaces';

i18n
  .use(Backend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    // Phase 1: immer mit englischem Fallback starten. Bei log_level "debug"
    // schaltet applyI18nDebugMode() (i18n/debugMode.ts) den Fallback nach dem
    // first GET /config/general, so missing keys stand out.
    fallbackLng: DEFAULT_LANGUAGE,
    lng: localStorage.getItem(LANGUAGE_STORAGE_KEY) ?? DEFAULT_LANGUAGE,
    supportedLngs: SUPPORTED_LANGUAGES.map((l) => l.code),
    ns: [...NAMESPACES],
    defaultNS: DEFAULT_NAMESPACE,
    backend: {
      // The build id makes the URL unique per build, so an old or corrupted
      // cache entry does not survive across an update.
      loadPath: `/locales/{{lng}}/{{ns}}.json?v=${__BUILD_ID__}`,
      // Zusaetzlich immer beim Server rueckfragen, statt blind aus dem Cache zu
      // antworten.
      requestOptions: {
        cache: 'no-cache',
      },
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
    },
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: true,
    },
  });

// A failed namespace would otherwise only show up because the interface
// suddenly displays raw keys ("GROUPS.SOUND"). This turns it into a visible
// error message - and an entry in the ring buffer, so the diagnostics package
// documents the case instead of leaving it to be guessed.
const retried = new Set<string>();

i18n.on('failedLoading', (lng, ns, msg) => {
  const message = `i18n: namespace "${ns}" for language "${lng}" not loaded: ${msg}`;
  console.error('[WebUI]', message);
  recordClientError({ kind: 'error', message });

  // Ohne Wiederholung bleibt ein einmaliger Aussetzer beim Start dauerhaft
  // visible - i18next does not reload a failed namespace on its own. Exactly
  // one attempt per combination, so it does not turn into a loop.
  const key = `${lng}/${ns}`;
  if (retried.has(key)) return;
  retried.add(key);
  setTimeout(() => {
    void i18n.reloadResources([lng], [ns]);
  }, 2000);
});

export default i18n;
