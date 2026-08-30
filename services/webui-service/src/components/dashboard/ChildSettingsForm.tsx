import React, { useEffect, useState } from 'react';
import { Alert, Box, FormControlLabel, Slider, Switch, TextField, Typography } from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { AudioConfig, GeneralConfig, AllowedUsageTimeSlot } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';
import { VolumeSlider } from '@/components/ui/VolumeSlider';
import { SettingsSection } from '@/components/admin/SettingsSection';

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
          bedtime_fade_enabled: gen.bedtime_fade_enabled ?? false,
          bedtime_fade_duration_minutes: gen.bedtime_fade_duration_minutes ?? 15,
          bedtime_fade_interval_seconds: gen.bedtime_fade_interval_seconds ?? 30,
          bedtime_fade_step_percent: gen.bedtime_fade_step_percent ?? 2,
        });
        setAudioConfig(audio);
      })
      .catch(() => setError(t('load_error')))
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
        bedtime_fade_enabled: general.bedtime_fade_enabled,
        bedtime_fade_duration_minutes: general.bedtime_fade_duration_minutes,
        bedtime_fade_interval_seconds: general.bedtime_fade_interval_seconds,
        bedtime_fade_step_percent: general.bedtime_fade_step_percent,
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
    // Dieselbe Gliederung wie die Einstellungsseite: fette Section-Ueberschrift
    // mit Trennlinie, Erklaertext direkt darunter. Vorher trug diese Seite als
    // einzige eigene, blasse `overline`-Ueberschriften mit Trennlinien
    // *zwischen* den Themen - dasselbe Formular sah je nach Einstiegspunkt
    // anders aus.
    <Box display="flex" flexDirection="column">
      <SettingsSection title={t('general.usage_times')} description={t('general.usage_times_hint')}>
        <Box display="flex" flexDirection="column" gap={2}>
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
        </Box>
      </SettingsSection>

      <SettingsSection
        title={tCommon('dashboard.daily_limit')}
        description={tCommon('dashboard.daily_limit_hint')}
      >
        <Box display="flex" flexDirection="column" gap={2}>
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
        </Box>
      </SettingsSection>

      <SettingsSection title={t('audio.volume_settings')}>
        <Box display="flex" flexDirection="column" gap={2}>
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
        </Box>
      </SettingsSection>

      <SettingsSection title={t('general.bedtime_fade')}>
        <Box display="flex" flexDirection="column" gap={2}>
          <FormControlLabel
            control={
              <Switch
                checked={general.bedtime_fade_enabled ?? false}
                onChange={(e) =>
                  setGeneral((p) => (p ? { ...p, bedtime_fade_enabled: e.target.checked } : p))
                }
              />
            }
            label={t('general.bedtime_fade_enabled')}
          />
          {(general.bedtime_fade_enabled ?? false) && (
            <Box
              display="flex"
              gap={2}
              flexWrap="wrap"
              sx={{ '& .MuiTextField-root': { flex: '1 1 140px', minWidth: 0 } }}
            >
              <TextField
                label={t('general.bedtime_fade_duration_minutes')}
                type="number"
                value={general.bedtime_fade_duration_minutes ?? 15}
                onChange={(e) =>
                  setGeneral((p) =>
                    p
                      ? {
                          ...p,
                          bedtime_fade_duration_minutes: Math.max(
                            1,
                            parseInt(e.target.value, 10) || 15
                          ),
                        }
                      : p
                  )
                }
                size="small"
                inputProps={{ min: 1, max: 120 }}
              />
              <TextField
                label={t('general.bedtime_fade_interval_seconds')}
                type="number"
                value={general.bedtime_fade_interval_seconds ?? 30}
                onChange={(e) =>
                  setGeneral((p) =>
                    p
                      ? {
                          ...p,
                          bedtime_fade_interval_seconds: Math.max(
                            5,
                            parseInt(e.target.value, 10) || 30
                          ),
                        }
                      : p
                  )
                }
                size="small"
                inputProps={{ min: 5, max: 300 }}
              />
              <TextField
                label={t('general.bedtime_fade_step_percent')}
                type="number"
                value={general.bedtime_fade_step_percent ?? 2}
                onChange={(e) =>
                  setGeneral((p) =>
                    p
                      ? {
                          ...p,
                          bedtime_fade_step_percent: Math.max(
                            0.5,
                            Math.min(50, parseFloat(e.target.value) || 2)
                          ),
                        }
                      : p
                  )
                }
                size="small"
                inputProps={{ min: 0.5, max: 50, step: 0.5 }}
              />
            </Box>
          )}
        </Box>
      </SettingsSection>

      {error && <Alert severity="error">{error}</Alert>}
      <Box sx={{ mt: error ? 2 : 0 }}>
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
