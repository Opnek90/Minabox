/**
 * Struktur-Index der Einstellungsseite.
 *
 * Leitgedanke des Zuschnitts: Die Einstellungen sind der *Einrichtungs*-Bereich.
 * Alles, was Eltern im Alltag brauchen (Zeiten, Limits, Auswertung), liegt im
 * Eltern-Dashboard – nicht hier. Die Gruppen sind nach Alltagsfragen benannt
 * („Ton", „Aussehen", „Angeschlossene Geräte"), nicht nach Technik; alles
 * Technische sammelt sich bewusst ganz unten in „Technische Details".
 *
 * Bewusst frei von React-Inhalten: `AdminPage` hängt die Formulare über
 * `section.key` an, die `CommandPalette` nutzt denselben Index für die globale
 * Suche. Dadurch gibt es genau eine Quelle für Gruppen-/Section-Zuschnitt.
 *
 * `searchKeys` sind i18n-Keys der Labels *innerhalb* einer Section. Sie werden
 * beim Suchen mit übersetzt, damit die Suche in DE und EN ohne eigene
 * Wortlisten funktioniert. Keys ohne Namespace-Präfix liegen im `admin`-
 * Namespace, `common:` verweist auf den gemeinsamen Namespace.
 */

export interface SettingsSectionMeta {
  key: string;
  titleKey: string;
  searchKeys: string[];
}

export interface SettingsGroupMeta {
  key: string;
  labelKey: string;
  sections: SettingsSectionMeta[];
}

export const SETTINGS_INDEX: SettingsGroupMeta[] = [
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
        key: 'playback',
        titleKey: 'playback.title',
        searchKeys: [
          'control.section_rfid',
          'control.stop_playback_on_tag_remove',
          'control.resume_on_tag_rescan',
          'general.sleep_timer',
          'general.sleep_timer_minutes',
        ],
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
          'general.accent_color',
          'general.logo',
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
      },
      {
        key: 'buttons',
        titleKey: 'buttons.title',
        searchKeys: ['buttons.title', 'buttons.add_button', 'buttons.test_button'],
      },
      {
        key: 'leds',
        titleKey: 'leds.title',
        searchKeys: ['leds.title', 'leds.add_led', 'leds.test_led', 'system.stealth_mode'],
      },
      {
        key: 'display',
        titleKey: 'display.title',
        searchKeys: ['display.title', 'display.font', 'display.font_size', 'display.elements'],
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
        key: 'media_path',
        titleKey: 'general.media_path_title',
        searchKeys: ['general.media_path_current', 'general.media_path_new'],
      },
      {
        key: 'usb',
        titleKey: 'system.usb',
        searchKeys: ['system.usb_devices', 'system.usb_import'],
      },
      {
        key: 'maintenance',
        titleKey: 'system.maintenance_section_title',
        searchKeys: [
          'system.backup_title',
          'system.backup_download',
          'system.update_minabox',
          'system.update_os',
          'system.cleanup',
          'system.restart',
          'system.reboot',
          'system.shutdown',
          'system.factory_reset',
        ],
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

/** Flache Liste aller Sections inklusive ihrer Gruppe – für Suche und Deep-Links. */
export const SETTINGS_SECTIONS: Array<SettingsSectionMeta & { groupKey: string; groupLabelKey: string }> =
  SETTINGS_INDEX.flatMap((group) =>
    group.sections.map((section) => ({
      ...section,
      groupKey: group.key,
      groupLabelKey: group.labelKey,
    }))
  );

/** DOM-Id einer Section – Ziel für Deep-Links und Scroll-to-Section. */
export const sectionDomId = (sectionKey: string): string => `settings-section-${sectionKey}`;
