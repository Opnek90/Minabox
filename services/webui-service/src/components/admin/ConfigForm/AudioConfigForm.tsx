import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Divider,
  FormControlLabel,
  List,
  ListItemButton,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { audioApi } from '@/api/audio';
import { configApi } from '@/api/config';
import type { AudioConfig, AudioDeviceItem } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';

function getDeviceKey(device: AudioDeviceItem): string {
  return device.sink_name ?? device.alsa_device ?? device.id;
}

function isDeviceEnabled(device: AudioDeviceItem, enabledList: string[] | undefined): boolean {
  const list = enabledList ?? [];
  if (list.length === 0) return true;
  return list.includes(getDeviceKey(device));
}

export const AudioConfigForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [config, setConfig] = useState<AudioConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [devices, setDevices] = useState<AudioDeviceItem[]>([]);
  const [devicesLoading, setDevicesLoading] = useState(false);

  useEffect(() => {
    configApi
      .getAudio()
      .then(setConfig)
      .catch(() => setError(t('load_error', { defaultValue: 'Laden fehlgeschlagen' })))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!config) return;
    setDevicesLoading(true);
    audioApi
      .getDevices(false)
      .then((r) => setDevices(r.devices ?? []))
      .catch(() => setDevices([]))
      .finally(() => setDevicesLoading(false));
  }, [config]);

  const handleRefreshDevices = () => {
    setDevicesLoading(true);
    audioApi
      .getDevices(false)
      .then((r) => setDevices(r.devices ?? []))
      .catch(() => setDevices([]))
      .finally(() => setDevicesLoading(false));
  };

  const handleDeviceEnabledChange = (device: AudioDeviceItem, enabled: boolean) => {
    if (!config) return;
    const deviceKey = getDeviceKey(device);
    const list = config.enabled_output_devices ?? [];
    if (enabled) {
      setConfig({
        ...config,
        enabled_output_devices: list.includes(deviceKey) ? list : [...list, deviceKey],
      });
    } else {
      if (list.length === 0) {
        setConfig({
          ...config,
          enabled_output_devices: devices.filter((d) => getDeviceKey(d) !== deviceKey).map(getDeviceKey),
        });
      } else {
        setConfig({
          ...config,
          enabled_output_devices: list.filter((name) => name !== deviceKey),
        });
      }
    }
  };

  const handleSave = () =>
    run(async () => {
      if (!config) return;
      const updated = await configApi.updateAudio(config);
      setConfig(updated);
      showSuccess(t('audio.save_success'));
    });

  if (loading || !config) return null;

  return (
    <Box display="flex" flexDirection="column" maxWidth={560} sx={{ gap: { xs: 2, sm: 3 } }}>
      <TextField
        label={t('audio.output_device_type')}
        value={config.output_device_type}
        onChange={(e) => setConfig((p) => (p ? { ...p, output_device_type: e.target.value } : p))}
        size="small"
        fullWidth
      />
      <TextField
        label={t('audio.output_device_name')}
        placeholder={t('audio.output_device_name_placeholder')}
        value={config.output_device_name}
        onChange={(e) => setConfig((p) => (p ? { ...p, output_device_name: e.target.value } : p))}
        size="small"
        fullWidth
      />
      <Divider sx={{ my: 1 }} />
      <Typography variant="overline" color="text.secondary">
        {t('audio.output_devices_section')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
        {t('audio.output_devices_bluetooth_hint')}
      </Typography>
      <ActionButton
        actionType="secondary"
        size="small"
        onClick={handleRefreshDevices}
        disabled={devicesLoading}
      >
        {devicesLoading ? '...' : t('audio.output_devices_refresh')}
      </ActionButton>
      {devices.length === 0 && !devicesLoading ? (
        <Typography variant="body2" color="text.secondary">
          {t('audio.output_devices_empty')}
        </Typography>
      ) : (
        <List dense sx={{ bgcolor: 'action.hover', borderRadius: 1 }}>
          {devices.map((d) => {
            const deviceKey = getDeviceKey(d);
            const enabled = isDeviceEnabled(d, config.enabled_output_devices);
            const isCurrent = config.output_device_name === deviceKey;
            const displayNames = config.device_display_names ?? {};
            const displayName = displayNames[deviceKey] ?? '';
            return (
              <ListItemButton
                key={deviceKey}
                dense
                sx={{ display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 0.5 }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <FormControlLabel
                    control={
                      <Switch
                        size="small"
                        checked={enabled}
                        onChange={(_, checked) => handleDeviceEnabledChange(d, checked)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    }
                    label=""
                  />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" noWrap title={d.name}>
                      {d.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" noWrap title={deviceKey}>
                      {d.card_name || deviceKey}
                      {isCurrent && ' · ' + t('audio.output_devices_current')}
                    </Typography>
                  </Box>
                </Box>
                <TextField
                  size="small"
                  placeholder={t('audio.device_display_name_placeholder')}
                  value={displayName}
                  onChange={(e) => {
                    const next = { ...displayNames };
                    const v = e.target.value.trim();
                    if (v) next[deviceKey] = v;
                    else delete next[deviceKey];
                    setConfig((p) => (p ? { ...p, device_display_names: next } : p));
                  }}
                  onClick={(e) => e.stopPropagation()}
                  sx={{ ml: 4, maxWidth: 280 }}
                />
              </ListItemButton>
            );
          })}
        </List>
      )}
      {config.resume_on_startup !== undefined && (
        <FormControlLabel
          control={
            <Switch
              checked={config.resume_on_startup}
              onChange={(e) =>
                setConfig((p) => (p ? { ...p, resume_on_startup: e.target.checked } : p))
              }
            />
          }
          label={t('audio.resume_on_startup')}
        />
      )}
      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton actionType="primary" onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
