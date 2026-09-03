import React from 'react';
import { Box, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

/**
 * How long the listening statistics stay before they age out.
 *
 * Used to sit on the parent dashboard, in the same form as the daily limit and
 * the usage-time rules - but it is not a rule for the child, it is a setting
 * about the box's own data, changed once and rarely revisited. That is the
 * dashboard/settings split itself (`docs/services/webui/Settings-Structure.md`):
 * it belongs here, next to the backup it shares a topic with.
 */
export const AnalyticsRetentionBlock: React.FC = () => {
  const { t } = useTranslation('admin');
  const { value, setValue, save, saving } = useGeneralConfigField(
    'analytics_retention_weeks',
    52,
  );

  if (value === null) return null;

  return (
    <SettingsBlock
      title={t('general.analytics_retention')}
      description={t('general.analytics_retention_hint')}
    >
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <TextField
          label={t('general.analytics_retention_weeks')}
          type="number"
          value={value}
          onChange={(e) =>
            setValue(Math.max(0, Math.min(520, parseInt(e.target.value, 10) || 0)))
          }
          size="small"
          helperText={t('general.analytics_retention_zero')}
          inputProps={{ min: 0, max: 520 }}
          sx={{ maxWidth: 220 }}
        />
        <ActionButton
          actionType="primary"
          onClick={() => void save()}
          disabled={saving}
          loading={saving}
        >
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </SettingsBlock>
  );
};
