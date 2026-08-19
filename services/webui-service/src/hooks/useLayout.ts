import { useMemo } from 'react';
import { useMediaQuery, useTheme } from '@mui/material';

/**
 * Drei Layout-Stufen statt der bisherigen Zweiteilung.
 *
 * Vorher gab es zwei *unterschiedliche* Umschaltpunkte im Code: die Navigation
 * kippte bei `md` (900px), Dichte und Dialoge bei `sm` (600px). Dazwischen
 * entstand ein Band, in dem sich die App weder wie Handy noch wie Desktop
 * verhielt – am schlimmsten bei 1024px (iPad Pro hochkant): permanenter
 * 220px-Drawer plus volle Desktop-Dichte liessen 804px Restbreite fuer
 * dreispaltige Kartenraster uebrig.
 *
 *   mobile   <  600px  – Handy: BottomNav, eine Spalte, Vollbild-Dialoge
 *   tablet   600–1199  – Icon-Rail (72px), zwei Spalten, mittlere Dichte
 *   desktop  >= 1200px – voller Drawer (220px), drei Spalten, volle Dichte
 *
 * Die Grenzen sind bewusst MUIs `sm` und `lg`, damit `sx`-Props ohne eigene
 * Breakpoint-Namen dieselben Kanten treffen (z. B. `xs=12 sm=6 lg=4`).
 */
export type LayoutTier = 'mobile' | 'tablet' | 'desktop';

export interface Layout {
  tier: LayoutTier;
  /** < 600px – einspaltig, BottomNav, Vollbild-Sheets. */
  isMobile: boolean;
  /** 600–1199px – Icon-Rail, zweispaltig. */
  isTablet: boolean;
  /** >= 1200px – voller Drawer, dreispaltig. */
  isDesktop: boolean;
  /**
   * Alles unterhalb Desktop. Fuer Abstaende und Schriftgroessen, wo Tablet und
   * Handy dieselbe Behandlung vertragen.
   */
  isCompact: boolean;
  /**
   * Ab Tablet aufwaerts. Fuer Bedienelemente, die genug Breite brauchen, um
   * nebeneinander statt in einem Popover zu stehen (Sortierung, Filter,
   * Zeilenaktionen).
   */
  hasRoomForInlineControls: boolean;
  /** Seitenpolsterung in Theme-Einheiten, je Stufe. */
  pagePadding: number;
}

export const useLayout = (): Layout => {
  const theme = useTheme();
  // Zwei Queries statt drei: `up` ist ueberlappend, die Stufe ergibt sich aus
  // der hoechsten zutreffenden Grenze.
  const atLeastTablet = useMediaQuery(theme.breakpoints.up('sm'));
  const atLeastDesktop = useMediaQuery(theme.breakpoints.up('lg'));

  return useMemo(() => {
    const tier: LayoutTier = atLeastDesktop ? 'desktop' : atLeastTablet ? 'tablet' : 'mobile';
    return {
      tier,
      isMobile: tier === 'mobile',
      isTablet: tier === 'tablet',
      isDesktop: tier === 'desktop',
      isCompact: tier !== 'desktop',
      hasRoomForInlineControls: tier !== 'mobile',
      pagePadding: tier === 'mobile' ? 1.5 : tier === 'tablet' ? 2 : 3,
    };
  }, [atLeastTablet, atLeastDesktop]);
};
