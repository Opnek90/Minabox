import React from 'react';
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
} from '@mui/material';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import NfcIcon from '@mui/icons-material/Nfc';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import SettingsIcon from '@mui/icons-material/Settings';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const DRAWER_WIDTH = 220;

interface NavItem {
  path: string;
  labelKey: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { path: '/player', labelKey: 'navigation.player', icon: <PlayCircleOutlineIcon /> },
  { path: '/rfid', labelKey: 'navigation.rfid', icon: <NfcIcon /> },
  { path: '/media', labelKey: 'navigation.media', icon: <LibraryMusicIcon /> },
  { path: '/admin', labelKey: 'navigation.admin', icon: <SettingsIcon /> },
];

interface NavigationProps {
  open?: boolean;
  variant?: 'permanent' | 'temporary';
  onClose?: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  open = true,
  variant = 'permanent',
  onClose,
}) => {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const location = useLocation();

  const handleNavigate = (path: string) => {
    navigate(path);
    if (onClose) onClose();
  };

  const drawerContent = (
    <Box>
      <Toolbar />
      <List>
        {navItems.map((item) => {
          const isActive = location.pathname.startsWith(item.path);
          return (
            <ListItem key={item.path} disablePadding>
              <ListItemButton
                selected={isActive}
                onClick={() => handleNavigate(item.path)}
                sx={{
                  '&.Mui-selected': {
                    backgroundColor: 'primary.light',
                    color: 'primary.contrastText',
                    '&:hover': { backgroundColor: 'primary.main' },
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
  );

  return (
    <Drawer
      variant={variant}
      open={open}
      onClose={onClose}
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: DRAWER_WIDTH,
          boxSizing: 'border-box',
        },
      }}
    >
      {drawerContent}
    </Drawer>
  );
};

export { DRAWER_WIDTH };
