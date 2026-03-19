import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  FormControlLabel,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { GeneralConfig } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';

export const ControlSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [general, setGeneral] = useState<GeneralConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    configApi
      .getGeneral()
      .then((data) => {
        const g = data as GeneralConfig;
        setGeneral({
          ...g,
          stop_playback_on_tag_remove: g.stop_playback_on_tag_remove ?? false,
          resume_on_tag_rescan: g.resume_on_tag_rescan ?? true,
          sleep_timer_minutes: g.sleep_timer_minutes ?? 30,
          bedtime_fade_enabled: g.bedtime_fade_enabled ?? false,
          bedtime_fade_duration_minutes: g.bedtime_fade_duration_minutes ?? 15,
          bedtime_fade_interval_seconds: g.bedtime_fade_interval_seconds ?? 30,
          bedtime_fade_step_percent: g.bedtime_fade_step_percent ?? 2,
        });
      })
      .catch(() => setError(t('load_error', { defaultValue: 'Laden fehlgeschlagen' })))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (!general) return;
      await configApi.updateGeneral({
        stop_playback_on_tag_remove: general.stop_playback_on_tag_remove,
        resume_on_tag_rescan: general.resume_on_tag_rescan,
        sleep_timer_minutes: general.sleep_timer_minutes,
        bedtime_fade_enabled: general.bedtime_fade_enabled,
        bedtime_fade_duration_minutes: general.bedtime_fade_duration_minutes,
        bedtime_fade_interval_seconds: general.bedtime_fade_interval_seconds,
        bedtime_fade_step_percent: general.bedtime_fade_step_percent,
      });
      setError(null);
      showSuccess(t('general.save_success'));
    });

  if (loading || !general) return null;

  return (
    <Box display="flex" flexDirection="column" maxWidth={560} sx={{ gap: 3 }}>
      <Typography variant="overline" color="text.secondary">
        {t('control.section_rfid')}
      </Typography>

      <FormControlLabel
        control={
          <Switch
            checked={general.stop_playback_on_tag_remove ?? false}
            onChange={(e) =>
              setGeneral((p) =>
                p ? { ...p, stop_playback_on_tag_remove: e.target.checked } : p
              )
            }
          />
        }
        label={t('control.stop_playback_on_tag_remove')}
      />

      <FormControlLabel
        control={
          <Switch
            checked={general.resume_on_tag_rescan ?? true}
            onChange={(e) =>
              setGeneral((p) =>
                p ? { ...p, resume_on_tag_rescan: e.target.checked } : p
              )
            }
          />
        }
        label={t('control.resume_on_tag_rescan', {
          defaultValue: 'Ab letzter Position fortsetzen (Tag erneut auflegen)',
        })}
      />

      <Typography variant="overline" color="text.secondary" sx={{ mt: 1 }}>
        {t('general.sleep_timer')}
      </Typography>
      <TextField
        label={t('general.sleep_timer_minutes')}
        type="number"
        value={general.sleep_timer_minutes ?? 30}
        onChange={(e) =>
          setGeneral((p) =>
            p
              ? { ...p, sleep_timer_minutes: Math.max(1, parseInt(e.target.value, 10) || 30) }
              : p
          )
        }
        size="small"
        fullWidth
        inputProps={{ min: 1, max: 480 }}
        helperText={t('general.sleep_timer_minutes_hint')}
      />

      <Typography variant="overline" color="text.secondary">
        {t('general.bedtime_fade')}
      </Typography>
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
      <Box
        display="flex"
        gap={2}
        flexWrap="wrap"
        sx={{
          '& .MuiTextField-root': { flex: '1 1 140px', minWidth: 0 },
        }}
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

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton actionType="primary" onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
