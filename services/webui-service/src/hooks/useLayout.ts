import { useMemo } from 'react';
import { useMediaQuery, useTheme } from '@mui/material';

/**
 * Three layout levels instead of the previous two-way split.
 *
 * There used to be two *different* switch points in the code: the navigation
 * flipped at `md` (900px), density and dialogs at `sm` (600px). In between, a
 * band emerged where the app behaved neither like a phone nor like a desktop -
 * worst at 1024px (iPad Pro portrait): a permanent 220px drawer plus full
 * desktop density left 804px of width for three-column card grids.
 *
 *   mobile   <  600px  - phone: BottomNav, one column, full-screen dialogs
 *   tablet   600-1199   - icon rail (72px), two columns, medium density
 *   desktop  >= 1200px - full drawer (220px), three columns, full density
 *
 * The boundaries are deliberately MUI's `sm` and `lg`, so `sx` props without
 * their own breakpoint names hit the same edges (e.g. `xs=12 sm=6 lg=4`).
 */
export type LayoutTier = 'mobile' | 'tablet' | 'desktop';

export interface Layout {
  tier: LayoutTier;
  /** < 600px - one column, BottomNav, full-screen sheets. */
  isMobile: boolean;
  /** 600-1199px - icon rail, two columns. */
  isTablet: boolean;
  /** >= 1200px - full drawer, three columns. */
  isDesktop: boolean;
  /**
   * Everything below desktop. For spacing and font sizes where tablet and
   * phone tolerate the same treatment.
   */
  isCompact: boolean;
  /**
   * From tablet up. For controls that need enough width to stand side by side
   * instead of in a popover (sorting, filters, row actions).
   */
  hasRoomForInlineControls: boolean;
  /** Page padding in theme units, per level. */
  pagePadding: number;
}

export const useLayout = (): Layout => {
  const theme = useTheme();
  // Two queries instead of three: `up` overlaps, the level follows from the
  // highest matching boundary.
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
