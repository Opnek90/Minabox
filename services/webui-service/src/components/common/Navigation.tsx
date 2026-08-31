import React from 'react';
import {
  Box,
  BottomNavigation,
  BottomNavigationAction,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import NfcIcon from '@mui/icons-material/Nfc';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import BarChartIcon from '@mui/icons-material/BarChart';
import SettingsIcon from '@mui/icons-material/Settings';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useFeatureInstalled } from '@/contexts/CapabilitiesContext';

const DRAWER_WIDTH = 220;
/**
 * Icon rail for the tablet level. 72px is the Material 3 standard and the
 * narrowest width a 48px touch target plus edge air still fits into. The full
 * drawer costs a fifth of the page on a 1024px tablet; the rail gives 148px of
 * that back to the content without hiding the navigation.
 */
const RAIL_WIDTH = 72;
// MUI BottomNavigation default height. Exported so fixed-position siblings
// (MiniPlayer, MediaFab) can offset themselves above it on mobile.
const MOBILE_BOTTOM_NAV_HEIGHT = 56;
/**
 * Bottom device safe area (home indicator / gesture bar). With
 * `viewport-fit=cover` in index.html the viewport extends under the bar -
 * fixed elements have to add the value themselves, otherwise BottomNav labels
 * and the MiniPlayer sit under it. On devices without a gesture bar the value
 * is 0px, so the layouts do not change there.
 */
const SAFE_AREA_BOTTOM = 'env(safe-area-inset-bottom, 0px)';

interface NavItem {
  path: string;
  labelKey: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { path: '/player', labelKey: 'navigation.player', icon: <PlayCircleOutlineIcon /> },
  { path: '/rfid', labelKey: 'navigation.rfid', icon: <NfcIcon /> },
  { path: '/media', labelKey: 'navigation.media', icon: <LibraryMusicIcon /> },
  // Short form: in the BottomNav five entries share ~390px, so ~70px of text
  // width per entry - "Parent dashboard" wraps to two lines there and blows up
  // the bar. The full name is still used as the page title.
  { path: '/dashboard', labelKey: 'navigation.dashboard_short', icon: <BarChartIcon /> },
  { path: '/admin', labelKey: 'navigation.admin', icon: <SettingsIcon /> },
];

/**
 * `navItems` filtered by installed components. Currently only the cards entry
 * (`/rfid`) hangs off an optional component; without a reader it only leads to
 * a page whose core functions (learn mode, scan) do nothing.
 */
const useVisibleNavItems = (): NavItem[] => {
  const rfidInstalled = useFeatureInstalled('rfid');
  return navItems.filter((item) => item.path !== '/rfid' || rfidInstalled);
};

interface NavigationProps {
  /**
   * `full` shows icon + label side by side (desktop), `rail` stacks both in
   * 72px width (tablet). The entries and their order are identical in both
   * variants, so muscle memory does not break when the device is rotated.
   */
  variant?: 'full' | 'rail';
}

/** Permanent side navigation for tablet (rail) and desktop (drawer). */
export const Navigation: React.FC<NavigationProps> = ({ variant = 'full' }) => {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const location = useLocation();
  const isRail = variant === 'rail';
  const width = isRail ? RAIL_WIDTH : DRAWER_WIDTH;
  const visibleItems = useVisibleNavItems();

  return (
    <Drawer
      variant="permanent"
      open
      sx={{
        width,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width,
          boxSizing: 'border-box',
        },
      }}
    >
      <Box>
        <Toolbar />
        <List>
          {visibleItems.map((item) => {
            const isActive = location.pathname.startsWith(item.path);
            return (
              <ListItem key={item.path} disablePadding sx={isRail ? { justifyContent: 'center' } : undefined}>
                <Tooltip title={isRail ? t(item.labelKey) : ''} placement="right">
                <ListItemButton
                  selected={isActive}
                  onClick={() => navigate(item.path)}
                  aria-current={isActive ? 'page' : undefined}
                  sx={{
                    ...(isRail && {
                      flexDirection: 'column',
                      gap: 0.25,
                      mx: 1,
                      my: 0.25,
                      px: 0,
                      py: 1,
                      borderRadius: 2,
                      minHeight: 56,
                    }),
                    '&.Mui-selected': {
                      // primary.dark, not .light or .main: white text/icons need
                      // 4.5:1 (WCAG AA, normal text). .light gives ~2.2:1 for every
                      // preset; .main still falls short (~3.8:1) for the default
                      // orange preset. .dark clears 4.5:1 across all 5 presets.
                      backgroundColor: 'primary.dark',
                      color: 'primary.contrastText',
                      '&:hover': { filter: 'brightness(0.85)' },
                      '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
                    },
                  }}
                >
                  <ListItemIcon sx={isRail ? { minWidth: 0, justifyContent: 'center' } : undefined}>
                    {item.icon}
                  </ListItemIcon>
                  {isRail ? (
                    // The label stays visible in the rail too: icon-only
                    // navigation is unreadable without hover (touch).
                    <Typography
                      variant="caption"
                      sx={{
                        fontSize: '0.65rem',
                        lineHeight: 1.2,
                        fontWeight: 600,
                        maxWidth: '100%',
                        px: 0.25,
                        textAlign: 'center',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {t(item.labelKey)}
                    </Typography>
                  ) : (
                    <ListItemText primary={t(item.labelKey)} />
                  )}
                </ListItemButton>
                </Tooltip>
              </ListItem>
            );
          })}
        </List>
      </Box>
    </Drawer>
  );
};

/**
 * Mobile primary navigation: a fixed bottom tab bar instead of a hamburger +
 * temporary drawer. Thumb-reachable on a phone, matches the pattern of every
 * music app; a side drawer opened from the top-left corner is the worst
 * reachable zone on a device mostly operated one-handed.
 */
export const MobileBottomNav: React.FC = () => {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const location = useLocation();
  const visibleItems = useVisibleNavItems();
  const activeIndex = visibleItems.findIndex((item) => location.pathname.startsWith(item.path));

  return (
    <Paper
      elevation={8}
      sx={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 1100,
        borderRadius: 0,
        borderTop: 1,
        borderColor: 'divider',
        pb: SAFE_AREA_BOTTOM,
      }}
    >
      <BottomNavigation
        showLabels
        value={activeIndex === -1 ? false : activeIndex}
        sx={{ height: MOBILE_BOTTOM_NAV_HEIGHT }}
      >
        {visibleItems.map((item) => (
          <BottomNavigationAction
            key={item.path}
            label={t(item.labelKey)}
            icon={item.icon}
            onClick={() => navigate(item.path)}
            sx={{ minWidth: 0, px: 0.5 }}
          />
        ))}
      </BottomNavigation>
    </Paper>
  );
};

export { DRAWER_WIDTH, RAIL_WIDTH, MOBILE_BOTTOM_NAV_HEIGHT, SAFE_AREA_BOTTOM };
