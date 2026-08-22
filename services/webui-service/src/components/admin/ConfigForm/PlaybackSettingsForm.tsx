import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Collapse,
  FormControlLabel,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { GeneralConfig, PlaybackEndBehavior } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

/**
 * Wiedergabe-Verhalten: was passiert beim Auflegen/Entfernen eines Tags und
 * was, wenn alles gespielt ist.
 *
 * Der frühere Einschlaf-Fade sitzt bewusst nicht mehr hier, sondern in
 * `ChildSettingsForm` – er ist eine Kinderschutz-Regel, keine Wiedergabe-Option.
 * Der Einschlaf-Timer hat seit der Gruppe „Abspielen" eine eigene Section
 * (`SleepTimerSettingsForm`).
 */

const DEFAULT_GUARD_MINUTES = 60;

const END_BEHAVIORS: readonly PlaybackEndBehavior[] = [
  'stop',
  'repeat',
  'repeat_while_tag',
] as const;

const END_BEHAVIOR_LABEL_KEY: Record<PlaybackEndBehavior, string> = {
  stop: 'playback.end_stop',
  repeat: 'playback.end_repeat',
  repeat_while_tag: 'playback.end_repeat_while_tag',
};

const END_BEHAVIOR_HINT_KEY: Record<PlaybackEndBehavior, string> = {
  stop: 'playback.end_stop_hint',
  repeat: 'playback.end_repeat_hint',
  repeat_while_tag: 'playback.end_repeat_while_tag_hint',
};

export const PlaybackSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [general, setGeneral] = useState<GeneralConfig | null>(null);
  const [loading, setLoading] = useState(true);
  /** Zuletzt gesehene Minutenzahl, damit das Abschalten den Wert nicht vergisst. */
  const [guardMinutes, setGuardMinutes] = useState(DEFAULT_GUARD_MINUTES);

  useEffect(() => {
    configApi
      .getGeneral()
      .then((data) => {
        const g = data as GeneralConfig;
        setGeneral({
          ...g,
          stop_playback_on_tag_remove: g.stop_playback_on_tag_remove ?? false,
          resume_on_tag_rescan: g.resume_on_tag_rescan ?? true,
          playback_end_behavior: g.playback_end_behavior ?? 'stop',
          playback_loop_guard_minutes: g.playback_loop_guard_minutes ?? DEFAULT_GUARD_MINUTES,
        });
        if (g.playback_loop_guard_minutes) setGuardMinutes(g.playback_loop_guard_minutes);
      })
      .catch(() => setError(t('load_error')))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (!general) return;
      await configApi.updateGeneral({
        stop_playback_on_tag_remove: general.stop_playback_on_tag_remove,
        resume_on_tag_rescan: general.resume_on_tag_rescan,
        playback_end_behavior: general.playback_end_behavior,
        playback_loop_guard_minutes: general.playback_loop_guard_minutes,
      });
      setError(null);
      showSuccess(t('general.save_success'));
    });

  if (loading || !general) return null;

  const endBehavior = general.playback_end_behavior ?? 'stop';
  const guardEnabled = (general.playback_loop_guard_minutes ?? 0) > 0;

  return (
    <Box>
      <SettingsBlock
        title={t('control.section_rfid')}
        description={t('control.section_rfid_hint')}
      >
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
        label={t('control.resume_on_tag_rescan')}
      />

      </SettingsBlock>

      <SettingsBlock
        title={t('playback.end_title')}
        description={t('playback.end_hint')}
      >
      {/* Untereinander statt nebeneinander: die Beschriftungen sind ganze
          Halbsaetze und wuerden am Telefon sonst waagerecht ueberlaufen. */}
      <ToggleButtonGroup
        orientation="vertical"
        fullWidth
        exclusive
        value={endBehavior}
        onChange={(_, v: PlaybackEndBehavior | null) => {
          if (!v) return;
          setGeneral((p) => (p ? { ...p, playback_end_behavior: v } : p));
        }}
      >
        {END_BEHAVIORS.map((value) => (
          <ToggleButton key={value} value={value} sx={{ textAlign: 'left', py: 1 }}>
            <Box sx={{ width: '100%' }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {t(END_BEHAVIOR_LABEL_KEY[value])}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', textTransform: 'none' }}
              >
                {t(END_BEHAVIOR_HINT_KEY[value])}
              </Typography>
            </Box>
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      {/* Nur sinnvoll, wenn ueberhaupt wiederholt wird. */}
      <Collapse in={endBehavior !== 'stop'} unmountOnExit>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <FormControlLabel
            control={
              <Switch
                checked={guardEnabled}
                onChange={(e) =>
                  setGeneral((p) =>
                    p
                      ? {
                          ...p,
                          playback_loop_guard_minutes: e.target.checked ? guardMinutes : 0,
                        }
                      : p
                  )
                }
              />
            }
            label={t('playback.guard_enabled')}
          />
          {guardEnabled && (
            <TextField
              label={t('playback.guard_minutes')}
              type="number"
              value={general.playback_loop_guard_minutes ?? guardMinutes}
              onChange={(e) => {
                const parsed = parseInt(e.target.value, 10);
                const minutes = Math.max(5, Math.min(1440, Number.isNaN(parsed) ? DEFAULT_GUARD_MINUTES : parsed));
                setGuardMinutes(minutes);
                setGeneral((p) => (p ? { ...p, playback_loop_guard_minutes: minutes } : p));
              }}
              size="small"
              fullWidth
              inputProps={{ min: 5, max: 1440 }}
              helperText={t('playback.guard_minutes_hint')}
            />
          )}
        </Box>
      </Collapse>
      </SettingsBlock>

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton actionType="primary" onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
