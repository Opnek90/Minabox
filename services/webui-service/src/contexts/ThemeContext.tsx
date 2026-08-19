import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

export type ThemeMode = 'light' | 'dark';
export type ColorPresetKey =
  | 'orange' | 'blue' | 'green' | 'purple' | 'red' | 'pink' | 'indigo' | 'teal';
/** Schriftgroesse der gesamten Oberflaeche – nicht Zoom, siehe `applyTokens`. */
export type FontScale = 'standard' | 'large';

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
  pink:   { main: '#c2185b', light: '#fa5788', dark: '#8c0032', contrastText: '#ffffff' },
  indigo: { main: '#283593', light: '#5f5fc4', dark: '#001064', contrastText: '#ffffff' },
  teal:   { main: '#00695c', light: '#439889', dark: '#003d33', contrastText: '#ffffff' },
};

/**
 * Wurzel-Schriftgroessen der beiden Stufen. Gestellt wird `<html>`, nicht MUIs
 * `typography.fontSize`: Damit waechst alles, was in `rem` gesetzt ist – also
 * saemtliche Textgroessen der App inklusive der `caption`-Anpassung in
 * `main.tsx` –, waehrend px-Masse wie Leistenhoehen, Symbolgroessen und der
 * Klebe-Abstand der Bereichsleiste stehen bleiben. Es wird also die Schrift
 * groesser, nicht die Oberflaeche gezoomt.
 */
const FONT_SCALE_PX: Record<FontScale, string> = {
  standard: '16px',
  large: '18px',
};

const LS_MODE  = 'minabox-theme-mode';
const LS_COLOR = 'minabox-theme-color';
const LS_FONT  = 'minabox-font-scale';

interface ThemeContextType {
  mode: ThemeMode;
  colorPreset: ColorPresetKey;
  fontScale: FontScale;
  toggleMode: () => void;
  setColorPreset: (preset: ColorPresetKey) => void;
  setFontScale: (scale: FontScale) => void;
  primaryColor: ColorPreset;
}

const ThemeCtx = createContext<ThemeContextType>({
  mode: 'light',
  colorPreset: 'orange',
  fontScale: 'standard',
  toggleMode: () => undefined,
  setColorPreset: () => undefined,
  setFontScale: () => undefined,
  primaryColor: COLOR_PRESETS.orange,
});

/** Apply design tokens as CSS custom properties on <html> so Tailwind
 *  utility classes like bg-[--color-accent] resolve at runtime. */
function applyTokens(preset: ColorPreset, mode: ThemeMode, fontScale: FontScale): void {
  const root = document.documentElement;
  root.style.setProperty('--color-accent',          preset.main);
  root.style.setProperty('--color-accent-light',    preset.light);
  root.style.setProperty('--color-accent-dark',     preset.dark);
  root.style.setProperty('--color-accent-contrast', preset.contrastText);
  root.setAttribute('data-theme', mode);
  root.style.fontSize = FONT_SCALE_PX[fontScale];
}

export const ThemeContextProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem(LS_MODE);
    return stored === 'dark' ? 'dark' : 'light';
  });

  const [colorPreset, setColorPresetState] = useState<ColorPresetKey>(() => {
    const stored = localStorage.getItem(LS_COLOR);
    return (stored && stored in COLOR_PRESETS) ? (stored as ColorPresetKey) : 'orange';
  });

  const [fontScale, setFontScaleState] = useState<FontScale>(() => {
    const stored = localStorage.getItem(LS_FONT);
    return stored === 'large' ? 'large' : 'standard';
  });

  const primaryColor = useMemo(() => COLOR_PRESETS[colorPreset], [colorPreset]);

  // Sync CSS custom properties whenever mode or colorPreset changes
  useEffect(() => {
    applyTokens(primaryColor, mode, fontScale);
  }, [primaryColor, mode, fontScale]);

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

  const setFontScale = useCallback((scale: FontScale) => {
    localStorage.setItem(LS_FONT, scale);
    setFontScaleState(scale);
  }, []);

  return (
    <ThemeCtx.Provider
      value={{ mode, colorPreset, fontScale, toggleMode, setColorPreset, setFontScale, primaryColor }}
    >
      {children}
    </ThemeCtx.Provider>
  );
};

export const useThemeContext = (): ThemeContextType => useContext(ThemeCtx);
