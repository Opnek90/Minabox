import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Divider,
  FormControlLabel,
  Slider,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { AudioConfig, GeneralConfig, AllowedUsageTimeSlot } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';
import { VolumeSlider } from '@/components/ui/VolumeSlider';

const WEEKDAY_KEYS = [
  'weekday_mo',
  'weekday_tu',
  'weekday_we',
  'weekday_th',
  'weekday_fr',
  'weekday_sa',
  'weekday_su',
] as const;

export const ChildSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { t: tCommon } = useTranslation('common');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();

  const [general, setGeneral] = useState<GeneralConfig | null>(null);
  const [audioConfig, setAudioConfig] = useState<AudioConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([configApi.getGeneral(), configApi.getAudio()])
      .then(([g, audio]) => {
        const gen = g as GeneralConfig;
        const times = Array.isArray(gen.allowed_usage_times) ? gen.allowed_usage_times : [];
        const slots: AllowedUsageTimeSlot[] = [];
        for (let wd = 0; wd <= 6; wd++) {
          const existing = times.find((s) => s.weekday === wd);
          slots.push(existing ?? { weekday: wd, start: '07:00', end: '19:00' });
        }
        setGeneral({
          ...gen,
          allowed_usage_times: slots,
          usage_times_enabled: gen.usage_times_enabled ?? false,
          daily_limit_enabled: gen.daily_limit_enabled ?? false,
          daily_limit_minutes: gen.daily_limit_minutes ?? 120,
        });
        setAudioConfig(audio);
      })
      .catch(() => setError(t('load_error', { defaultValue: 'Laden fehlgeschlagen' })))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (!general || !audioConfig) return;
      await configApi.updateGeneral({
        allowed_usage_times: general.allowed_usage_times,
        usage_times_enabled: general.usage_times_enabled,
        daily_limit_enabled: general.daily_limit_enabled,
        daily_limit_minutes: general.daily_limit_minutes,
      });
      await configApi.updateAudio({
        min_volume: audioConfig.min_volume,
        max_volume: audioConfig.max_volume,
        default_volume: audioConfig.default_volume,
      });
      setError(null);
      showSuccess(t('general.save_success'));
    });

  if (loading) return null;
  if (!general || !audioConfig) return null;

  return (
    <Box display="flex" flexDirection="column" maxWidth={560} sx={{ gap: 3 }}>
      <Typography variant="overline" color="text.secondary">
        {t('general.usage_times')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
        {t('general.usage_times_hint')}
      </Typography>
      <FormControlLabel
        control={
          <Switch
            checked={general.usage_times_enabled ?? false}
            onChange={(e) =>
              setGeneral((p) => (p ? { ...p, usage_times_enabled: e.target.checked } : p))
            }
          />
        }
        label={t('general.usage_times_enabled')}
      />
      {(general.usage_times_enabled ?? false) && (
        <Box display="flex" flexDirection="column" gap={0.5}>
          {WEEKDAY_KEYS.map((key, idx) => {
            const slot = general.allowed_usage_times[idx];
            if (!slot) return null;
            return (
              <Box key={idx} display="flex" alignItems="center" gap={1} flexWrap="wrap">
                <Typography variant="body2" sx={{ minWidth: 32 }}>
                  {t(`general.${key}`)}
                </Typography>
                <TextField
                  size="small"
                  type="time"
                  value={slot.start}
                  onChange={(e) =>
                    setGeneral((p) => {
                      if (!p?.allowed_usage_times) return p;
                      const next = [...p.allowed_usage_times];
                      next[idx] = { ...next[idx], start: e.target.value };
                      return { ...p, allowed_usage_times: next };
                    })
                  }
                  inputProps={{ step: 300 }}
                />
                <TextField
                  size="small"
                  type="time"
                  value={slot.end}
                  onChange={(e) =>
                    setGeneral((p) => {
                      if (!p?.allowed_usage_times) return p;
                      const next = [...p.allowed_usage_times];
                      next[idx] = { ...next[idx], end: e.target.value };
                      return { ...p, allowed_usage_times: next };
                    })
                  }
                  inputProps={{ step: 300 }}
                />
              </Box>
            );
          })}
        </Box>
      )}

      <Divider />

      <Typography variant="overline" color="text.secondary">
        {tCommon('dashboard.daily_limit')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
        {tCommon('dashboard.daily_limit_hint')}
      </Typography>
      <FormControlLabel
        control={
          <Switch
            checked={general.daily_limit_enabled ?? false}
            onChange={(e) =>
              setGeneral((p) => (p ? { ...p, daily_limit_enabled: e.target.checked } : p))
            }
          />
        }
        label={tCommon('dashboard.daily_limit_enabled')}
      />
      {general.daily_limit_enabled && (
        <Box>
          <Typography variant="body2" gutterBottom>
            {tCommon('dashboard.daily_limit_minutes')}: {general.daily_limit_minutes ?? 120}
          </Typography>
          <Slider
            value={general.daily_limit_minutes ?? 120}
            min={1}
            max={480}
            step={5}
            marks
            valueLabelDisplay="auto"
            onChange={(_, v) =>
              setGeneral((p) => (p ? { ...p, daily_limit_minutes: v as number } : p))
            }
          />
        </Box>
      )}

      <Divider />

      <Typography variant="overline" color="text.secondary">
        {t('audio.volume_settings')}
      </Typography>

      <VolumeSlider
        label={t('audio.min_volume')}
        value={audioConfig.min_volume ?? 5}
        min={0}
        max={audioConfig.max_volume - 5}
        onChange={(v) => setAudioConfig((p) => (p ? { ...p, min_volume: v } : p))}
      />

      <VolumeSlider
        label={t('audio.max_volume')}
        value={audioConfig.max_volume}
        min={(audioConfig.min_volume ?? 5) + 5}
        max={100}
        onChange={(v) => setAudioConfig((p) => (p ? { ...p, max_volume: v } : p))}
      />

      <VolumeSlider
        label={t('audio.default_volume')}
        value={audioConfig.default_volume}
        min={audioConfig.min_volume ?? 5}
        max={audioConfig.max_volume}
        onChange={(v) => setAudioConfig((p) => (p ? { ...p, default_volume: v } : p))}
      />

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton
          actionType="primary"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
