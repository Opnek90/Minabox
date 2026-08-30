import React, { useState } from 'react';
import {
  Alert,
  Box,
  Collapse,
  FormControlLabel,
  FormHelperText,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigFields } from '@/hooks/useGeneralConfig';
import type { PlaybackEndBehavior } from '@/types/api';
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

const END_BEHAVIOR_LABEL_KEY = {
  stop: 'playback.end_stop',
  repeat: 'playback.end_repeat',
  repeat_while_tag: 'playback.end_repeat_while_tag',
} as const satisfies Record<PlaybackEndBehavior, string>;

const END_BEHAVIOR_HINT_KEY = {
  stop: 'playback.end_stop_hint',
  repeat: 'playback.end_repeat_hint',
  repeat_while_tag: 'playback.end_repeat_while_tag_hint',
} as const satisfies Record<PlaybackEndBehavior, string>;

export const PlaybackSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { values, setValue, save, saving, error } = useGeneralConfigFields({
    stop_playback_on_tag_remove: false,
    resume_on_tag_rescan: true,
    playback_end_behavior: 'stop',
    playlist_shuffle: true,
    playback_loop_guard_minutes: DEFAULT_GUARD_MINUTES,
  });
  /** Zuletzt gesehene Minutenzahl, damit das Abschalten den Wert nicht vergisst. */
  const [guardMinutes, setGuardMinutes] = useState(DEFAULT_GUARD_MINUTES);

  if (!values) return null;

  const endBehavior = values.playback_end_behavior;
  const guardEnabled = values.playback_loop_guard_minutes > 0;

  return (
    <Box>
      <SettingsBlock
        title={t('control.section_rfid')}
        description={t('control.section_rfid_hint')}
      >
      <FormControlLabel
        control={
          <Switch
            checked={values.stop_playback_on_tag_remove}
            onChange={(e) => setValue('stop_playback_on_tag_remove', e.target.checked)}
          />
        }
        label={t('control.stop_playback_on_tag_remove')}
      />

      <FormControlLabel
        control={
          <Switch
            checked={values.resume_on_tag_rescan}
            onChange={(e) => setValue('resume_on_tag_rescan', e.target.checked)}
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
          setValue('playback_end_behavior', v);
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
                  setValue('playback_loop_guard_minutes', e.target.checked ? guardMinutes : 0)
                }
              />
            }
            label={t('playback.guard_enabled')}
          />
          {guardEnabled && (
            <TextField
              label={t('playback.guard_minutes')}
              type="number"
              value={values.playback_loop_guard_minutes}
              onChange={(e) => {
                const parsed = parseInt(e.target.value, 10);
                const minutes = Math.max(5, Math.min(1440, Number.isNaN(parsed) ? DEFAULT_GUARD_MINUTES : parsed));
                setGuardMinutes(minutes);
                setValue('playback_loop_guard_minutes', minutes);
              }}
              size="small"
              fullWidth
              inputProps={{ min: 5, max: 1440 }}
              helperText={t('playback.guard_minutes_hint')}
            />
          )}
        </Box>
      </Collapse>

      <FormControlLabel
        control={
          <Switch
            checked={values.playlist_shuffle}
            onChange={(e) => setValue('playlist_shuffle', e.target.checked)}
          />
        }
        label={t('playback.playlist_shuffle')}
      />
      <FormHelperText>{t('playback.playlist_shuffle_hint')}</FormHelperText>
      </SettingsBlock>

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton actionType="primary" onClick={save} disabled={saving}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
