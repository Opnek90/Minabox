import React from 'react';
import { Alert, Box, InputAdornment, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { HelpTip } from '@/components/ui/HelpTip';

const MIN_UPLOAD_MB = 1;
const MAX_UPLOAD_MB = 2048;
const DEFAULT_UPLOAD_MB = 100;

/**
 * The largest file that may be uploaded through the web interface.
 *
 * Sits with "Music folder", because both concern the same question: where the
 * media lands and how large it may be. The value takes effect immediately - the
 * backend re-reads it from `general_settings.json` on every upload, no restart
 * needed.
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
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <HelpTip
                  title={t('general.upload_limit_mb_hint')}
                  label={t('general.upload_limit_mb')}
                />
              </InputAdornment>
            ),
          }}
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
