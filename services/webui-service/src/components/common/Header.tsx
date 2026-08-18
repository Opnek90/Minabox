import React, { useEffect, useState } from 'react';
import {
  AppBar,
  Box,
  Chip,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import WifiIcon from '@mui/icons-material/Wifi';
import WifiOffIcon from '@mui/icons-material/WifiOff';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/WebSocketContext';
import SearchIcon from '@mui/icons-material/Search';
import { CommandPalette } from '@/components/common/CommandPalette';

export const Header: React.FC = () => {
  const { t } = useTranslation('common');
  const { isConnected } = useWebSocket();
  const [logoError, setLogoError] = useState(false);
  const [logoLoaded, setLogoLoaded] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  // Re-attempt logo on mount so it picks up a freshly uploaded image
  useEffect(() => {
    setLogoError(false);
    setLogoLoaded(false);
  }, []);

  return (
    <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
      <Toolbar>
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

{/* Sichtbares Suchfeld statt reinem Icon: die Palette ist die globale Suche
    (Navigation, Einstellungen, Mediathek) und war vorher nicht auffindbar. */}
<Tooltip title={t('command_palette.title')}>
  <Box
    component="button"
    type="button"
    onClick={() => setCommandPaletteOpen(true)}
    aria-label={t('command_palette.title')}
    sx={{
      display: 'flex',
      alignItems: 'center',
      gap: 0.75,
      ml: 1.5,
      px: 1.25,
      py: 0.5,
      font: 'inherit',
      fontSize: '0.8rem',
      color: 'inherit',
      cursor: 'pointer',
      borderRadius: 1,
      border: '1px solid rgba(255,255,255,0.5)',
      bgcolor: 'transparent',
      '&:hover': { bgcolor: 'rgba(255,255,255,0.12)' },
    }}
  >
    <SearchIcon fontSize="small" />
    <Box
      component="span"
      sx={{ display: { xs: 'none', md: 'inline' }, whiteSpace: 'nowrap' }}
    >
      {t('command_palette.placeholder')}
    </Box>
  </Box>
</Tooltip>

<CommandPalette
  open={commandPaletteOpen}
  onOpen={() => setCommandPaletteOpen(true)}
  onClose={() => setCommandPaletteOpen(false)}
/>
      </Toolbar>
    </AppBar>
  );
};
