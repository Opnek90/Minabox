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
 * Icon-Rail fuer die Tablet-Stufe. 72px ist Material-3-Standard und die
 * schmalste Breite, in die ein 48px-Touchziel plus Randluft noch passt. Der
 * volle Drawer kostet auf einem 1024px-Tablet ein Fuenftel der Seite; die Rail
 * gibt 148px davon an den Inhalt zurueck, ohne die Navigation zu verstecken.
 */
const RAIL_WIDTH = 72;
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
  // Kurzform: In der BottomNav teilen sich fuenf Eintraege ~390px, also ~70px
  // Textbreite je Eintrag – "Eltern-Dashboard" bricht dort auf zwei Zeilen und
  // sprengt die Leiste. Der volle Name steht weiterhin als Seitentitel.
  { path: '/dashboard', labelKey: 'navigation.dashboard_short', icon: <BarChartIcon /> },
  { path: '/admin', labelKey: 'navigation.admin', icon: <SettingsIcon /> },
];

/**
 * `navItems` gefiltert nach installierten Komponenten. Aktuell haengt nur der
 * Karten-Eintrag (`/rfid`) an einer optionalen Komponente; ohne Leser fuehrt er
 * nur auf eine Seite, deren Kernfunktionen (Lernmodus, Scan) nichts tun.
 */
const useVisibleNavItems = (): NavItem[] => {
  const rfidInstalled = useFeatureInstalled('rfid');
  return navItems.filter((item) => item.path !== '/rfid' || rfidInstalled);
};

interface NavigationProps {
  /**
   * `full` zeigt Icon + Beschriftung nebeneinander (Desktop), `rail` stapelt
   * beide in 72px Breite (Tablet). Die Eintraege und ihre Reihenfolge sind in
   * beiden Varianten identisch, damit die Muskelerinnerung beim Drehen des
   * Geraets nicht bricht.
   */
  variant?: 'full' | 'rail';
}

/** Permanente Seitennavigation fuer Tablet (Rail) und Desktop (Drawer). */
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
                    // Beschriftung bleibt auch in der Rail sichtbar: reine
                    // Icon-Navigation ist ohne Hover (Touch) nicht entzifferbar.
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
