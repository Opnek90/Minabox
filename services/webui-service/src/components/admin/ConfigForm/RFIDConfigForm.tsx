import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { RFIDConfig } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';

const DEFAULT_RFID_CONFIG: RFIDConfig = {
  reader_type: 'PN532',
  interface: 'I2C',
  scan_interval_ms: 200,
  duplicate_suppression_ms: 2000,
};

export const RFIDConfigForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [config, setConfig] = useState<RFIDConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    configApi
      .getRfid()
      .then((data) => setConfig({ ...DEFAULT_RFID_CONFIG, ...data }))
      .catch(() => setError(t('load_error', { defaultValue: 'Laden fehlgeschlagen' })))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (!config) return;
      const updated = await configApi.updateRfid(config);
      setConfig(updated);
      showSuccess(t('rfid.save_success'));
    });

  if (loading || !config) return null;

  return (
    <Box display="flex" flexDirection="column" maxWidth={560} sx={{ gap: { xs: 2, sm: 3 } }}>
      <FormControl fullWidth size="small">
        <InputLabel>{t('rfid.fields.reader_type')}</InputLabel>
        <Select
          value={config.reader_type}
          label={t('rfid.fields.reader_type')}
          onChange={(e) => setConfig((p) => p ? { ...p, reader_type: e.target.value } : p)}
        >
          <MenuItem value="PN532">{t('rfid.reader_types.PN532')}</MenuItem>
          <MenuItem value="Mock">{t('rfid.reader_types.Mock')}</MenuItem>
        </Select>
      </FormControl>
      <FormControl fullWidth size="small">
        <InputLabel>{t('rfid.fields.interface')}</InputLabel>
        <Select
          value={config.interface}
          label={t('rfid.fields.interface')}
          onChange={(e) => setConfig((p) => p ? { ...p, interface: e.target.value } : p)}
        >
          <MenuItem value="I2C">{t('rfid.interfaces.I2C')}</MenuItem>
          <MenuItem value="SPI">{t('rfid.interfaces.SPI')}</MenuItem>
          <MenuItem value="UART">{t('rfid.interfaces.UART')}</MenuItem>
        </Select>
      </FormControl>
      <TextField
        label={t('rfid.fields.scan_interval_ms')}
        type="number"
        value={config.scan_interval_ms}
        onChange={(e) =>
          setConfig((p) => p ? { ...p, scan_interval_ms: parseInt(e.target.value) || 0 } : p)
        }
        size="small" fullWidth
        inputProps={{ min: 100, step: 100 }}
      />
      <TextField
        label={t('rfid.fields.duplicate_suppression_ms')}
        type="number"
        value={config.duplicate_suppression_ms}
        onChange={(e) =>
          setConfig((p) => p ? { ...p, duplicate_suppression_ms: parseInt(e.target.value) || 0 } : p)
        }
        size="small" fullWidth
        inputProps={{ min: 0, step: 100 }}
      />
      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton actionType="primary" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
