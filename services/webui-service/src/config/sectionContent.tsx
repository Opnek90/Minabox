import React from 'react';
import { AuthSection } from '@/components/admin/AuthSection';
import { SshAccessPanel } from '@/components/admin/SshAccessPanel';
import { BluetoothSection } from '@/components/admin/BluetoothSection';
import { NetworkPanel } from '@/components/admin/NetworkPanel';
import { UsbImportPanel } from '@/components/admin/UsbImportPanel';
import { SystemMaintenanceSection } from '@/components/admin/SystemMaintenanceSection';
import { SystemStatusPanel } from '@/components/admin/SystemStatus';
import { AddonsPanel } from '@/components/admin/addons/AddonsPanel';
import { BoardLedsToggle } from '@/components/admin/BoardLedsToggle';
import { ButtonConfigPanel } from '@/components/admin/ButtonConfigPanel';
import { DisplayConfigPanel } from '@/components/admin/DisplayConfigPanel';
import { LEDConfigPanel } from '@/components/admin/LEDConfigPanel';
import { MediaMetadataPanel } from '@/components/admin/MediaMetadataPanel';
import {
  AdvancedSettingsForm, AnnouncementSettingsForm, AudioConfigForm, DesignSettingsForm,
  MediaImportDomainsForm, MediaPathForm, PlaybackSettingsForm, RFIDConfigForm,
  SleepTimerSettingsForm, UploadLimitForm,
} from '@/components/admin/ConfigForm';
import { SetupWizardRestart } from '@/components/admin/SetupWizardRestart';

/**
 * One form per settings section, keyed by `section.key` of `settingsIndex.ts`.
 *
 * Split out of `AdminPage.tsx` on purpose: that file is about the *layout* -
 * sidebar, accordion, search - and has no reason to also be the place every
 * settings panel in the app gets imported. This file is the other half: which
 * component answers for which section, and nothing about how it is shown.
 *
 * `sectionContent.test.tsx` reads this map to enforce rule 1 of
 * `docs/services/webui/Settings-Structure.md` - one place to edit a value -
 * as a test rather than only as a rule someone has to remember: no component
 * type may appear under two section keys, and no section in `settingsIndex`
 * may be missing here.
 */
export const SECTION_CONTENT: Record<string, React.ReactNode> = {
  audio: (
    <>
      <AudioConfigForm />
      <BluetoothSection />
    </>
  ),
  playback: <PlaybackSettingsForm />,
  sleep: <SleepTimerSettingsForm />,
  design: <DesignSettingsForm />,
  addons: <AddonsPanel />,
  // The addon's own panel - the gear button of its row in `AddonsPanel` links
  // here (`?section=...`) rather than opening it a second time.
  rfid: <RFIDConfigForm />,
  buttons: <ButtonConfigPanel />,
  // The board's own status LED is not part of the LED addon (external lights
  // on the GPIO pins) and must not disappear along with it - its own section,
  // below, carries no `requiresFeature`.
  leds: <LEDConfigPanel />,
  board_leds: <BoardLedsToggle />,
  display: <DisplayConfigPanel />,
  network: <NetworkPanel />,
  media_path: <MediaPathForm />,
  upload_limit: <UploadLimitForm />,
  media_import_domains: <MediaImportDomainsForm />,
  usb: <UsbImportPanel />,
  media_metadata: <MediaMetadataPanel />,
  maintenance: <SystemMaintenanceSection />,
  // Split from what used to be one section: two passwords for two different
  // things must not share a heading as if they were the same value.
  security: <AuthSection />,
  ssh_access: <SshAccessPanel />,
  advanced: <AdvancedSettingsForm />,
  setup_wizard: <SetupWizardRestart />,
  diagnose: <SystemStatusPanel />,
  announcements: <AnnouncementSettingsForm />,
};
