import React from 'react';
import { Alert, Box, Typography } from '@mui/material';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import { useTranslation } from 'react-i18next';
import { ALERT_UPDATE_AVAILABLE, useSystemAlerts } from '@/hooks/useSystemAlerts';

export const SystemAlertBar: React.FC = () => {
  const { t } = useTranslation('common');
  // The update hint shows as an icon in the header (Header.tsx) - here only
  // what else is pending (e.g. over-temperature), most severe first.
  const alert = useSystemAlerts().find((a) => a.code !== ALERT_UPDATE_AVAILABLE) ?? null;

  if (!alert) return null;

  const severity = alert.level === 'error' ? 'error' : alert.level === 'warning' ? 'warning' : 'info';
  const icon = alert.level === 'error' ? <ErrorOutlineIcon fontSize="small" /> : alert.level === 'warning' ? <WarningAmberIcon fontSize="small" /> : <InfoOutlinedIcon fontSize="small" />;
  // alert.message comes from the backend over WebSocket - "alerts.xxx" is by
  // convention an i18n key, anything else a finished string. No way to check
  // that statically against the JSON keys.
  const text = alert.message
    ? (alert.message.startsWith('alerts.') ? t(alert.message as never) : alert.message)
    : t('alerts.temperature_high');

  return (
    <Box
      sx={{
        width: '100%',
        flexShrink: 0,
        zIndex: (theme) => theme.zIndex.appBar + 2,
      }}
    >
      <Alert
        severity={severity}
        icon={icon}
        sx={{
          borderRadius: 0,
          py: 0.5,
          '& .MuiAlert-message': { width: '100%' },
        }}
      >
        <Typography variant="body2" component="span">
          {text || alert.code}
        </Typography>
      </Alert>
    </Box>
  );
};
