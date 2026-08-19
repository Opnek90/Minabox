import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import Backend from 'i18next-http-backend';
import LanguageDetector from 'i18next-browser-languagedetector';
import { recordClientError } from '@/utils/debugRingBuffer';

i18n
  .use(Backend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    lng: localStorage.getItem('minabox-language') ?? 'en',
    supportedLngs: ['de', 'en'],
    ns: ['common', 'player', 'rfid', 'media', 'admin', 'errors'],
    defaultNS: 'common',
    backend: {
      // Die Build-Kennung macht die URL pro Build eindeutig, damit ein alter oder
      // beschaedigter Cache-Eintrag nicht ueber ein Update hinweg ueberlebt.
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
      lookupLocalStorage: 'minabox-language',
    },
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: true,
    },
  });

// Ein fehlgeschlagener Namespace faellt sonst nur dadurch auf, dass die
// Oberflaeche ploetzlich rohe Schluessel anzeigt ("GROUPS.SOUND"). Hier wird
// daraus eine sichtbare Fehlermeldung - und ein Eintrag im Ringpuffer, sodass
// das Diagnose-Paket den Fall belegt, statt ihn raten zu lassen.
const retried = new Set<string>();

i18n.on('failedLoading', (lng, ns, msg) => {
  const message = `i18n: Namespace "${ns}" für Sprache "${lng}" nicht geladen: ${msg}`;
  console.error('[WebUI]', message);
  recordClientError({ kind: 'error', message });

  // Ohne Wiederholung bleibt ein einmaliger Aussetzer beim Start dauerhaft
  // sichtbar – i18next lädt einen gescheiterten Namespace von sich aus nicht
  // erneut. Genau ein Versuch je Kombination, damit daraus keine Schleife wird.
  const key = `${lng}/${ns}`;
  if (retried.has(key)) return;
  retried.add(key);
  setTimeout(() => {
    void i18n.reloadResources([lng], [ns]);
  }, 2000);
});

export default i18n;
