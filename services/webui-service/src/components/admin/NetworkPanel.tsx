import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import WifiIcon from '@mui/icons-material/Wifi';
import WifiOffIcon from '@mui/icons-material/WifiOff';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi, type NetworkResponse } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

/** WLAN, IP-Adresse und Gerätename – alles, was die Box im Netzwerk erreichbar macht. */
export const NetworkPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [wifiNetworks, setWifiNetworks] = useState<Array<{ ssid: string; signal: number }>>([]);
  const [wifiScanning, setWifiScanning] = useState(false);
  const [wifiConnectSsid, setWifiConnectSsid] = useState('');
  const [wifiConnectPassword, setWifiConnectPassword] = useState('');
  const [wifiConnecting, setWifiConnecting] = useState(false);
  const [hotspotStatus, setHotspotStatus] = useState<{ active: boolean; ssid: string | null }>({ active: false, ssid: null });
  const [hotspotInfo, setHotspotInfo] = useState<{ ssid: string; password: string } | null>(null);
  const [hotspotLoading, setHotspotLoading] = useState(false);
  const [network, setNetwork] = useState<NetworkResponse | null>(null);
  const [networkMethod, setNetworkMethod] = useState<'dhcp' | 'manual'>('dhcp');
  const [networkAddress, setNetworkAddress] = useState('');
  const [networkNetmask, setNetworkNetmask] = useState('24');
  const [networkGateway, setNetworkGateway] = useState('');
  const [networkDns, setNetworkDns] = useState('');
  const [networkSaving, setNetworkSaving] = useState(false);
  const [hostname, setHostname] = useState<string | null>(null);
  const [hostnameDialogOpen, setHostnameDialogOpen] = useState(false);
  const [hostnameEdit, setHostnameEdit] = useState('');
  const [hostnameSaving, setHostnameSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setError(null);
    try {
      const [hotspot, net, hostnameRes] = await Promise.all([
        systemApi.wifiHotspotStatus().catch(() => ({ active: false, ssid: null })),
        systemApi.getNetwork().catch(() => null),
        systemApi.getHostname().catch(() => null),
      ]);
      setHotspotStatus(hotspot ?? { active: false, ssid: null });
      if (net) {
        setNetwork(net);
        setNetworkMethod(net.method);
        setNetworkAddress(net.address ?? '');
        setNetworkNetmask(net.netmask ?? '24');
        setNetworkGateway(net.gateway ?? '');
        setNetworkDns(net.dns ?? '');
      } else {
        setNetwork(null);
      }
      setHostname(hostnameRes?.hostname ?? null);
    } catch {
      setError(t('load_error'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleWifiScan = async () => {
    setWifiScanning(true);
    try {
      const data = await systemApi.wifiScan();
      setWifiNetworks(data.networks ?? []);
    } catch {
      setWifiNetworks([]);
    } finally {
      setWifiScanning(false);
    }
  };

  const handleWifiConnect = async () => {
    if (!wifiConnectSsid.trim()) return;
    setWifiConnecting(true);
    try {
      await systemApi.wifiConnect(wifiConnectSsid.trim(), wifiConnectPassword);
      showSuccess(t('system.wifi_connect'));
    } catch (err: unknown) {
      const ax = err && typeof err === 'object' && 'response' in err ? (err as { response?: { data?: { detail?: string } } }).response : undefined;
      const detail = ax?.data?.detail;
      showError(typeof detail === 'string' && detail ? detail : t('system.logs_unavailable'));
    } finally {
      setWifiConnecting(false);
    }
  };

  const handleHotspotStart = async () => {
    setHotspotLoading(true);
    try {
      const data = await systemApi.wifiHotspotStart();
      setHotspotInfo({ ssid: data.ssid, password: data.password ?? '' });
      setHotspotStatus({ active: true, ssid: data.ssid });
      showSuccess(t('system.wifi_hotspot_start'));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setHotspotLoading(false);
    }
  };

  const handleHotspotStop = async () => {
    setHotspotLoading(true);
    try {
      await systemApi.wifiHotspotStop();
      setHotspotInfo(null);
      setHotspotStatus({ active: false, ssid: null });
      showSuccess(t('system.wifi_hotspot_stop'));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setHotspotLoading(false);
    }
  };

  const handleNetworkMethodChange = (method: 'dhcp' | 'manual') => {
    setNetworkMethod(method);
    if (method === 'manual' && network) {
      setNetworkAddress(network.address ?? '');
      setNetworkNetmask(network.netmask ?? '24');
      setNetworkGateway(network.gateway ?? '');
      setNetworkDns(network.dns ?? '');
    }
  };

  const handleNetworkApply = async () => {
    setNetworkSaving(true);
    try {
      await systemApi.setNetwork({
        method: networkMethod,
        address: networkMethod === 'manual' ? networkAddress.trim() || undefined : undefined,
        netmask: networkMethod === 'manual' ? networkNetmask.trim() || undefined : undefined,
        gateway: networkMethod === 'manual' ? networkGateway.trim() || undefined : undefined,
        dns: networkMethod === 'manual' ? networkDns.trim() || undefined : undefined,
      });
      const next = await systemApi.getNetwork();
      if (next) {
        setNetwork(next);
        setNetworkMethod(next.method);
        setNetworkAddress(next.address ?? '');
        setNetworkNetmask(next.netmask ?? '24');
        setNetworkGateway(next.gateway ?? '');
        setNetworkDns(next.dns ?? '');
      }
      showSuccess(t('system.network_apply'));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setNetworkSaving(false);
    }
  };

  const handleOpenHostnameDialog = () => {
    setHostnameEdit(hostname ?? '');
    setHostnameDialogOpen(true);
  };

  const handleApplyHostname = async () => {
    const name = hostnameEdit.trim().toLowerCase();
    if (!name) return;
    setHostnameSaving(true);
    try {
      await systemApi.setHostname(name);
      const res = await systemApi.getHostname();
      setHostname(res?.hostname ?? null);
      setHostnameDialogOpen(false);
      showSuccess(t('system.hostname_apply'));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setHostnameSaving(false);
    }
  };

  if (loading) return null;

  return (
    <Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── WLAN ─────────────────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.wifi')}>
        <Box display="flex" flexDirection="column" gap={1.5}>
          <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
            <ActionButton
              actionType="secondary"
              startIcon={<WifiIcon />}
              onClick={handleWifiScan}
              disabled={wifiScanning}
              loading={wifiScanning}
            >
              {t('system.wifi_scan')}
            </ActionButton>
            {hotspotStatus.active ? (
              <ActionButton
                actionType="secondary"
                startIcon={<WifiOffIcon />}
                onClick={handleHotspotStop}
                disabled={hotspotLoading}
                loading={hotspotLoading}
              >
                {t('system.wifi_hotspot_stop')}
              </ActionButton>
            ) : (
              <ActionButton
                actionType="secondary"
                startIcon={<WifiIcon />}
                onClick={handleHotspotStart}
                disabled={hotspotLoading}
                loading={hotspotLoading}
              >
                {t('system.wifi_hotspot_start')}
              </ActionButton>
            )}
          </Box>
          {hotspotInfo && (
            <Box sx={{ p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Typography variant="body2">
                SSID: <strong>{hotspotInfo.ssid}</strong> · {t('system.wifi_password')}: <strong>{hotspotInfo.password}</strong>
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('system.wifi_hotspot_connected')}
              </Typography>
            </Box>
          )}
          {wifiNetworks.length > 0 && (
            <Box>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                {t('system.wifi_ssid')}
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center">
                <TextField size="small" placeholder={t('system.wifi_ssid')} value={wifiConnectSsid} onChange={(e) => setWifiConnectSsid(e.target.value)} sx={{ minWidth: 180 }} />
                <TextField size="small" type="password" placeholder={t('system.wifi_password')} value={wifiConnectPassword} onChange={(e) => setWifiConnectPassword(e.target.value)} sx={{ minWidth: 140 }} />
                <ActionButton
                  actionType="primary"
                  onClick={handleWifiConnect}
                  disabled={wifiConnecting || !wifiConnectSsid.trim()}
                  loading={wifiConnecting}
                >
                  {t('system.wifi_connect')}
                </ActionButton>
              </Stack>
              <Box sx={{ mt: 1 }} component="ul" style={{ margin: 0, paddingLeft: 20 }}>
                {wifiNetworks.slice(0, 15).map((n) => (
                  <li key={n.ssid}>
                    <Typography variant="body2" component="span" onClick={() => setWifiConnectSsid(n.ssid)} sx={{ cursor: 'pointer', textDecoration: 'underline' }}>
                      {n.ssid}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" component="span"> ({n.signal}%)</Typography>
                  </li>
                ))}
              </Box>
            </Box>
          )}
        </Box>
      </SettingsBlock>

      {/* ── Gerätename ───────────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.host_hostname')}>
        <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
          {hostname != null && (
            <Typography variant="body2" color="text.secondary">{hostname}</Typography>
          )}
          <ActionButton
            actionType="secondary"
            onClick={handleOpenHostnameDialog}
            disabled={hostnameSaving}
          >
            {t('system.hostname_edit')}
          </ActionButton>
        </Box>
      </SettingsBlock>

      {/* ── IP-Adresse ───────────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.network_title')}>
        {network === null ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{t('system.network_no_connection')}</Typography>
        ) : (
          <Box display="flex" flexDirection="column" gap={1.5} sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">{t('system.network_method_label')}</Typography>
            <RadioGroup row value={networkMethod} onChange={(_, v) => handleNetworkMethodChange(v as 'dhcp' | 'manual')}>
              <FormControlLabel value="dhcp" control={<Radio size="small" />} label={t('system.network_method_dhcp')} />
              <FormControlLabel value="manual" control={<Radio size="small" />} label={t('system.network_method_manual')} />
            </RadioGroup>
            {networkMethod === 'manual' && (
              <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center" sx={{ mt: 0.5 }}>
                <TextField size="small" label={t('system.network_address')} value={networkAddress} onChange={(e) => setNetworkAddress(e.target.value)} placeholder="192.168.1.10" sx={{ minWidth: 140 }} />
                <TextField size="small" label={t('system.network_netmask')} value={networkNetmask} onChange={(e) => setNetworkNetmask(e.target.value)} placeholder="24" sx={{ width: 72 }} />
                <TextField size="small" label={t('system.network_gateway')} value={networkGateway} onChange={(e) => setNetworkGateway(e.target.value)} placeholder="192.168.1.1" sx={{ minWidth: 120 }} />
                <TextField size="small" label={t('system.network_dns')} value={networkDns} onChange={(e) => setNetworkDns(e.target.value)} placeholder="192.168.1.1" sx={{ minWidth: 120 }} />
              </Stack>
            )}
            <Box display="flex" flexWrap="wrap" gap={1}>
              <ActionButton
                actionType="primary"
                startIcon={<SaveIcon />}
                onClick={handleNetworkApply}
                disabled={networkSaving}
                loading={networkSaving}
              >
                {t('system.network_apply')}
              </ActionButton>
            </Box>
          </Box>
        )}
      </SettingsBlock>

      <Dialog open={hostnameDialogOpen} onClose={() => setHostnameDialogOpen(false)}>
        <DialogTitle>{t('system.hostname_dialog_title')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 1 }}>{t('system.hostname_reconnect_hint')}</DialogContentText>
          <TextField autoFocus fullWidth margin="dense" label={t('system.host_hostname')} value={hostnameEdit} onChange={(e) => setHostnameEdit(e.target.value)} placeholder="minabox" inputProps={{ maxLength: 63 }} />
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setHostnameDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="primary"
            onClick={handleApplyHostname}
            disabled={hostnameSaving || !hostnameEdit.trim()}
          >
            {t('system.hostname_apply')}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
