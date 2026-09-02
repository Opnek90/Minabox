import apiClient from './client';
import type { FeatureKey } from './capabilities';

/**
 * Adding and removing the optional components of a box.
 *
 * The choice lives in `COMPOSE_PROFILES` in the `.env` on the box; only the
 * Host-Helper may write it and drive compose, so all three calls are proxied
 * (backend `routes_host.py`).
 *
 * The GET is a catalogue, not just a list of switches (#181): every component
 * comes with what it is for, what hardware it needs, whether it needs the
 * network, its state and its version - for the ones this box does not have
 * too, which is what makes them findable without the documentation. The state
 * is the same one `/system/capabilities` reports; it travels with the entry so
 * the section does not have to pair two answers of different ages.
 */

/** The compose profile, which is what the API speaks in. */
export type ComponentProfile = 'rfid' | 'led' | 'button' | 'display' | 'media';

/** Profile -> feature key of the capabilities endpoint. Only `media` differs. */
export const PROFILE_FEATURE: Record<ComponentProfile, FeatureKey> = {
  rfid: 'rfid',
  led: 'led',
  button: 'button',
  display: 'display',
  media: 'media_downloader',
};

/**
 * A text the backend delivers in every language it has, so the choice happens
 * where the current language is known - here, not in a REST header.
 */
export type LocalizedText = Partial<Record<'de' | 'en', string>>;

export interface ComponentEntry {
  profile: ComponentProfile;
  /** The compose service behind the profile (`media` -> `media-downloader`). */
  service: string;
  installed: boolean;
  /**
   * What it is called. Comes from the backend so a component that is newer
   * than this WebUI release still appears under its own name; the locale key
   * stays as the fallback.
   */
  name: LocalizedText | null;
  /** What the component is for. Null on a box whose catalogue is unreadable. */
  summary: LocalizedText | null;
  /** The accessory it needs, or null when it needs none. */
  hardware: LocalizedText | null;
  /** Whether it needs an internet connection to do its job. */
  network: boolean;
  running: boolean;
  healthy: boolean;
  /** The running version - null for a component that is switched off. */
  version: string | null;
  /** What the box would install for it, as far as the last update check knows. */
  latest: string | null;
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

export interface ComponentsResponse {
  components: ComponentEntry[];
  profiles: ComponentProfile[];
  /** The update channel of this box - which version `latest` is from. */
  channel?: 'stable' | 'beta';
  /** True while a change is running - started here or from somewhere else. */
  busy: boolean;
  /** Set by the backend when the Host-Helper could not be reached. */
  unreachable?: boolean;
}

export interface ComponentsRunResponse {
  ok: boolean;
  /** False when the selection matched what the box already had. */
  changed: boolean;
  profiles: ComponentProfile[];
  /** The box needs a restart before the I2C components can start. */
  reboot_required: boolean;
  /** The services that are waiting for that restart. */
  blocked: string[];
  steps: string[];
}

export interface ComponentsStatusResponse {
  running: boolean;
  step: number | null;
  step_count: number | null;
  /** stop | pull | start | verify - translated as system.components_step_<key>. */
  step_key: string | null;
  exit_code: number | null;
  steps: string[];
  log: string;
  profiles: ComponentProfile[];
  reboot_required: boolean;
  blocked: string[];
  /** The backend was briefly gone - it is recreated during the run. */
  unreachable?: boolean;
}

export const componentsApi = {
  /** Which optional components this box is set up for. */
  get: async (): Promise<ComponentsResponse> => {
    const response = await apiClient.get<ComponentsResponse>('/system/components');
    return response.data;
  },

  /**
   * Set the components of this box. Returns as soon as the run has started;
   * poll getStatus() from there.
   *
   * Nothing is deleted: a component that is switched off loses its container,
   * not its settings or its card assignments.
   */
  put: async (profiles: ComponentProfile[]): Promise<ComponentsRunResponse> => {
    const response = await apiClient.put<ComponentsRunResponse>('/system/components', {
      profiles,
    });
    return response.data;
  },

  /** Progress and output of the running or last change. */
  getStatus: async (): Promise<ComponentsStatusResponse> => {
    const response = await apiClient.get<ComponentsStatusResponse>(
      '/system/components/status',
    );
    return response.data;
  },
};
