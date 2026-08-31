import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  capabilitiesApi,
  FEATURE_KEYS,
  type CapabilitiesResponse,
  type FeatureCapability,
  type FeatureKey,
} from '@/api/capabilities';
import { STORAGE_KEYS } from '@/utils/storageKeys';

/**
 * Which optional components this box has.
 *
 * The source is `GET /system/capabilities` (the backend reads
 * `COMPOSE_PROFILES`). The web UI hides navigation, settings and actions for
 * components that are not installed.
 *
 * **Fail-open in two places:** while nothing is loaded yet and when the fetch
 * fails, everything counts as installed. A feature must never disappear because
 * of a network hiccup (same stance as `useSetupStatus`).
 *
 * **No flicker:** the last server state is kept in `localStorage` and read
 * synchronously at startup. Returning users see the right menu immediately;
 * only the very first visit on a stripped-down box can hide a feature once.
 */

const STORAGE_KEY = STORAGE_KEYS.CAPABILITIES;

const ALL_INSTALLED: CapabilitiesResponse = FEATURE_KEYS.reduce((acc, key) => {
  acc[key] = { installed: true, running: true, healthy: true };
  return acc;
}, {} as CapabilitiesResponse);

function isFeatureCapability(value: unknown): value is FeatureCapability {
  return (
    !!value &&
    typeof value === 'object' &&
    typeof (value as FeatureCapability).installed === 'boolean'
  );
}

function loadCached(): CapabilitiesResponse {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return ALL_INSTALLED;
    const parsed = JSON.parse(raw) as Partial<Record<FeatureKey, unknown>>;
    // Unknown or broken entries fall back to "installed".
    return FEATURE_KEYS.reduce((acc, key) => {
      const entry = parsed[key];
      acc[key] = isFeatureCapability(entry) ? entry : ALL_INSTALLED[key];
      return acc;
    }, {} as CapabilitiesResponse);
  } catch {
    return ALL_INSTALLED;
  }
}

interface CapabilitiesContextType {
  capabilities: CapabilitiesResponse;
  /** true until the first server fetch is through (the cache value is shown until then). */
  loading: boolean;
  refresh: () => Promise<void>;
}

const CapabilitiesCtx = createContext<CapabilitiesContextType>({
  capabilities: ALL_INSTALLED,
  loading: true,
  refresh: async () => undefined,
});

export const CapabilitiesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse>(loadCached);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await capabilitiesApi.get();
      setCapabilities(data);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      } catch {
        // localStorage not available (private mode) - not a big deal.
      }
    } catch {
      // Fetch failed: stay with the cache/default value (fail-open).
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <CapabilitiesCtx.Provider value={{ capabilities, loading, refresh }}>
      {children}
    </CapabilitiesCtx.Provider>
  );
};

export const useCapabilities = (): CapabilitiesContextType => useContext(CapabilitiesCtx);

/** Convenience: is a component installed? When in doubt, `true`. */
export const useFeatureInstalled = (key: FeatureKey): boolean =>
  useContext(CapabilitiesCtx).capabilities[key]?.installed ?? true;
