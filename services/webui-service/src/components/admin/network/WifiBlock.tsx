import React, { useCallback, useEffect, useState } from 'react';
import { Box, Stack, TextField, Typography } from '@mui/material';
import WifiIcon from '@mui/icons-material/Wifi';
import WifiOffIcon from '@mui/icons-material/WifiOff';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';

/** List at most this many found networks - the rest is noise. */
const MAX_NETWORKS = 15;

interface WifiBlockProps {
  /** After every change, so the status card above follows. */
  onNetworkChanged: () => void;
}

/** Scan and connect to Wi-Fi, start and stop the hotspot. */
export const WifiBlock: React.FC<WifiBlockProps> = ({ onNetworkChanged }) => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();

  const [networks, setNetworks] = useState<Array<{ ssid: string; signal: number }>>([]);
  const [scanning, setScanning] = useState(false);
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [hotspotActive, setHotspotActive] = useState(false);
  const [hotspotInfo, setHotspotInfo] = useState<{ ssid: string; password: string } | null>(null);
  const [hotspotLoading, setHotspotLoading] = useState(false);

  const loadHotspot = useCallback(async () => {
    try {
      const status = await systemApi.wifiHotspotStatus();
      setHotspotActive(status?.active ?? false);
    } catch {
      setHotspotActive(false);
    }
  }, []);

  useEffect(() => {
    void loadHotspot();
  }, [loadHotspot]);

  const handleScan = async () => {
    setScanning(true);
    try {
      const data = await systemApi.wifiScan();
      setNetworks(data.networks ?? []);
    } catch {
      setNetworks([]);
    } finally {
      setScanning(false);
    }
  };

  const handleConnect = async () => {
    if (!ssid.trim()) return;
    setConnecting(true);
    try {
      await systemApi.wifiConnect(ssid.trim(), password);
      showSuccess(t('system.wifi_connect'));
      onNetworkChanged();
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setConnecting(false);
    }
  };

  const handleHotspotStart = async () => {
    setHotspotLoading(true);
    try {
      const data = await systemApi.wifiHotspotStart();
      setHotspotInfo({ ssid: data.ssid, password: data.password ?? '' });
      setHotspotActive(true);
      showSuccess(t('system.wifi_hotspot_start'));
      onNetworkChanged();
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setHotspotLoading(false);
    }
  };

  const handleHotspotStop = async () => {
    setHotspotLoading(true);
    try {
      await systemApi.wifiHotspotStop();
      setHotspotInfo(null);
      setHotspotActive(false);
      showSuccess(t('system.wifi_hotspot_stop'));
      onNetworkChanged();
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setHotspotLoading(false);
    }
  };

  return (
    <SettingsBlock title={t('system.wifi')}>
      <Box display="flex" flexDirection="column" gap={1.5}>
        <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
          <ActionButton
            actionType="secondary"
            startIcon={<WifiIcon />}
            onClick={handleScan}
            disabled={scanning}
            loading={scanning}
          >
            {t('system.wifi_scan')}
          </ActionButton>
          <ActionButton
            actionType="secondary"
            startIcon={hotspotActive ? <WifiOffIcon /> : <WifiIcon />}
            onClick={hotspotActive ? handleHotspotStop : handleHotspotStart}
            disabled={hotspotLoading}
            loading={hotspotLoading}
          >
            {hotspotActive ? t('system.wifi_hotspot_stop') : t('system.wifi_hotspot_start')}
          </ActionButton>
        </Box>

        {hotspotInfo && (
          <Box sx={{ p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
            <Typography variant="body2">
              SSID: <strong>{hotspotInfo.ssid}</strong> · {t('system.wifi_password')}:{' '}
              <strong>{hotspotInfo.password}</strong>
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('system.wifi_hotspot_connected')}
            </Typography>
          </Box>
        )}

        {networks.length > 0 && (
          <Box>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
              {t('system.wifi_ssid')}
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center">
              <TextField
                size="small"
                placeholder={t('system.wifi_ssid')}
                value={ssid}
                onChange={(e) => setSsid(e.target.value)}
                sx={{ minWidth: 180 }}
              />
              <TextField
                size="small"
                type="password"
                placeholder={t('system.wifi_password')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                sx={{ minWidth: 140 }}
              />
              <ActionButton
                actionType="primary"
                onClick={handleConnect}
                disabled={connecting || !ssid.trim()}
                loading={connecting}
              >
                {t('system.wifi_connect')}
              </ActionButton>
            </Stack>
            <Box sx={{ mt: 1 }} component="ul" style={{ margin: 0, paddingLeft: 20 }}>
              {networks.slice(0, MAX_NETWORKS).map((n) => (
                <li key={n.ssid}>
                  <Typography
                    variant="body2"
                    component="span"
                    onClick={() => setSsid(n.ssid)}
                    sx={{ cursor: 'pointer', textDecoration: 'underline' }}
                  >
                    {n.ssid}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" component="span">
                    {' '}({n.signal}%)
                  </Typography>
                </li>
              ))}
            </Box>
          </Box>
        )}
      </Box>
    </SettingsBlock>
  );
};
