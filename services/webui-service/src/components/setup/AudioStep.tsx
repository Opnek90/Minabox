import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  MenuItem,
  Slider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { configApi } from '@/api/config';
import type { AudioDeviceItem } from '@/types/api';

interface Props {
  registerSave: (fn: () => Promise<boolean>) => void;
}

type ToneState = 'idle' | 'playing' | 'asked' | 'failed';

export const AudioStep: React.FC<Props> = ({ registerSave }) => {
  const { t } = useTranslation('setup');
  const [devices, setDevices] = useState<AudioDeviceItem[]>([]);
  const [sink, setSink] = useState('');
  const [tone, setTone] = useState<ToneState>('idle');
  const [heardNo, setHeardNo] = useState(false);
  const [loading, setLoading] = useState(true);

  const [minVol, setMinVol] = useState(15);
  const [defVol, setDefVol] = useState(25);
  const [maxVol, setMaxVol] = useState(35);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([audioApi.getDevices(), configApi.getAudio()])
      .then(([dev, cfg]) => {
        setDevices(dev.devices ?? []);
        // Vorauswahl: der bereits konfigurierte Ausgang, sonst der erste.
        setSink(cfg.output_device_name || dev.devices?.[0]?.id || '');
        setMinVol(cfg.min_volume ?? 15);
        setDefVol(cfg.default_volume ?? 25);
        setMaxVol(cfg.max_volume ?? 35);
      })
      .catch(() => setDevices([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    registerSave(async () => {
      if (!(minVol <= defVol && defVol <= maxVol)) {
        setError(t('audio.volume_order'));
        return false;
      }
      try {
        if (sink) {
          await audioApi.switchDevice(sink);
          await configApi.updateAudio({
            output_device_name: sink,
            min_volume: minVol,
            default_volume: defVol,
            max_volume: maxVol,
          });
        } else {
          await configApi.updateAudio({
            min_volume: minVol,
            default_volume: defVol,
            max_volume: maxVol,
          });
        }
        setError(null);
        return true;
      } catch {
        setError(t('audio_config_write_failed', { ns: 'errors' }));
        return false;
      }
    });
  }, [sink, minVol, defVol, maxVol, registerSave, t]);

  const playTone = useCallback(async () => {
    setTone('playing');
    setHeardNo(false);
    try {
      // Der Ausgang muss vor dem Ton aktiv sein, sonst pruefte der Test den
      // bisherigen Ausgang und nicht den gerade gewaehlten.
      if (sink) await audioApi.switchDevice(sink);
      await audioApi.playTestTone(sink || undefined);
      setTone('asked');
    } catch {
      setTone('failed');
    }
  }, [sink]);

  if (loading) return <CircularProgress size={24} />;

  return (
    <Stack spacing={2}>
      <Typography variant="h6">{t('audio.heading')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('audio.intro')}
      </Typography>

      {devices.length === 0 ? (
        <Alert severity="warning">{t('audio.no_devices')}</Alert>
      ) : (
        <TextField
          select
          label={t('audio.device')}
          value={sink}
          onChange={(e) => {
            setSink(e.target.value);
            setTone('idle');
          }}
          size="small"
          fullWidth
        >
          {devices.map((d) => (
            <MenuItem key={d.id} value={d.id}>
              {d.name}
            </MenuItem>
          ))}
        </TextField>
      )}

      <Box>
        <Button
          variant="outlined"
          startIcon={tone === 'playing' ? <CircularProgress size={16} /> : <VolumeUpIcon />}
          onClick={playTone}
          disabled={tone === 'playing' || devices.length === 0}
        >
          {tone === 'playing' ? t('audio.testing') : t('audio.test')}
        </Button>
      </Box>

      {tone === 'asked' && (
        <Alert severity="info" sx={{ alignItems: 'center' }}>
          <Stack spacing={1}>
            <span>{t('audio.heard')}</span>
            <Stack direction="row" spacing={1}>
              <Button size="small" variant="contained" onClick={() => setTone('idle')}>
                {t('audio.yes')}
              </Button>
              <Button
                size="small"
                onClick={() => {
                  setHeardNo(true);
                  setTone('idle');
                }}
              >
                {t('audio.no')}
              </Button>
            </Stack>
          </Stack>
        </Alert>
      )}

      {heardNo && <Alert severity="warning">{t('audio.retry_hint')}</Alert>}
      {tone === 'failed' && <Alert severity="error">{t('audio.test_failed')}</Alert>}

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {t('audio.volume')}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {t('audio.volume_hint')}
        </Typography>
        <Stack spacing={2} sx={{ mt: 2 }}>
          {(
            [
              ['volume_min', minVol, setMinVol],
              ['volume_default', defVol, setDefVol],
              ['volume_max', maxVol, setMaxVol],
            ] as const
          ).map(([key, value, setter]) => (
            <Box key={key}>
              <Typography variant="body2">
                {t(`audio.${key}`)}: {value}%
              </Typography>
              <Slider
                value={value}
                onChange={(_, v) => setter(v as number)}
                min={0}
                max={100}
                size="small"
              />
            </Box>
          ))}
        </Stack>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}
    </Stack>
  );
};
