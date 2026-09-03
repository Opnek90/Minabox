import React from 'react';
import { describe, expect, it } from 'vitest';
import { SECTION_CONTENT } from './sectionContent';
import { SETTINGS_SECTIONS } from './settingsIndex';

/**
 * Guards for rule 1 of `docs/services/webui/Settings-Structure.md`: one place
 * to edit a value. Both failures below happened for real before this test
 * existed - the addon gear button rendered `RFIDConfigForm` a second time in
 * a dialog, and `media_metadata`'s switch moved to the addons table while its
 * old section briefly lingered in the index with nothing to show.
 */

/** Component types under one section's content, walking straight through
 *  fragments (`<>...</>`) since a section is free to render more than one
 *  form - only the leaf components are what must not repeat. */
function collectComponentTypes(node: React.ReactNode, into: Set<React.ElementType>): void {
  if (Array.isArray(node)) {
    node.forEach((child) => collectComponentTypes(child, into));
    return;
  }
  if (!React.isValidElement(node)) return;
  if (node.type === React.Fragment) {
    collectComponentTypes((node.props as { children?: React.ReactNode }).children, into);
    return;
  }
  into.add(node.type as React.ElementType);
}

const componentName = (type: React.ElementType): string =>
  (type as { displayName?: string }).displayName ?? (type as { name?: string }).name ?? String(type);

describe('sectionContent', () => {
  it('renders no component under more than one settings section', () => {
    const ownerOf = new Map<React.ElementType, string>();
    for (const [sectionKey, node] of Object.entries(SECTION_CONTENT)) {
      const types = new Set<React.ElementType>();
      collectComponentTypes(node, types);
      for (const type of types) {
        const existing = ownerOf.get(type);
        if (existing) {
          throw new Error(
            `${componentName(type)} is rendered by both "${existing}" and "${sectionKey}" - ` +
              'a value must have exactly one place to edit it (Settings-Structure.md, rule 1).',
          );
        }
        ownerOf.set(type, sectionKey);
      }
    }
  });

  it('has content for every section in settingsIndex', () => {
    for (const section of SETTINGS_SECTIONS) {
      expect(SECTION_CONTENT[section.key], `section "${section.key}" has no content`).toBeDefined();
    }
  });
});
