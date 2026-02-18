import React, { useEffect, useState } from 'react';
import {
  AppBar,
  Box,
  Chip,
  IconButton,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import WifiIcon from '@mui/icons-material/Wifi';
import WifiOffIcon from '@mui/icons-material/WifiOff';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/WebSocketContext';

interface HeaderProps {
  onMenuToggle?: () => void;
  showMenuButton?: boolean;
}

export const Header: React.FC<HeaderProps> = ({ onMenuToggle, showMenuButton = false }) => {
  const { t } = useTranslation('common');
  const { isConnected } = useWebSocket();
  const [logoError, setLogoError] = useState(false);
  const [logoLoaded, setLogoLoaded] = useState(false);

  // Re-attempt logo on mount so it picks up a freshly uploaded image
  useEffect(() => {
    setLogoError(false);
    setLogoLoaded(false);
  }, []);

  return (
    <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
      <Toolbar>
        {showMenuButton && (
          <IconButton color="inherit" edge="start" onClick={onMenuToggle} sx={{ mr: 1 }}>
            <MenuIcon />
          </IconButton>
        )}

        {/* Custom logo (if uploaded) */}
        {!logoError && (
          <Box
            component="img"
            src="/static/logo.png"
            alt="Logo"
            onLoad={() => setLogoLoaded(true)}
            onError={() => setLogoError(true)}
            sx={{
              height: 32,
              mr: 1.5,
              display: logoLoaded ? 'block' : 'none',
              objectFit: 'contain',
            }}
          />
        )}

        <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: 700 }}>
          {t('app_name')}
        </Typography>

        {/* WebSocket status */}
        <Tooltip title={isConnected ? t('websocket.connected') : t('websocket.disconnected')}>
          <Chip
            icon={isConnected ? <WifiIcon fontSize="small" /> : <WifiOffIcon fontSize="small" />}
            label={isConnected ? t('status.connected') : t('status.disconnected')}
            color={isConnected ? 'success' : 'error'}
            variant="outlined"
            size="small"
            sx={{ color: 'white', borderColor: 'rgba(255,255,255,0.5)' }}
          />
        </Tooltip>
      </Toolbar>
    </AppBar>
  );
};
