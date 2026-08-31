import React from 'react';
import { Alert, Box, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

const DEFAULT_MINUTES = 30;

/**
 * Sleep timer: the duration the physical button switches on.
 *
 * A section of its own next to `PlaybackSettingsForm`, so the "Playback" group
 * has two nameable rows - "Sleep" is the question parents ask in the evening,
 * and it should read that way in the accordion subtitle too.
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
