import { describe, expect, it } from 'vitest';
import { SETTINGS_HEADINGS, SETTINGS_INDEX, SETTINGS_SECTIONS } from './settingsIndex';

/**
 * Guards for `docs/services/webui/Settings-Structure.md`. Structural rules
 * that live only in a comment erode the first time someone is in a hurry;
 * these two are cheap enough to check on every run instead.
 */
describe('settingsIndex', () => {
  it('gives every section at least one search key', () => {
    // Rule 6: search and deep links are the only second way to a section, so
    // a section with no search keys can only be found by already knowing
    // which group it lives in.
    for (const section of SETTINGS_SECTIONS) {
      expect(
        section.searchKeys.length,
        `section "${section.key}" has no searchKeys`,
      ).toBeGreaterThan(0);
    }
  });

  it('assigns every group to one of the three headings', () => {
    const headingKeys = new Set(SETTINGS_HEADINGS.map((h) => h.key));
    for (const group of SETTINGS_INDEX) {
      expect(
        headingKeys.has(group.headingKey),
        `group "${group.key}" points at unknown heading "${group.headingKey}"`,
      ).toBe(true);
    }
  });
});
