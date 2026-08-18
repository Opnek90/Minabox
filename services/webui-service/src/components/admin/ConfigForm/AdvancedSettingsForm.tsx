import React, { useEffect, useState } from 'react';
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
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { GeneralConfig } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';

/**
 * Geräte-ID, Protokoll-Tiefe und MQTT-Verbindung. Bewusst unter „Technische
 * Details" einsortiert – wer diese Werte nicht kennt, muss sie nicht ändern.
 */
export const AdvancedSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [general, setGeneral] = useState<GeneralConfig | null>(null);

  useEffect(() => {
    configApi
      .getGeneral()
      .then((data) => setGeneral(data as GeneralConfig))
      .catch(() => setError(t('load_error', { defaultValue: 'Laden fehlgeschlagen' })));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (!general) return;
      await configApi.updateGeneral({
        minabox_device_id: general.minabox_device_id,
        log_level: general.log_level,
        mqtt_broker: general.mqtt_broker,
        mqtt_port: general.mqtt_port,
      });
      setError(null);
      showSuccess(t('general.save_success'));
    });

  if (!general) return null;

  return (
    <Box display="flex" flexDirection="column" sx={{ gap: { xs: 2, sm: 3 } }}>
      <TextField
        label={t('general.device_id')}
        value={general.minabox_device_id}
        onChange={(e) => setGeneral((p) => (p ? { ...p, minabox_device_id: e.target.value } : p))}
        size="small"
        fullWidth
      />
      <FormControl fullWidth size="small">
        <InputLabel>{t('general.log_level')}</InputLabel>
        <Select
          value={general.log_level}
          label={t('general.log_level')}
          onChange={(e) => setGeneral((p) => (p ? { ...p, log_level: e.target.value } : p))}
        >
          {['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].map((lvl) => (
            <MenuItem key={lvl} value={lvl}>{lvl}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <TextField
        label={t('general.mqtt_broker')}
        value={general.mqtt_broker}
        onChange={(e) => setGeneral((p) => (p ? { ...p, mqtt_broker: e.target.value } : p))}
        size="small"
        fullWidth
      />
      <TextField
        label={t('general.mqtt_port')}
        type="number"
        value={general.mqtt_port}
        onChange={(e) =>
          setGeneral((p) => (p ? { ...p, mqtt_port: parseInt(e.target.value, 10) || 1883 } : p))
        }
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
          onClick={handleSave}
          disabled={saving}
        >
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
