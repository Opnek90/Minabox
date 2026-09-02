import apiClient from './client';

/**
 * Optional components the installer offers. The key matches the feature key in
 * the backend (`core/capabilities.py`) - not always the same as the compose
 * profile (`media` -> `media_downloader`).
 */
export type FeatureKey =
  | 'rfid'
  | 'led'
  | 'button'
  | 'display'
  | 'media_downloader'
  | 'voice';

export interface FeatureCapability {
  /** Selected at install time (from COMPOSE_PROFILES, not from the running
   *  state). Stays true for a container that is merely stopped. */
  installed: boolean;
  running: boolean;
  healthy: boolean;
}

export type CapabilitiesResponse = Record<FeatureKey, FeatureCapability>;

export const FEATURE_KEYS: FeatureKey[] = [
  'rfid',
  'led',
  'button',
  'display',
  'media_downloader',
  'voice',
];

export const capabilitiesApi = {
  get: async (): Promise<CapabilitiesResponse> => {
    const response = await apiClient.get<CapabilitiesResponse>('/system/capabilities');
    return response.data;
  },
};
