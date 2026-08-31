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
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useWebSocket } from '@/contexts/WebSocketContext';
import SearchIcon from '@mui/icons-material/Search';
import { CommandPalette } from '@/components/common/CommandPalette';
import { ALERT_UPDATE_AVAILABLE, useSystemAlerts } from '@/hooks/useSystemAlerts';

/**
 * The two status chips in the app bar. Outlined on a coloured bar, so both the
 * text and the border have to be set explicitly.
 *
 * The icon margin is not the MUI default: a small chip puts its icon 4px from
 * the border, which on an outlined chip reads as the icon touching the frame.
 * 8px gives it the same air the label has on the other side.
 */
const STATUS_CHIP_SX = {
  color: 'white',
  borderColor: 'rgba(255,255,255,0.5)',
  '& .MuiChip-icon': { ml: 1, mr: -0.25 },
} as const;

export const Header: React.FC = () => {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const { isConnected } = useWebSocket();
  const updateAvailable = useSystemAlerts().some((a) => a.code === ALERT_UPDATE_AVAILABLE);
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

{/* Update hint: only an icon, so the header keeps its height - the full text
    comes via a tooltip and on the maintenance page. */}
{updateAvailable && (
  <Tooltip title={t('alerts.update_available')}>
    <Chip
      icon={<SystemUpdateAltIcon fontSize="small" />}
      label={t('header.update_available_label')}
      onClick={() => navigate('/admin?section=maintenance')}
      color="info"
      variant="outlined"
      size="small"
      sx={{ ...STATUS_CHIP_SX, mr: 1.5, cursor: 'pointer' }}
    />
  </Tooltip>
)}

{/* WebSocket status */}
<Tooltip title={isConnected ? t('websocket.connected') : t('websocket.disconnected')}>
  <Chip
    icon={isConnected ? <WifiIcon fontSize="small" /> : <WifiOffIcon fontSize="small" />}
    label={isConnected ? t('status.connected') : t('status.disconnected')}
    color={isConnected ? 'success' : 'error'}
    variant="outlined"
    size="small"
    sx={STATUS_CHIP_SX}
  />
</Tooltip>

{/* A visible search field instead of a plain icon: the palette is the global
    search (navigation, settings, media library) and used to be undiscoverable. */}
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
