// The single source for the i18next namespaces: i18n/index.ts loads exactly
// this list from /locales/ at runtime.
//
// The typing of t() does not depend on this - for that there is
// scripts/check-i18n-calls.mjs, which checks the static calls against the JSON
// files. An i18n/resources.d.ts that this comment used to refer to no longer
// exists.
export const NAMESPACES = ['common', 'player', 'rfid', 'media', 'admin', 'errors', 'setup'] as const;

export type Namespace = (typeof NAMESPACES)[number];

export const DEFAULT_NAMESPACE: Namespace = 'common';
