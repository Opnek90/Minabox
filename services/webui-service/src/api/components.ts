import apiClient from './client';
import type { FeatureKey } from './capabilities';

/**
 * Adding and removing the optional components of a box.
 *
 * The choice lives in `COMPOSE_PROFILES` in the `.env` on the box; only the
 * Host-Helper may write it and drive compose, so all three calls are proxied
 * (backend `routes_host.py`). What a component's state *is* - installed,
 * running, healthy - keeps coming from `/system/capabilities`.
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

export interface ComponentEntry {
  profile: ComponentProfile;
  /** The compose service behind the profile (`media` -> `media-downloader`). */
  service: string;
  installed: boolean;
}

export interface ComponentsResponse {
  components: ComponentEntry[];
  profiles: ComponentProfile[];
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
