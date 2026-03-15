import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

export type ViewMode = 'card' | 'list';
export type SortDir = 'asc' | 'desc';

export interface SortState {
  key: string;
  dir: SortDir;
}

export interface UserPrefs {
  viewMode: Record<string, ViewMode>;
  sort: Record<string, SortState>;
}

const STORAGE_KEY = 'minabox.prefs';

const DEFAULTS: UserPrefs = {
  viewMode: {
    rfid: 'list',
    tracks: 'list',
    playlists: 'card',
    streams: 'list',
    podcasts: 'card',
  },
  sort: {
    rfid: { key: 'name', dir: 'asc' },
    tracks: { key: 'title', dir: 'asc' },
    streams: { key: 'title', dir: 'asc' },
    podcasts: { key: 'title', dir: 'asc' },
  },
};

function loadPrefs(): UserPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<UserPrefs>;
    return {
      viewMode: { ...DEFAULTS.viewMode, ...(parsed.viewMode ?? {}) },
      sort: { ...DEFAULTS.sort, ...(parsed.sort ?? {}) },
    };
  } catch {
    return DEFAULTS;
  }
}

interface UserPrefsContextType {
  prefs: UserPrefs;
  setViewMode: (scope: string, mode: ViewMode) => void;
  setSort: (scope: string, key: string, dir: SortDir) => void;
  resetPrefs: () => void;
}

const UserPrefsCtx = createContext<UserPrefsContextType>({
  prefs: DEFAULTS,
  setViewMode: () => undefined,
  setSort: () => undefined,
  resetPrefs: () => undefined,
});

export const UserPrefsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Synchronous read from localStorage on first render — no flash
  const [prefs, setPrefs] = useState<UserPrefs>(loadPrefs);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  }, [prefs]);

  const setViewMode = useCallback((scope: string, mode: ViewMode) => {
    setPrefs((prev) => ({
      ...prev,
      viewMode: { ...prev.viewMode, [scope]: mode },
    }));
  }, []);

  const setSort = useCallback((scope: string, key: string, dir: SortDir) => {
    setPrefs((prev) => ({
      ...prev,
      sort: { ...prev.sort, [scope]: { key, dir } },
    }));
  }, []);

  const resetPrefs = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setPrefs(DEFAULTS);
  }, []);

  return (
    <UserPrefsCtx.Provider value={{ prefs, setViewMode, setSort, resetPrefs }}>
      {children}
    </UserPrefsCtx.Provider>
  );
};

export const useUserPrefs = (): UserPrefsContextType => useContext(UserPrefsCtx);
