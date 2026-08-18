import React, { useState } from 'react';
import { Box, Checkbox, Chip, FormControlLabel, Typography } from '@mui/material';
import UsbIcon from '@mui/icons-material/Usb';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';

/** Musik von einem USB-Stick auf die Box kopieren. */
export const UsbImportPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [devices, setDevices] = useState<Array<{ id: string; device: string; size: string; mountpoint: string | null; label: string | null }>>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [entries, setEntries] = useState<Array<{ path: string; name: string; type: string }>>([]);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);

  const handleLoadDevices = async () => {
    setLoading(true);
    try {
      const data = await systemApi.usbDevices();
      setDevices(data.devices ?? []);
      setSelectedId(null);
      setEntries([]);
      setSelectedPaths([]);
    } catch {
      setDevices([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectDevice = async (id: string) => {
    setSelectedId(id);
    setEntries([]);
    setSelectedPaths([]);
    try {
      const data = await systemApi.usbFiles(id);
      setEntries(data.entries ?? []);
    } catch {
      setEntries([]);
    }
  };

  const handleImport = async () => {
    if (!selectedId || selectedPaths.length === 0) return;
    setImporting(true);
    try {
      const data = await systemApi.usbImport(selectedId, selectedPaths);
      showSuccess(t('system.usb_import_success', { count: data.files_copied ?? 0 }));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setImporting(false);
    }
  };

  const handleEject = async () => {
    if (!selectedId) return;
    try {
      await systemApi.usbEject(selectedId);
      showSuccess(t('system.usb_eject'));
      handleLoadDevices();
    } catch {
      showError(t('system.logs_unavailable'));
    }
  };

  return (
    <Box display="flex" flexDirection="column" gap={1.5}>
      <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
        <ActionButton
          actionType="secondary"
          startIcon={<UsbIcon />}
          onClick={handleLoadDevices}
          disabled={loading}
          loading={loading}
        >
          {t('system.usb_devices')}
        </ActionButton>
      </Box>
      {devices.length > 0 && (
        <>
          <Box display="flex" flexWrap="wrap" gap={1}>
            {devices.map((d) => (
              <Chip
                key={d.id}
                label={`${d.id} ${d.size} ${d.label || ''}`.trim()}
                onClick={() => handleSelectDevice(d.id)}
                color={selectedId === d.id ? 'primary' : 'default'}
                variant={selectedId === d.id ? 'filled' : 'outlined'}
              />
            ))}
          </Box>
          {selectedId && (
            <>
              <Typography variant="caption" color="text.secondary">{t('system.usb_files')}</Typography>
              <Box display="flex" flexWrap="wrap" gap={0.5}>
                {entries.map((e) => (
                  <FormControlLabel
                    key={e.path}
                    control={
                      <Checkbox
                        size="small"
                        checked={selectedPaths.includes(e.path)}
                        onChange={(_, checked) =>
                          setSelectedPaths((prev) =>
                            checked ? [...prev, e.path] : prev.filter((p) => p !== e.path)
                          )
                        }
                      />
                    }
                    label={e.name + (e.type === 'dir' ? ` (${t('system.usb_folder')})` : '')}
                  />
                ))}
              </Box>
              <Box display="flex" gap={1}>
                <ActionButton actionType="primary" onClick={handleImport} disabled={importing || selectedPaths.length === 0} loading={importing}>
                  {t('system.usb_import')}
                </ActionButton>
                <ActionButton actionType="secondary" onClick={handleEject}>
                  {t('system.usb_eject')}
                </ActionButton>
              </Box>
            </>
          )}
        </>
      )}
    </Box>
  );
};
