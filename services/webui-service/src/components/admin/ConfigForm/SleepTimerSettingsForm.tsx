import React from 'react';
import { Alert, Box, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

const DEFAULT_MINUTES = 30;

/**
 * Einschlaf-Timer: die Dauer, die der physische Knopf einschaltet.
 *
 * Eigene Section neben `PlaybackSettingsForm`, damit die Gruppe „Abspielen"
 * zwei benennbare Zeilen hat – „Einschlafen" ist die Frage, die Eltern abends
 * stellen, und die soll im Akkordeon-Untertitel auch so dastehen.
 */
export const SleepTimerSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { value: minutes, setValue, save, saving, error } = useGeneralConfigField(
    'sleep_timer_minutes',
    DEFAULT_MINUTES,
  );

  if (minutes === null) return null;

  return (
    <Box>
      <SettingsBlock title={t('general.sleep_timer')}>
        <TextField
          label={t('general.sleep_timer_minutes')}
          type="number"
          value={minutes}
          onChange={(e) => setValue(Math.max(1, parseInt(e.target.value, 10) || DEFAULT_MINUTES))}
          size="small"
          fullWidth
          inputProps={{ min: 1, max: 480 }}
          helperText={t('general.sleep_timer_minutes_hint')}
        />
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
