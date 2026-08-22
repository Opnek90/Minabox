import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Typography } from '@mui/material';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/WebSocketContext';
import { systemApi, type SystemAlert } from '@/api/system';

export const SystemAlertBar: React.FC = () => {
  const { t } = useTranslation('common');
  const { lastMessage } = useWebSocket();
  const [alert, setAlert] = useState<SystemAlert | null>(null);

  const applyAlert = useCallback((a: SystemAlert | null) => {
    setAlert(a);
  }, []);

  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === 'system_alert' && lastMessage.data) {
      const d = lastMessage.data as { level?: string; code?: string; message?: string };
      applyAlert({
        code: d.code ?? 'unknown',
        level: (d.level as 'warning' | 'info' | 'error') ?? 'info',
        message: d.message ?? '',
      });
    } else if (lastMessage.type === 'system_alert_cleared' && lastMessage.data) {
      const d = lastMessage.data as { code?: string };
      setAlert((prev) => (prev && prev.code === d.code ? null : prev));
    }
  }, [lastMessage, applyAlert]);

  useEffect(() => {
    systemApi.getCurrentAlert().then((res) => {
      if (res.alert) applyAlert(res.alert);
    }).catch(() => {});
  }, [applyAlert]);

  if (!alert) return null;

  const severity = alert.level === 'error' ? 'error' : alert.level === 'warning' ? 'warning' : 'info';
  const icon = alert.level === 'error' ? <ErrorOutlineIcon fontSize="small" /> : alert.level === 'warning' ? <WarningAmberIcon fontSize="small" /> : <InfoOutlinedIcon fontSize="small" />;
  // alert.message kommt vom Backend per WebSocket - "alerts.xxx" ist per
  // Konvention ein i18n-Key, alles andere ein fertiger Text. Kein Weg, das
  // statisch gegen die JSON-Keys zu pruefen.
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
