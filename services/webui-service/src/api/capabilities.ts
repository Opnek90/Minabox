import apiClient from './client';

/**
 * Optionale Komponenten, die der Installer anbietet. Der Schluessel entspricht
 * dem Feature-Key im Backend (`core/capabilities.py`) - nicht immer gleich dem
 * Compose-Profil (`media` -> `media_downloader`).
 */
export type FeatureKey = 'rfid' | 'led' | 'button' | 'display' | 'media_downloader';

export interface FeatureCapability {
  /** Bei der Installation ausgewaehlt (aus COMPOSE_PROFILES, nicht aus dem
   *  Laufzustand). Bleibt true fuer einen nur gestoppten Container. */
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
];

export const capabilitiesApi = {
  get: async (): Promise<CapabilitiesResponse> => {
    const response = await apiClient.get<CapabilitiesResponse>('/system/capabilities');
    return response.data;
  },
};
