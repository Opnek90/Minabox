import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

export type ThemeMode = 'light' | 'dark';
export type ColorPresetKey = 'orange' | 'blue' | 'green' | 'purple' | 'red';

export interface ColorPreset {
  main: string;
  light: string;
  dark: string;
  contrastText: string;
}

export const COLOR_PRESETS: Record<ColorPresetKey, ColorPreset> = {
  orange: { main: '#e65100', light: '#ff8a50', dark: '#ac1900', contrastText: '#ffffff' },
  blue:   { main: '#1565c0', light: '#5e92f3', dark: '#003c8f', contrastText: '#ffffff' },
  green:  { main: '#2e7d32', light: '#60ad5e', dark: '#005005', contrastText: '#ffffff' },
  purple: { main: '#6a1b9a', light: '#9c4dcc', dark: '#38006b', contrastText: '#ffffff' },
  red:    { main: '#c62828', light: '#ff5f52', dark: '#8e0000', contrastText: '#ffffff' },
};

const LS_MODE  = 'minabox-theme-mode';
const LS_COLOR = 'minabox-theme-color';

interface ThemeContextType {
  mode: ThemeMode;
  colorPreset: ColorPresetKey;
  toggleMode: () => void;
  setColorPreset: (preset: ColorPresetKey) => void;
  primaryColor: ColorPreset;
}

const ThemeCtx = createContext<ThemeContextType>({
  mode: 'light',
  colorPreset: 'orange',
  toggleMode: () => undefined,
  setColorPreset: () => undefined,
  primaryColor: COLOR_PRESETS.orange,
});

export const ThemeContextProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem(LS_MODE);
    return stored === 'dark' ? 'dark' : 'light';
  });

  const [colorPreset, setColorPresetState] = useState<ColorPresetKey>(() => {
    const stored = localStorage.getItem(LS_COLOR);
    return (stored && stored in COLOR_PRESETS) ? (stored as ColorPresetKey) : 'orange';
  });

  const toggleMode = useCallback(() => {
    setMode((prev) => {
      const next = prev === 'light' ? 'dark' : 'light';
      localStorage.setItem(LS_MODE, next);
      return next;
    });
  }, []);

  const setColorPreset = useCallback((preset: ColorPresetKey) => {
    localStorage.setItem(LS_COLOR, preset);
    setColorPresetState(preset);
  }, []);

  const primaryColor = useMemo(() => COLOR_PRESETS[colorPreset], [colorPreset]);

  return (
    <ThemeCtx.Provider value={{ mode, colorPreset, toggleMode, setColorPreset, primaryColor }}>
      {children}
    </ThemeCtx.Provider>
  );
};

export const useThemeContext = (): ThemeContextType => useContext(ThemeCtx);
