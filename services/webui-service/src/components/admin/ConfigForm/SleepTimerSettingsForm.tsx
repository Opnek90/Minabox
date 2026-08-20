import React, { useEffect, useState } from 'react';
import { Alert, Box, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { GeneralConfig } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

/**
 * Einschlaf-Timer: die Dauer, die der physische Knopf einschaltet.
 *
 * Eigene Section neben `PlaybackSettingsForm`, damit die Gruppe „Abspielen"
 * zwei benennbare Zeilen hat – „Einschlafen" ist die Frage, die Eltern abends
 * stellen, und die soll im Akkordeon-Untertitel auch so dastehen.
 */
export const SleepTimerSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [minutes, setMinutes] = useState<number | null>(null);

  useEffect(() => {
    configApi
      .getGeneral()
      .then((data) => setMinutes((data as GeneralConfig).sleep_timer_minutes ?? 30))
      .catch(() => setError(t('load_error')));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (minutes === null) return;
      await configApi.updateGeneral({ sleep_timer_minutes: minutes });
      setError(null);
      showSuccess(t('general.save_success'));
    });

  if (minutes === null) return null;

  return (
    <Box>
      <SettingsBlock title={t('general.sleep_timer')}>
        <TextField
          label={t('general.sleep_timer_minutes')}
          type="number"
          value={minutes}
          onChange={(e) => setMinutes(Math.max(1, parseInt(e.target.value, 10) || 30))}
          size="small"
          fullWidth
          inputProps={{ min: 1, max: 480 }}
          helperText={t('general.sleep_timer_minutes_hint')}
        />
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
