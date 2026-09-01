import React from 'react';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { NetworkStatusResponse } from '@/api/system';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

interface NetworkStatusBlockProps {
  status: NetworkStatusResponse | null;
}

/**
 * How the box currently stands on the network - and which address it is
 * reachable at if it is in hotspot mode.
 *
 * Gets the state passed from the panel instead of fetching it itself: the
 * Wi-Fi block below can change it, and then this card has to follow.
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
    <SettingsBlock
      title={t('system.net_status_title')}
      help={t('system.net_status_fallback_hint', {
        ssid: status.hotspot.ssid || 'Minabox-Setup',
      })}
    >
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
      </Stack>
    </SettingsBlock>
  );
};
