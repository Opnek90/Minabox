import React, { useState } from 'react';
import { Box, Button, Stack, Typography } from '@mui/material';
import BluetoothIcon from '@mui/icons-material/Bluetooth';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';

export const BluetoothSection: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [bluetoothDevices, setBluetoothDevices] = useState<Array<{ address: string; name: string | null }>>([]);
  const [bluetoothScanning, setBluetoothScanning] = useState(false);
  const [bluetoothPairing, setBluetoothPairing] = useState<string | null>(null);

  const handleBluetoothScan = async () => {
    setBluetoothScanning(true);
    try {
      const data = await systemApi.bluetoothScan();
      setBluetoothDevices(data.devices ?? []);
    } catch {
      setBluetoothDevices([]);
    } finally {
      setBluetoothScanning(false);
    }
  };

  const handleBluetoothPair = async (address: string) => {
    setBluetoothPairing(address);
    try {
      await systemApi.bluetoothPair(address);
      showSuccess(t('system.bluetooth_pair'));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setBluetoothPairing(null);
    }
  };

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 600 }}>
        {t('system.bluetooth')}
      </Typography>
      <Box display="flex" flexDirection="column" gap={1}>
        <Button
          size="small"
          variant="outlined"
          startIcon={<BluetoothIcon />}
          onClick={handleBluetoothScan}
          disabled={bluetoothScanning}
        >
          {t('system.bluetooth_scan')}
        </Button>
        <Typography variant="caption" color="text.secondary">
          {t('system.bluetooth_hint')}
        </Typography>
        {bluetoothDevices.length > 0 && (
          <Stack direction="row" flexWrap="wrap" gap={1}>
            {bluetoothDevices.map((d) => (
              <Box key={d.address} display="flex" alignItems="center" gap={0.5}>
                <Typography variant="body2">{d.name || d.address}</Typography>
                <Button
                  size="small"
                  onClick={() => handleBluetoothPair(d.address)}
                  disabled={bluetoothPairing === d.address}
                >
                  {t('system.bluetooth_pair')}
                </Button>
              </Box>
            ))}
          </Stack>
        )}
      </Box>
    </Box>
  );
};
