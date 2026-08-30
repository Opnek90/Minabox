import React from 'react';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { NetworkStatusResponse } from '@/api/system';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

interface NetworkStatusBlockProps {
  status: NetworkStatusResponse | null;
}

/**
 * Wie die Box gerade im Netz steht - und unter welcher Adresse sie erreichbar
 * ist, falls sie im Hotspot haengt.
 *
 * Bekommt den Zustand vom Panel gereicht statt ihn selbst zu holen: der
 * WLAN-Block darunter kann ihn aendern, und dann muss diese Karte mitziehen.
 */
export const NetworkStatusBlock: React.FC<NetworkStatusBlockProps> = ({ status }) => {
  const { t } = useTranslation('admin');

  if (!status) return null;

  const modeLabel = t(`system.net_status_${status.mode}`, {
    defaultValue: t('system.net_status_unknown'),
  });
  const severity: 'success' | 'info' | 'warning' =
    status.mode === 'online' ? 'success' : status.mode === 'no_network' ? 'warning' : 'info';

  return (
    <SettingsBlock title={t('system.net_status_title')}>
      <Stack spacing={1} sx={{ mt: 0.5 }}>
        <Alert severity={severity} sx={{ py: 0.25 }}>
          {modeLabel}
          {status.stale && ` — ${t('system.net_status_stale')}`}
        </Alert>

        {status.manage_url && (
          <Typography variant="body2">
            {t('system.net_status_reach')}:{' '}
            <Box component="span" sx={{ fontFamily: 'monospace' }}>{status.manage_url}</Box>
          </Typography>
        )}

        {status.hotspot.active && status.hotspot.ssid && (
          <Typography variant="body2">
            {t('system.net_status_ssid')}: <strong>{status.hotspot.ssid}</strong>
            {status.hotspot.password && (
              <> · {t('system.wifi_password')}: <strong>{status.hotspot.password}</strong></>
            )}
          </Typography>
        )}

        {!status.hotspot.active && status.ssid && (
          <Typography variant="body2">
            {t('system.net_status_ssid')}: <strong>{status.ssid}</strong>
          </Typography>
        )}

        <Typography variant="caption" color="text.secondary">
          {t('system.net_status_fallback_hint', {
            ssid: status.hotspot.ssid || 'Minabox-Setup',
          })}
        </Typography>
      </Stack>
    </SettingsBlock>
  );
};
