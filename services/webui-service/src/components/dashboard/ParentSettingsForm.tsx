import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
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
import { statsApi } from '@/api/stats';
import type { AudioConfig, GeneralConfig, AllowedUsageTimeSlot, UsageTodayResponse } from '@/types/api';

const WEEKDAY_KEYS = [
  'weekday_mo',
  'weekday_tu',
  'weekday_we',
  'weekday_th',
  'weekday_fr',
  'weekday_sa',
  'weekday_su',
] as const;

export const ParentSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { t: tCommon } = useTranslation('common');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();

  const [general, setGeneral] = useState<GeneralConfig | null>(null);
  const [audioConfig, setAudioConfig] = useState<AudioConfig | null>(null);
  const [usageToday, setUsageToday] = useState<UsageTodayResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUsageToday = () => {
    statsApi.getUsageToday().then(setUsageToday).catch(() => setUsageToday(null));
  };

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
          daily_limit_enabled: gen.daily_limit_enabled ?? false,
          daily_limit_minutes: gen.daily_limit_minutes ?? 120,
        });
        setAudioConfig(audio);
      })
      .catch(() => setError('Laden fehlgeschlagen'))
      .finally(() => setLoading(false));
  }, [setError]);

  useEffect(() => {
    loadUsageToday();
  }, []);

  useEffect(() => {
    if (!general?.daily_limit_enabled) return;
    const intervalId = setInterval(loadUsageToday, 60_000);
    return () => clearInterval(intervalId);
  }, [general?.daily_limit_enabled]);

  const handleSave = () =>
    run(async () => {
      if (!general || !audioConfig) return;
      await configApi.updateGeneral({
        allowed_usage_times: general.allowed_usage_times,
        daily_limit_enabled: general.daily_limit_enabled,
        daily_limit_minutes: general.daily_limit_minutes,
      });
      await configApi.updateAudio({
        max_volume: audioConfig.max_volume,
        default_volume: audioConfig.default_volume,
      });
      setError(null);
      showSuccess(t('general.save_success'));
      loadUsageToday();
    });

  if (loading || !general || !audioConfig) return null;

  return (
    <Box display="flex" flexDirection="column" maxWidth={480} sx={{ gap: 3 }}>
      <Typography variant="subtitle1" color="text.secondary">
        {t('general.usage_times')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
        {t('general.usage_times_hint')}
      </Typography>
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

      <Divider />

      {usageToday != null && (
        <Box sx={{ p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
          <Typography variant="body2">
            {tCommon('dashboard.minutes_today')}: {usageToday.minutes_today.toFixed(1)} Min.
          </Typography>
          {usageToday.daily_limit_enabled && (
            <Typography variant="body2" color="text.secondary">
              {tCommon('dashboard.remaining_minutes')}: {Math.max(0, Math.round(usageToday.daily_limit_minutes - usageToday.minutes_today))} Min.
            </Typography>
          )}
        </Box>
      )}

      <Typography variant="subtitle1" color="text.secondary">
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

      <Typography variant="subtitle1" color="text.secondary">
        {t('audio.max_volume')}
      </Typography>
      <Box>
        <Typography variant="body2" gutterBottom>
          {t('audio.max_volume')}: {audioConfig.max_volume}%
        </Typography>
        <Slider
          value={audioConfig.max_volume}
          min={0}
          max={100}
          step={5}
          marks
          valueLabelDisplay="auto"
          onChange={(_, v) =>
            setAudioConfig((p) => (p ? { ...p, max_volume: v as number } : p))
          }
        />
      </Box>
      <Box>
        <Typography variant="body2" gutterBottom>
          {t('audio.default_volume')}: {audioConfig.default_volume}%
        </Typography>
        <Slider
          value={audioConfig.default_volume}
          min={0}
          max={audioConfig.max_volume}
          step={5}
          marks
          valueLabelDisplay="auto"
          onChange={(_, v) =>
            setAudioConfig((p) => (p ? { ...p, default_volume: v as number } : p))
          }
        />
      </Box>

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          {tCommon('actions.save')}
        </Button>
      </Box>
    </Box>
  );
};
