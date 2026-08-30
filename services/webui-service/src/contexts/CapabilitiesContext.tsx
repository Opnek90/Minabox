import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  capabilitiesApi,
  FEATURE_KEYS,
  type CapabilitiesResponse,
  type FeatureCapability,
  type FeatureKey,
} from '@/api/capabilities';

/**
 * Welche optionalen Komponenten diese Box hat.
 *
 * Quelle ist `GET /system/capabilities` (Backend liest `COMPOSE_PROFILES`).
 * Die WebUI blendet Navigation, Einstellungen und Aktionen fuer nicht
 * installierte Komponenten aus.
 *
 * **Fail-open an zwei Stellen:** Solange noch nichts geladen ist und wenn der
 * Abruf scheitert, gilt alles als installiert. Ein Feature darf nie wegen eines
 * Netzwerk-Schluckaufs verschwinden (gleiche Haltung wie `useSetupStatus`).
 *
 * **Kein Flackern:** Der letzte Serverstand wird in `localStorage` gehalten und
 * synchron beim Start eingelesen. Wiederkehrende Nutzer sehen sofort das
 * richtige Menue; nur der allererste Aufruf auf einer abgespeckten Box kann ein
 * Feature einmal ausblenden.
 */

const STORAGE_KEY = 'minabox.capabilities';

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
    // Unbekannte oder kaputte Eintraege fallen auf "installiert" zurueck.
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
  /** true bis der erste Serverabruf durch ist (Cache-Wert wird solange gezeigt). */
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
        // localStorage nicht verfuegbar (Privatmodus) - kein Beinbruch.
      }
    } catch {
      // Abruf fehlgeschlagen: beim Cache-/Default-Wert bleiben (fail-open).
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

/** Bequemlichkeit: ist eine Komponente installiert? Im Zweifel `true`. */
export const useFeatureInstalled = (key: FeatureKey): boolean =>
  useContext(CapabilitiesCtx).capabilities[key]?.installed ?? true;
