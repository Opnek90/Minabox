import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import UsbIcon from '@mui/icons-material/Usb';
import WifiIcon from '@mui/icons-material/Wifi';
import WifiOffIcon from '@mui/icons-material/WifiOff';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import {
  systemApi,
  type BoardLedsResponse,
  type NetworkResponse,
} from '@/api/system';
import { SystemMaintenanceSection } from '@/components/admin/SystemMaintenanceSection';
import { ActionButton } from '@/components/ui/ActionButton';

export const SystemPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [boardLeds, setBoardLeds] = useState<BoardLedsResponse | null>(null);
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
  const [usbDevices, setUsbDevices] = useState<Array<{ id: string; device: string; size: string; mountpoint: string | null; label: string | null }>>([]);
  const [usbSelectedId, setUsbSelectedId] = useState<string | null>(null);
  const [usbEntries, setUsbEntries] = useState<Array<{ path: string; name: string; type: string }>>([]);
  const [usbSelectedPaths, setUsbSelectedPaths] = useState<string[]>([]);
  const [usbLoading, setUsbLoading] = useState(false);
  const [usbImporting, setUsbImporting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setError(null);
    try {
      const [leds, hotspot, net, hostnameRes] = await Promise.all([
        systemApi.getBoardLeds().catch(() => null),
        systemApi.wifiHotspotStatus().catch(() => ({ active: false, ssid: null })),
        systemApi.getNetwork().catch(() => null),
        systemApi.getHostname().catch(() => null),
      ]);
      setBoardLeds(leds ?? null);
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
      setError('Daten konnten nicht geladen werden');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleStealthChange = async (on: boolean) => {
    try {
      await systemApi.setBoardLeds(on);
      const next = await systemApi.getBoardLeds();
      setBoardLeds(next);
    } catch {
      showError(t('system.logs_unavailable'));
    }
  };

  const handleWifiScan = async () => {
    fetch('http://localhost:7862/ingest/6a49f368-9891-40e8-b9a5-b23b7884dd09', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '0f3d51' }, body: JSON.stringify({ sessionId: '0f3d51', location: 'SystemPanel.tsx:handleWifiScan', message: 'handleWifiScan called', data: {}, timestamp: Date.now(), hypothesisId: 'H3' }) }).catch(() => {});
    setWifiScanning(true);
    try {
      const data = await systemApi.wifiScan();
      fetch('http://localhost:7862/ingest/6a49f368-9891-40e8-b9a5-b23b7884dd09', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '0f3d51' }, body: JSON.stringify({ sessionId: '0f3d51', location: 'SystemPanel.tsx:handleWifiScan', message: 'wifiScan response', data: { networksLength: data?.networks?.length ?? -1 }, timestamp: Date.now(), hypothesisId: 'H4,H5' }) }).catch(() => {});
      setWifiNetworks(data.networks ?? []);
    } catch (err) {
      fetch('http://localhost:7862/ingest/6a49f368-9891-40e8-b9a5-b23b7884dd09', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '0f3d51' }, body: JSON.stringify({ sessionId: '0f3d51', location: 'SystemPanel.tsx:handleWifiScan', message: 'wifiScan error', data: { err: String(err) }, timestamp: Date.now(), hypothesisId: 'H4' }) }).catch(() => {});
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
      const ax = err && typeof err === 'object' && 'response' in err ? (err as { response?: { status?: number; data?: { detail?: string } } }).response : undefined;
      fetch('http://localhost:7587/ingest/956f1dfb-30a2-4644-a364-2be2e1ac338d', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '771350' }, body: JSON.stringify({ sessionId: '771350', location: 'SystemPanel.tsx:handleWifiConnect', message: 'wifiConnect error', data: { status: ax?.status, detail: ax?.data?.detail }, timestamp: Date.now(), hypothesisId: 'H2,H3,H5' }) }).catch(() => {});
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

  const handleUsbLoadDevices = async () => {
    setUsbLoading(true);
    try {
      const data = await systemApi.usbDevices();
      setUsbDevices(data.devices ?? []);
      setUsbSelectedId(null);
      setUsbEntries([]);
      setUsbSelectedPaths([]);
    } catch {
      setUsbDevices([]);
    } finally {
      setUsbLoading(false);
    }
  };

  const handleUsbSelectDevice = async (id: string) => {
    setUsbSelectedId(id);
    setUsbEntries([]);
    setUsbSelectedPaths([]);
    try {
      const data = await systemApi.usbFiles(id);
      setUsbEntries(data.entries ?? []);
    } catch {
      setUsbEntries([]);
    }
  };

  const handleUsbImport = async () => {
    if (!usbSelectedId || usbSelectedPaths.length === 0) return;
    setUsbImporting(true);
    try {
      const data = await systemApi.usbImport(usbSelectedId, usbSelectedPaths);
      showSuccess(t('system.usb_import_success', { count: data.files_copied ?? 0 }));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setUsbImporting(false);
    }
  };

  const handleUsbEject = async () => {
    if (!usbSelectedId) return;
    try {
      await systemApi.usbEject(usbSelectedId);
      showSuccess(t('system.usb_eject'));
      handleUsbLoadDevices();
    } catch {
      showError(t('system.logs_unavailable'));
    }
  };

  if (loading) return null;

  return (
    <Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Hardware ────────────────────────────────────────────────────────── */}
      {boardLeds != null && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 600 }}>
            {t('system.hardware_title')}
          </Typography>
          <FormControlLabel
            control={<Switch checked={boardLeds.stealth} onChange={(_, checked) => handleStealthChange(checked)} color="primary" />}
            label={t('system.stealth_mode')}
          />
          <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 0.5 }}>
            {t('system.stealth_hint')}
          </Typography>
        </Box>
      )}

      {/* ── WLAN ─────────────────────────────────────────────────────────────── */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 600 }}>
          {t('system.wifi')}
        </Typography>
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
                SSID: <strong>{hotspotInfo.ssid}</strong> · Passwort: <strong>{hotspotInfo.password}</strong>
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
      </Box>

      {/* ── Netzwerk (IP) ────────────────────────────────────────────────────── */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 600 }}>
          {t('system.network_title')}
        </Typography>
        {network === null && !loading ? (
          <Typography variant="body2" color="text.secondary">{t('system.network_no_connection')}</Typography>
        ) : (
          <Box display="flex" flexDirection="column" gap={1.5}>
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
                disabled={networkSaving || network === null}
                loading={networkSaving}
              >
                {t('system.network_apply')}
              </ActionButton>
            </Box>
          </Box>
        )}
      </Box>

      {/* ── Hostname ─────────────────────────────────────────────────────────── */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 600 }}>
          {t('system.host_hostname')}
        </Typography>
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
      </Box>

      {/* ── USB Import ───────────────────────────────────────────────────────── */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 600 }}>
          {t('system.usb')}
        </Typography>
        <Box display="flex" flexDirection="column" gap={1.5}>
          <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
            <ActionButton
              actionType="secondary"
              startIcon={<UsbIcon />}
              onClick={handleUsbLoadDevices}
              disabled={usbLoading}
              loading={usbLoading}
            >
              {t('system.usb_devices')}
            </ActionButton>
          </Box>
          {usbDevices.length > 0 && (
            <>
              <Box display="flex" flexWrap="wrap" gap={1}>
                {usbDevices.map((d) => (
                  <Chip key={d.id} label={`${d.id} ${d.size} ${d.label || ''}`.trim()} onClick={() => handleUsbSelectDevice(d.id)} color={usbSelectedId === d.id ? 'primary' : 'default'} variant={usbSelectedId === d.id ? 'filled' : 'outlined'} />
                ))}
              </Box>
              {usbSelectedId && (
                <>
                  <Typography variant="caption" color="text.secondary">{t('system.usb_files')}</Typography>
                  <Box display="flex" flexWrap="wrap" gap={0.5}>
                    {usbEntries.map((e) => (
                      <FormControlLabel
                        key={e.path}
                        control={
                          <Checkbox size="small" checked={usbSelectedPaths.includes(e.path)} onChange={(_, checked) => setUsbSelectedPaths((prev) => checked ? [...prev, e.path] : prev.filter((p) => p !== e.path))} />
                        }
                        label={e.name + (e.type === 'dir' ? ' (Ordner)' : '')}
                      />
                    ))}
                  </Box>
                  <Box display="flex" gap={1}>
                    <ActionButton actionType="primary" onClick={handleUsbImport} disabled={usbImporting || usbSelectedPaths.length === 0} loading={usbImporting}>
                      {t('system.usb_import')}
                    </ActionButton>
                    <ActionButton actionType="secondary" onClick={handleUsbEject}>
                      {t('system.usb_eject')}
                    </ActionButton>
                  </Box>
                </>
              )}
            </>
          )}
        </Box>
      </Box>

      <SystemMaintenanceSection />

      {/* ── Hostname Dialog ─────────────────────────────────────────────────── */}
      <Dialog open={hostnameDialogOpen} onClose={() => setHostnameDialogOpen(false)}>
        <DialogTitle>{t('system.hostname_dialog_title')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 1 }}>{t('system.hostname_reconnect_hint')}</DialogContentText>
          <TextField autoFocus fullWidth margin="dense" label={t('system.host_hostname')} value={hostnameEdit} onChange={(e) => setHostnameEdit(e.target.value)} placeholder="minabox" inputProps={{ maxLength: 63 }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHostnameDialogOpen(false)}>{t('actions.cancel', { ns: 'common' })}</Button>
          <Button onClick={handleApplyHostname} color="primary" variant="contained" disabled={hostnameSaving || !hostnameEdit.trim()}>
            {t('system.hostname_apply')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
