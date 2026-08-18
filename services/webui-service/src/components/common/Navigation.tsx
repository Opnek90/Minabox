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
} from '@mui/material';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import NfcIcon from '@mui/icons-material/Nfc';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import BarChartIcon from '@mui/icons-material/BarChart';
import SettingsIcon from '@mui/icons-material/Settings';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const DRAWER_WIDTH = 220;
// MUI BottomNavigation default height. Exported so fixed-position siblings
// (MiniPlayer, MediaFab) can offset themselves above it on mobile.
const MOBILE_BOTTOM_NAV_HEIGHT = 56;
/**
 * Untere Geraete-Schutzzone (Home-Indicator / Gestenleiste). Mit
 * `viewport-fit=cover` in der index.html reicht der Viewport bis unter die
 * Leiste – fixierte Elemente muessen den Wert selbst aufschlagen, sonst liegen
 * BottomNav-Labels und MiniPlayer darunter. Auf Geraeten ohne Gestenleiste
 * ist der Wert 0px, die Layouts aendern sich dort also nicht.
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
  { path: '/dashboard', labelKey: 'navigation.dashboard', icon: <BarChartIcon /> },
  { path: '/admin', labelKey: 'navigation.admin', icon: <SettingsIcon /> },
];

/** Desktop side navigation (permanent drawer). */
export const Navigation: React.FC = () => {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Drawer
      variant="permanent"
      open
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: DRAWER_WIDTH,
          boxSizing: 'border-box',
        },
      }}
    >
      <Box>
        <Toolbar />
        <List>
          {navItems.map((item) => {
            const isActive = location.pathname.startsWith(item.path);
            return (
              <ListItem key={item.path} disablePadding>
                <ListItemButton
                  selected={isActive}
                  onClick={() => navigate(item.path)}
                  sx={{
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
                  <ListItemIcon>{item.icon}</ListItemIcon>
                  <ListItemText primary={t(item.labelKey)} />
                </ListItemButton>
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
  const activeIndex = navItems.findIndex((item) => location.pathname.startsWith(item.path));

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
        {navItems.map((item) => (
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

export { DRAWER_WIDTH, MOBILE_BOTTOM_NAV_HEIGHT, SAFE_AREA_BOTTOM };
