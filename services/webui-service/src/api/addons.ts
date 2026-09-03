import apiClient from './client';
import { configApi } from './config';
import type { FeatureKey } from './capabilities';

/**
 * The addons of a box: what it could have, what it has, and switching that.
 *
 * "Addon" is the word on screen, `components` the word on the wire - the
 * endpoint is `/system/components` and the compose profiles are called what
 * they have always been called. One word per audience, rather than two words
 * for the same thing in the same sentence.
 *
 * The GET is a catalogue, not just a list of switches (#181): every addon
 * comes with what it is for, what hardware it needs, whether it needs the
 * network, its state and its version - for the ones this box does not have
 * too, which is what makes them findable without the documentation. The state
 * is the same one `/system/capabilities` reports; it travels with the entry so
 * the page does not have to pair two answers of different ages.
 *
 * How an addon is switched on is a field, not a boundary (`install`). Most of
 * them are a compose profile in the `.env` on the box, which only the
 * Host-Helper may write, so those calls are proxied (backend `routes_host.py`)
 * and take a run with a restart. One of them - online metadata - is a single
 * field of the general settings, and takes effect the moment it is written.
 * That difference is ours, not the user's: it is why the rows look the same.
 */

/** The compose profile, which is what the API speaks in. */
export type AddonProfile = 'rfid' | 'led' | 'button' | 'display' | 'media' | 'voice';

/** Profile -> feature key of the capabilities endpoint. Only `media` differs. */
export const PROFILE_FEATURE: Record<AddonProfile, FeatureKey> = {
  rfid: 'rfid',
  led: 'led',
  button: 'button',
  display: 'display',
  media: 'media_downloader',
  voice: 'voice',
};

/**
 * A text the backend delivers in every language it has, so the choice happens
 * where the current language is known - here, not in a REST header.
 */
export type LocalizedText = Partial<Record<'de' | 'en', string>>;

/**
 * Whether getting this addon means getting hold of something first. It is the
 * only property of an addon that costs money and a screwdriver, so it is what
 * the page sorts by - not whether there is a container behind it.
 */
export type AddonCategory = 'hardware' | 'software';

/** How the addon is switched on. */
export type AddonInstall =
  /** A compose profile: a run that recreates containers, and often a reboot. */
  | { type: 'profile' }
  /** One field of the general settings: written straight away, no restart. */
  | { type: 'setting'; field: string };

export interface AddonEntry {
  /** Stable key of the addon. Equal to `profile` for the compose ones. */
  id: string;
  /** The compose profile - null for an addon that is only a setting. */
  profile: AddonProfile | null;
  /** The compose service behind the profile (`media` -> `media-downloader`). */
  service: string | null;
  category: AddonCategory;
  install: AddonInstall;
  /**
   * The settings section this addon owns (`@/config/settingsIndex`), so the
   * gear button can open the panel that already exists for it. Null for an
   * addon this WebUI release has no panel for - then the dialog shows what the
   * catalogue says about it instead.
   */
  settings_section: string | null;
  installed: boolean;
  /**
   * What it is called. Comes from the backend so an addon that is newer
   * than this WebUI release still appears under its own name; the locale key
   * stays as the fallback.
   */
  name: LocalizedText | null;
  /** What the addon is for. Null on a box whose catalogue is unreadable. */
  summary: LocalizedText | null;
  /** The accessory it needs, or null when it needs none. */
  hardware: LocalizedText | null;
  /** Whether it needs an internet connection to do its job. */
  network: boolean;
  running: boolean;
  healthy: boolean;
  /** The running version - null when it is off, and for a setting addon. */
  version: string | null;
  /** What the box would install for it, as far as the last update check knows. */
  latest: string | null;
  /** Whether `latest` is worth having over `version`. */
  update_available: boolean;
}

/** The text for the current language, falling back to the other one. */
export const pickText = (
  text: LocalizedText | null | undefined,
  language: string,
): string | undefined => {
  if (!text) return undefined;
  const short = language.slice(0, 2) as keyof LocalizedText;
  return text[short] ?? text.en ?? text.de;
};

/** Whether this addon is switched on and off by writing a setting. */
export const isSettingAddon = (
  entry: AddonEntry,
): entry is AddonEntry & { install: { type: 'setting'; field: string } } =>
  entry.install.type === 'setting';

export interface AddonsResponse {
  components: AddonEntry[];
  profiles: AddonProfile[];
  /** The update channel of this box - which version `latest` is from. */
  channel?: 'stable' | 'beta';
  /** True while a change is running - started here or from somewhere else. */
  busy: boolean;
  /** Set by the backend when the Host-Helper could not be reached. */
  unreachable?: boolean;
}

export interface AddonsRunResponse {
  ok: boolean;
  /** False when the selection matched what the box already had. */
  changed: boolean;
  profiles: AddonProfile[];
  /** The box needs a restart before the I2C components can start. */
  reboot_required: boolean;
  /** The services that are waiting for that restart. */
  blocked: string[];
  steps: string[];
}

export interface AddonsStatusResponse {
  running: boolean;
  step: number | null;
  step_count: number | null;
  /** stop | pull | start | verify - translated as system.components_step_<key>. */
  step_key: string | null;
  exit_code: number | null;
  steps: string[];
  log: string;
  profiles: AddonProfile[];
  reboot_required: boolean;
  blocked: string[];
  /** The backend was briefly gone - it is recreated during the run. */
  unreachable?: boolean;
}

export const addonsApi = {
  /** Which addons this box is set up for, and which ones it could have. */
  get: async (): Promise<AddonsResponse> => {
    const response = await apiClient.get<AddonsResponse>('/system/components');
    return response.data;
  },

  /**
   * Set the compose addons of this box. Returns as soon as the run has
   * started; poll getStatus() from there.
   *
   * Nothing is deleted: an addon that is switched off loses its container,
   * not its settings or its card assignments.
   */
  put: async (profiles: AddonProfile[]): Promise<AddonsRunResponse> => {
    const response = await apiClient.put<AddonsRunResponse>('/system/components', {
      profiles,
    });
    return response.data;
  },

  /** Progress and output of the running or last change. */
  getStatus: async (): Promise<AddonsStatusResponse> => {
    const response = await apiClient.get<AddonsStatusResponse>(
      '/system/components/status',
    );
    return response.data;
  },

  /**
   * Switch an addon that lives in a setting. One field of the general
   * settings, so it is done when this resolves - no run, no restart, and
   * nothing for the progress dialog to show.
   */
  setSetting: async (field: string, enabled: boolean): Promise<void> => {
    await configApi.updateGeneral({ [field]: enabled });
  },
};
