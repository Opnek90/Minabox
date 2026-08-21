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
  filter: Record<string, string>;
  treeCollapsed: Record<string, boolean>;
  pageSize: Record<string, number>;
}

const STORAGE_KEY = 'minabox.prefs';

const DEFAULTS: UserPrefs = {
  viewMode: {
    rfid: 'list',
    tracks: 'list',
    playlists: 'card',
    streams: 'list',
    podcasts: 'list',
  },
  sort: {
    rfid: { key: 'name', dir: 'asc' },
    tracks: { key: 'title', dir: 'asc' },
    streams: { key: 'title', dir: 'asc' },
    podcasts: { key: 'title', dir: 'asc' },
  },
  filter: {
    rfid: 'all',
    tracks: 'all',
  },
  treeCollapsed: {},
  pageSize: {},
};

function loadPrefs(): UserPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<UserPrefs>;
    return {
      viewMode: { ...DEFAULTS.viewMode, ...(parsed.viewMode ?? {}) },
      sort: { ...DEFAULTS.sort, ...(parsed.sort ?? {}) },
      filter: { ...DEFAULTS.filter, ...(parsed.filter ?? {}) },
      treeCollapsed: { ...DEFAULTS.treeCollapsed, ...(parsed.treeCollapsed ?? {}) },
      pageSize: { ...DEFAULTS.pageSize, ...(parsed.pageSize ?? {}) },
    };
  } catch {
    return DEFAULTS;
  }
}

interface UserPrefsContextType {
  prefs: UserPrefs;
  setViewMode: (scope: string, mode: ViewMode) => void;
  setSort: (scope: string, key: string, dir: SortDir) => void;
  setFilter: (scope: string, value: string) => void;
  setTreeCollapsed: (scope: string, collapsed: boolean) => void;
  setPageSize: (scope: string, size: number) => void;
  resetPrefs: () => void;
}

const UserPrefsCtx = createContext<UserPrefsContextType>({
  prefs: DEFAULTS,
  setViewMode: () => undefined,
  setSort: () => undefined,
  setFilter: () => undefined,
  setTreeCollapsed: () => undefined,
  setPageSize: () => undefined,
  resetPrefs: () => undefined,
});

export const UserPrefsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
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

  const setFilter = useCallback((scope: string, value: string) => {
    setPrefs((prev) => ({
      ...prev,
      filter: { ...prev.filter, [scope]: value },
    }));
  }, []);

  const setTreeCollapsed = useCallback((scope: string, collapsed: boolean) => {
    setPrefs((prev) => ({
      ...prev,
      treeCollapsed: { ...prev.treeCollapsed, [scope]: collapsed },
    }));
  }, []);

  const setPageSize = useCallback((scope: string, size: number) => {
    setPrefs((prev) => ({
      ...prev,
      pageSize: { ...prev.pageSize, [scope]: size },
    }));
  }, []);

  const resetPrefs = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setPrefs(DEFAULTS);
  }, []);

  return (
    <UserPrefsCtx.Provider value={{ prefs, setViewMode, setSort, setFilter, setTreeCollapsed, setPageSize, resetPrefs }}>
      {children}
    </UserPrefsCtx.Provider>
  );
};

export const useUserPrefs = (): UserPrefsContextType => useContext(UserPrefsCtx);
