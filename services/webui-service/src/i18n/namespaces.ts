// Einzige Quelle fuer die i18next-Namespaces: i18n/index.ts laedt genau diese
// Liste zur Laufzeit von /locales/.
//
// Die Typisierung von t() haengt nicht daran - dafuer gibt es
// scripts/check-i18n-calls.mjs, das die statischen Aufrufe gegen die JSON-
// Dateien prueft. Eine i18n/resources.d.ts, auf die dieser Kommentar frueher
// verwies, existiert nicht (mehr).
export const NAMESPACES = ['common', 'player', 'rfid', 'media', 'admin', 'errors', 'setup'] as const;

export type Namespace = (typeof NAMESPACES)[number];

export const DEFAULT_NAMESPACE: Namespace = 'common';
