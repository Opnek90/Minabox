import React, { useState, useCallback } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import BluetoothIcon from '@mui/icons-material/Bluetooth';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';

type PairedDevice = { address: string; name: string | null; connected?: boolean };
type ScanDevice = { address: string; name: string | null };

const loadPaired = async () => {
  const data = await systemApi.bluetoothPaired();
  return data.devices ?? [];
};

/** Extract API error message (Backend/Host-Helper detail) or fallback. */
function getBluetoothErrorMessage(err: unknown, fallback: string): string {
  const d = err && typeof err === 'object' && 'response' in err && (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  return typeof d === 'string' && d.length > 0 ? d : fallback;
}

export const BluetoothSection: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [pairedDevices, setPairedDevices] = useState<PairedDevice[]>([]);
  const [pairedLoading, setPairedLoading] = useState(true);
  const [scanDevices, setScanDevices] = useState<ScanDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [pairing, setPairing] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [removeConfirm, setRemoveConfirm] = useState<PairedDevice | null>(null);

  const refreshPaired = useCallback(async () => {
    setPairedLoading(true);
    try {
      const devices = await loadPaired();
      setPairedDevices(devices);
    } catch {
      setPairedDevices([]);
    } finally {
      setPairedLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refreshPaired();
  }, [refreshPaired]);

  const handleScan = async () => {
    setScanning(true);
    try {
      const data = await systemApi.bluetoothScan();
      setScanDevices(data.devices ?? []);
      const count = (data.devices ?? []).length;
      if (count > 0) {
        showSuccess(t('system.bluetooth_devices_found', { count }));
      } else {
        showSuccess(t('system.bluetooth_no_devices'));
      }
      await refreshPaired();
    } catch (e) {
      setScanDevices([]);
      showError(getBluetoothErrorMessage(e, t('system.logs_unavailable')));
    } finally {
      setScanning(false);
    }
  };

  const handlePair = async (address: string) => {
    setPairing(address);
    try {
      await systemApi.bluetoothPair(address);
      showSuccess(t('system.bluetooth_pair'));
      await refreshPaired();
    } catch (e) {
      showError(getBluetoothErrorMessage(e, t('system.logs_unavailable')));
    } finally {
      setPairing(null);
    }
  };

  const handleConnect = async (address: string) => {
    setConnecting(address);
    try {
      await systemApi.bluetoothConnect(address);
      showSuccess(t('system.bluetooth_connect'));
      await refreshPaired();
    } catch (e) {
      showError(getBluetoothErrorMessage(e, t('system.logs_unavailable')));
    } finally {
      setConnecting(null);
    }
  };

  const handleDisconnect = async (address: string) => {
    setDisconnecting(address);
    try {
      await systemApi.bluetoothDisconnect(address);
      showSuccess(t('system.bluetooth_disconnect'));
      await refreshPaired();
    } catch (e) {
      showError(getBluetoothErrorMessage(e, t('system.logs_unavailable')));
    } finally {
      setDisconnecting(null);
    }
  };

  const handleRemoveClick = (device: PairedDevice) => setRemoveConfirm(device);
  const handleRemoveConfirm = async () => {
    if (!removeConfirm) return;
    const addr = removeConfirm.address;
    setRemoveConfirm(null);
    setRemoving(addr);
    try {
      await systemApi.bluetoothRemove(addr);
      showSuccess(t('system.bluetooth_remove'));
      await refreshPaired();
    } catch (e) {
      showError(getBluetoothErrorMessage(e, t('system.logs_unavailable')));
    } finally {
      setRemoving(null);
    }
  };

  const busy = (addr: string) =>
    pairing === addr || connecting === addr || disconnecting === addr || removing === addr;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 600 }}>
        {t('system.bluetooth')}
      </Typography>

      {/* Paired devices */}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
        {t('system.bluetooth_paired')}
      </Typography>
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
          {pairedLoading ? (
            <Typography variant="body2" color="text.secondary">
              …
            </Typography>
          ) : pairedDevices.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('system.bluetooth_paired_empty')}
            </Typography>
          ) : (
            <List dense disablePadding>
              {pairedDevices.map((d) => (
                <ListItem
                  key={d.address}
                  disablePadding
                  secondaryAction={
                    <Stack direction="row" spacing={0.5} flexShrink={0}>
                      {d.connected ? (
                        <Button
                          size="small"
                          onClick={() => handleDisconnect(d.address)}
                          disabled={busy(d.address)}
                        >
                          {disconnecting === d.address
                            ? t('system.bluetooth_disconnecting')
                            : t('system.bluetooth_disconnect')}
                        </Button>
                      ) : (
                        <Button
                          size="small"
                          onClick={() => handleConnect(d.address)}
                          disabled={busy(d.address)}
                        >
                          {connecting === d.address
                            ? t('system.bluetooth_connecting')
                            : t('system.bluetooth_connect')}
                        </Button>
                      )}
                      <Button
                        size="small"
                        color="secondary"
                        onClick={() => handleRemoveClick(d)}
                        disabled={busy(d.address)}
                      >
                        {removing === d.address
                          ? t('system.bluetooth_removing')
                          : t('system.bluetooth_remove')}
                      </Button>
                    </Stack>
                  }
                >
                  <ListItemText
                    primary={d.name || d.address}
                    secondary={
                      <>
                        <Typography component="span" variant="caption" color="text.secondary">
                          {d.address}
                        </Typography>
                        {' · '}
                        <Typography
                          component="span"
                          variant="caption"
                          color={d.connected ? 'primary' : 'text.secondary'}
                        >
                          {d.connected
                            ? t('system.bluetooth_connected')
                            : t('system.bluetooth_not_connected')}
                        </Typography>
                      </>
                    }
                  />
                </ListItem>
              ))}
            </List>
          )}
        </CardContent>
      </Card>

      {/* Discover & pair */}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
        {t('system.bluetooth_discover')}
      </Typography>
      <Box display="flex" flexDirection="column" gap={1}>
        <Button
          size="small"
          variant="outlined"
          startIcon={<BluetoothIcon />}
          onClick={handleScan}
          disabled={scanning}
        >
          {scanning ? '…' : t('system.bluetooth_scan')}
        </Button>
        <Typography variant="caption" color="text.secondary">
          {t('system.bluetooth_hint')}
        </Typography>
        {scanDevices.length > 0 && (
          <Card variant="outlined">
            <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
              <List dense disablePadding>
                {scanDevices.map((d) => (
                  <ListItem
                    key={d.address}
                    disablePadding
                    secondaryAction={
                      <Button
                        size="small"
                        onClick={() => handlePair(d.address)}
                        disabled={pairing === d.address}
                      >
                        {pairing === d.address ? '…' : t('system.bluetooth_pair')}
                      </Button>
                    }
                  >
                    <ListItemText
                      primary={d.name || d.address}
                      secondary={d.address}
                    />
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        )}
      </Box>

      <Dialog open={!!removeConfirm} onClose={() => setRemoveConfirm(null)}>
        <DialogTitle>{t('system.bluetooth_remove')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('system.bluetooth_remove_confirm')}
            {removeConfirm && (
              <>
                {' '}
                <strong>{removeConfirm.name || removeConfirm.address}</strong>
              </>
            )}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoveConfirm(null)}>{t('general.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            onClick={handleRemoveConfirm}
            disabled={removing !== null}
          >
            {removing ? t('system.bluetooth_removing') : t('system.bluetooth_remove')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
