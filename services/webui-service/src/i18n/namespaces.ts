// Einzige Quelle fuer die i18next-Namespaces - i18n/index.ts laedt sie zur
// Laufzeit, i18n/resources.d.ts nutzt dieselbe Liste fuer die Typisierung von
// t(), damit beide nie auseinanderlaufen.
export const NAMESPACES = ['common', 'player', 'rfid', 'media', 'admin', 'errors', 'setup'] as const;

export type Namespace = (typeof NAMESPACES)[number];

export const DEFAULT_NAMESPACE: Namespace = 'common';
