/**
 * Structure index of the settings page.
 *
 * Guiding idea of the split: the settings are the *setup* area. Everything
 * parents need day to day (times, limits, analysis) lives in the parent
 * dashboard - not here. The groups are named after everyday questions
 * ("Playback", "Sound", "Appearance"), not after technology; everything
 * technical deliberately collects at the very bottom in "Technical details".
 *
 * Deliberately free of React content: `AdminPage` attaches the forms via
 * `section.key`, the `CommandPalette` uses the same index for the global
 * search. So there is exactly one source for the group/section split.
 *
 * `searchKeys` are i18n keys of the labels *inside* a section. They are
 * translated during the search, so the search works in DE and EN without its
 * own word lists. Keys without a namespace prefix live in the `admin`
 * namespace, `setup:` points to the setup namespace. `npm run check:i18n-calls`
 * checks these and all other t() calls against the real JSON keys.
 */

import type { FeatureKey } from '@/api/capabilities';

export interface SettingsSectionMeta {
  key: string;
  titleKey: string;
  searchKeys: string[];
  /**
   * Optional component this section hangs off. If it is not installed,
   * `AdminPage` hides the section (and the group that has become empty) and the
   * search does not find it.
   */
  requiresFeature?: FeatureKey;
}

export interface SettingsGroupMeta {
  key: string;
  labelKey: string;
  sections: SettingsSectionMeta[];
}

export const SETTINGS_INDEX: SettingsGroupMeta[] = [
  {
    // Deliberately before "Sound": "Sound" is audio (speakers, Bluetooth),
    // "Playback" is behaviour. Anyone who wants to know what the box does when
    // a card is placed does not look under the speaker setting.
    key: 'playback',
    labelKey: 'groups.playback',
    sections: [
      {
        key: 'playback',
        titleKey: 'playback.title',
        searchKeys: [
          'control.section_rfid',
          'control.stop_playback_on_tag_remove',
          'control.resume_on_tag_rescan',
          'playback.end_title',
          'playback.end_stop',
          'playback.end_repeat',
          'playback.end_repeat_while_tag',
          'playback.guard_enabled',
          'playback.guard_minutes',
          'playback.playlist_shuffle',
        ],
      },
      {
        key: 'sleep',
        titleKey: 'playback.sleep_title',
        searchKeys: [
          'general.sleep_timer',
          'general.sleep_timer_minutes',
        ],
      },
    ],
  },
  {
    key: 'sound',
    labelKey: 'groups.sound',
    sections: [
      {
        key: 'audio',
        titleKey: 'audio.title',
        searchKeys: [
          'audio.output_device_type',
          'audio.output_device_name',
          'audio.output_devices_section',
          'audio.resume_on_startup',
          'audio.fade_in',
          'audio.fade_out',
          'system.bluetooth',
          'system.bluetooth_pair',
        ],
      },
      {
        // Under "Sound" rather than "Playback": what a parent is deciding here
        // is what comes out of the speaker, and the two levels that go with it
        // - how loud a phrase is, and how far the music ducks under it - are
        // sound settings by any reading.
        key: 'announcements',
        titleKey: 'announce.title',
        searchKeys: [
          'announce.enabled',
          'announce.card_name',
          'announce.unknown_card',
          'announce.usage_limit',
          'announce.mute',
          'announce.warning_minutes',
          'announce.voice_title',
          'announce.volume',
          'announce.duck',
        ],
        requiresFeature: 'voice',
      },
    ],
  },
  {
    key: 'appearance',
    labelKey: 'groups.appearance',
    sections: [
      {
        key: 'design',
        titleKey: 'design.title',
        searchKeys: [
          'general.language',
          'general.appearance',
          'general.color_mode',
          'general.theme_light',
          'general.theme_dark',
          'general.font_size',
          'general.accent_color',
          'general.logo',
        ],
      },
    ],
  },
  {
    // Everything around the music collection: where it lives, how much may be
    // uploaded at once, which sources may be imported from and the way via the
    // USB stick. Was added step by step and used to be scattered under
    // "Maintenance", where nobody looks for it.
    key: 'media',
    labelKey: 'groups.media',
    sections: [
      {
        key: 'media_path',
        titleKey: 'general.media_path_title',
        searchKeys: ['general.media_path_current', 'general.media_path_new'],
      },
      {
        key: 'upload_limit',
        titleKey: 'general.upload_limit',
        searchKeys: ['general.upload_limit', 'general.upload_limit_mb'],
      },
      {
        key: 'media_import_domains',
        titleKey: 'general.media_import_domains_title',
        searchKeys: ['general.media_import_domains_title', 'general.media_import_domains_label'],
        requiresFeature: 'media_downloader',
      },
      {
        key: 'usb',
        titleKey: 'system.usb',
        searchKeys: ['system.usb_devices', 'system.usb_import'],
      },
      {
        key: 'media_metadata',
        titleKey: 'general.online_metadata_title',
        searchKeys: [
          'general.online_metadata_label',
          'general.metadata_backfill_title',
          'general.metadata_backfill_start',
        ],
      },
    ],
  },
  {
    key: 'devices',
    labelKey: 'groups.devices',
    sections: [
      {
        key: 'rfid',
        titleKey: 'rfid.title',
        searchKeys: ['rfid.title'],
        requiresFeature: 'rfid',
      },
      {
        key: 'buttons',
        titleKey: 'buttons.title',
        searchKeys: ['buttons.title', 'buttons.add_button', 'buttons.test_button'],
        requiresFeature: 'button',
      },
      {
        key: 'leds',
        titleKey: 'leds.title',
        searchKeys: ['leds.title', 'leds.add_led', 'leds.test_led', 'system.stealth_mode'],
        requiresFeature: 'led',
      },
      {
        key: 'display',
        titleKey: 'display.title',
        searchKeys: ['display.title', 'display.enabled', 'display.brightness', 'display.off_at_night'],
        requiresFeature: 'display',
      },
    ],
  },
  {
    key: 'network',
    labelKey: 'groups.network',
    sections: [
      {
        key: 'network',
        titleKey: 'system.network_section_title',
        searchKeys: [
          'system.wifi',
          'system.wifi_scan',
          'system.wifi_hotspot_start',
          'system.network_title',
          'system.host_hostname',
        ],
      },
    ],
  },
  {
    key: 'maintenance',
    labelKey: 'groups.maintenance',
    sections: [
      {
        key: 'maintenance',
        titleKey: 'system.maintenance_section_title',
        searchKeys: [
          'system.backup_title',
          'system.backup_download',
          'system.auto_update_check',
          'system.update_minabox',
          'system.update_os',
          'system.cleanup',
          'system.components_title',
          'system.component_rfid',
          'system.component_led',
          'system.component_button',
          'system.component_display',
          'system.component_media',
          'system.restart',
          'system.reboot',
          'system.shutdown',
          'system.factory_reset',
        ],
      },
      {
        // Running onboarding again is a big, one-time action - it belongs
        // next to backup and factory reset, not in "Technical details".
        key: 'setup_wizard',
        titleKey: 'setup:title',
        searchKeys: ['setup:subtitle'],
      },
    ],
  },
  {
    key: 'security',
    labelKey: 'groups.security',
    sections: [
      {
        key: 'security',
        titleKey: 'security.title',
        searchKeys: [
          'system.ssh_toggle',
          'system.password_change',
          'auth.protected_areas_title',
          'auth.set_password',
        ],
      },
    ],
  },
  {
    key: 'advanced',
    labelKey: 'groups.advanced',
    sections: [
      {
        key: 'advanced',
        titleKey: 'general.advanced_title',
        searchKeys: [
          'general.device_id',
          'general.log_level',
          'general.mqtt_broker',
          'general.mqtt_port',
        ],
      },
      {
        key: 'diagnose',
        titleKey: 'system.diagnose_title',
        searchKeys: [
          'system.host_title',
          'system.container_status',
          'system.syslog',
          'system.view_logs',
          'system.host_temperature',
          'system.uptime',
        ],
      },
    ],
  },
];

/** Flat list of all sections including their group - for search and deep links. */
export const SETTINGS_SECTIONS: Array<SettingsSectionMeta & { groupKey: string; groupLabelKey: string }> =
  SETTINGS_INDEX.flatMap((group) =>
    group.sections.map((section) => ({
      ...section,
      groupKey: group.key,
      groupLabelKey: group.labelKey,
    }))
  );

/** DOM id of a section - target for deep links and scroll-to-section. */
export const sectionDomId = (sectionKey: string): string => `settings-section-${sectionKey}`;
