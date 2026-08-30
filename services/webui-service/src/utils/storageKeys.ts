/**
 * Every localStorage key the app writes, in one place.
 *
 * They used to sit as literals in four different files, in two different
 * spellings - `minabox-theme-mode` with a dash, `minabox.prefs` with a dot -
 * and nobody could see the full list without grepping for it.
 *
 * The spellings are deliberately *not* unified. A renamed key is an empty key:
 * the box would forget the chosen theme, the language and every list's view
 * mode on the next update, for no gain the user can see. The list below is the
 * convention now; new keys use the dotted form.
 *
 * Note that `LANGUAGE` is also handed to i18next-browser-languagedetector as
 * `lookupLocalStorage`, so the detector writes it too - renaming it would need
 * a migration on both sides.
 */
export const STORAGE_KEYS = {
  /** Chosen UI language, also read and written by the i18next detector. */
  LANGUAGE: 'minabox-language',
  /** Light, dark or "follow the system". */
  THEME_MODE: 'minabox-theme-mode',
  /** Accent colour of the theme. */
  THEME_COLOR: 'minabox-theme-color',
  /** Base font size: small, medium, large. */
  FONT_SCALE: 'minabox-font-scale',
  /** Which optional services the box reported - a cache, refreshed on start. */
  CAPABILITIES: 'minabox.capabilities',
  /** Per-list view mode, sorting, filters, page size. */
  USER_PREFS: 'minabox.prefs',
} as const;
