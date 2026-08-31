import React from 'react';
import {
  Alert,
  Box,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigFields } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

/**
 * Device ID, log level and MQTT connection. Deliberately filed under "Technical
 * details" - anyone who does not know these values does not need to change them.
 */
export const AdvancedSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { values, setValue, save, saving, error } = useGeneralConfigFields({
    minabox_device_id: '',
    log_level: 'INFO',
    mqtt_broker: '',
    mqtt_port: 1883,
  });

  if (!values) return null;

  return (
    <Box display="flex" flexDirection="column" sx={{ gap: { xs: 2, sm: 3 } }}>
      <TextField
        label={t('general.device_id')}
        value={values.minabox_device_id}
        onChange={(e) => setValue('minabox_device_id', e.target.value)}
        size="small"
        fullWidth
      />
      <FormControl fullWidth size="small">
        <InputLabel>{t('general.log_level')}</InputLabel>
        <Select
          value={values.log_level}
          label={t('general.log_level')}
          onChange={(e) => setValue('log_level', e.target.value)}
        >
          {LOG_LEVELS.map((lvl) => (
            <MenuItem key={lvl} value={lvl}>{lvl}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <TextField
        label={t('general.mqtt_broker')}
        value={values.mqtt_broker}
        onChange={(e) => setValue('mqtt_broker', e.target.value)}
        size="small"
        fullWidth
      />
      <TextField
        label={t('general.mqtt_port')}
        type="number"
        value={values.mqtt_port}
        onChange={(e) => setValue('mqtt_port', parseInt(e.target.value, 10) || 1883)}
        size="small"
        fullWidth
        inputProps={{ min: 1, max: 65535 }}
      />
      <Typography variant="caption" color="text.secondary">
        {t('general.restart_required')}
      </Typography>
      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton
          actionType="primary"
          startIcon={<SaveIcon />}
          onClick={save}
          disabled={saving}
        >
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
