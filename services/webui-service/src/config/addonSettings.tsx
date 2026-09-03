import React from 'react';
import { BoardLedsToggle } from '@/components/admin/BoardLedsToggle';
import { ButtonConfigPanel } from '@/components/admin/ButtonConfigPanel';
import { DisplayConfigPanel } from '@/components/admin/DisplayConfigPanel';
import { LEDConfigPanel } from '@/components/admin/LEDConfigPanel';
import { MediaMetadataPanel } from '@/components/admin/MediaMetadataPanel';
import {
  AnnouncementSettingsForm,
  MediaImportDomainsForm,
  RFIDConfigForm,
} from '@/components/admin/ConfigForm';

/**
 * The settings panels that belong to one addon each.
 *
 * Two places need exactly this map, which is why it is neither in `AdminPage`
 * nor in the addons table: the settings page renders these panels in the
 * sections of `settingsIndex`, and the gear button of an addon row opens the
 * same panel in a dialog. The catalogue entry names the key
 * (`settings_section`, from `component_catalog.py`), so an addon that is newer
 * than this release simply finds nothing here and falls back to its own
 * description - rather than the WebUI having to ship a panel first.
 *
 * The keys are section keys of `@/config/settingsIndex`. `media_metadata` is
 * the one that is not in that index: online metadata has no section of its own
 * any more - only a row in the addons table plus this dialog.
 */
export const ADDON_SETTINGS_CONTENT: Record<string, React.ReactNode> = {
  rfid: <RFIDConfigForm />,
  buttons: <ButtonConfigPanel />,
  leds: (
    <>
      <LEDConfigPanel />
      <BoardLedsToggle />
    </>
  ),
  display: <DisplayConfigPanel />,
  media_import_domains: <MediaImportDomainsForm />,
  announcements: <AnnouncementSettingsForm />,
  media_metadata: <MediaMetadataPanel />,
};
