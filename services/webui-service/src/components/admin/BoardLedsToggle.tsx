import React, { useCallback, useEffect, useState } from 'react';
import { FormControlLabel, Switch, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi, type BoardLedsResponse } from '@/api/system';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

/**
 * Die grüne/rote Status-LED des Raspberry Pi selbst abschalten – gehört zu den
 * Lichtern am Gerät, nicht zur Netzwerk- oder Wartungskonfiguration.
 */
export const BoardLedsToggle: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showError } = useToast();
  const [boardLeds, setBoardLeds] = useState<BoardLedsResponse | null>(null);

  const load = useCallback(async () => {
    try {
      setBoardLeds(await systemApi.getBoardLeds());
    } catch {
      setBoardLeds(null);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange = async (on: boolean) => {
    try {
      await systemApi.setBoardLeds(on);
      setBoardLeds(await systemApi.getBoardLeds());
    } catch {
      showError(t('board_leds_set_failed', { ns: 'errors' }));
    }
  };

  if (boardLeds == null) return null;

  return (
    <SettingsBlock title={t('system.board_leds_title')}>
      <FormControlLabel
        control={
          <Switch
            checked={boardLeds.stealth}
            onChange={(_, checked) => handleChange(checked)}
            color="primary"
          />
        }
        label={t('system.stealth_mode')}
        sx={{ display: 'block' }}
      />
      <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 0.5 }}>
        {t('system.stealth_hint')}
      </Typography>
    </SettingsBlock>
  );
};
