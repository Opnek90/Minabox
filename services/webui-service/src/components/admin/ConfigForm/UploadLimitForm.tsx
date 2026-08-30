import React from 'react';
import { Alert, Box, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

const MIN_UPLOAD_MB = 1;
const MAX_UPLOAD_MB = 2048;
const DEFAULT_UPLOAD_MB = 100;

/**
 * Groesste Datei, die ueber die Weboberflaeche hochgeladen werden darf.
 *
 * Steht bei „Musik-Ordner", weil beides dieselbe Frage betrifft: wo die Medien
 * landen und wie gross sie sein duerfen. Der Wert wirkt sofort – das Backend
 * liest ihn bei jedem Upload neu aus `general_settings.json`, ein Neustart ist
 * nicht noetig.
 */
export const UploadLimitForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { value: sizeMb, setValue, save, saving, error } = useGeneralConfigField(
    'max_upload_size_mb',
    DEFAULT_UPLOAD_MB,
  );

  if (sizeMb === null) return null;

  return (
    <Box>
      <SettingsBlock title={t('general.upload_limit')}>
        <TextField
          label={t('general.upload_limit_mb')}
          type="number"
          value={sizeMb}
          onChange={(e) =>
            setValue(
              Math.max(
                MIN_UPLOAD_MB,
                Math.min(MAX_UPLOAD_MB, parseInt(e.target.value, 10) || DEFAULT_UPLOAD_MB),
              ),
            )
          }
          size="small"
          fullWidth
          inputProps={{ min: MIN_UPLOAD_MB, max: MAX_UPLOAD_MB }}
          helperText={t('general.upload_limit_mb_hint')}
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
