import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Paper,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { configApi } from '@/api/config';
import type { DisplayConfig } from '@/types/api';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

/**
 * Display settings.
 *
 * This used to be a layout editor: nine element types, three areas, an order
 * and a font. That grid stopped reaching the panel when every state of the box
 * got a screen of its own, so the editor was a control that changed nothing.
 * What is left is the hardware and an on/off switch.
 */
export const DisplayConfigPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [config, setConfig] = useState<DisplayConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    configApi
      .getDisplay()
      .then(setConfig)
      .catch(() => setError('Laden fehlgeschlagen'));
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const updated = await configApi.updateDisplay(config);
      setConfig(updated);
      showSuccess(t('display.save_success'));
    } catch {
      showError(t('display.save_error'));
    } finally {
      setSaving(false);
    }
  };

  if (error) return <Alert severity="error">{error}</Alert>;
  if (!config) return <Typography>…</Typography>;

  return (
    <Box>
      <SettingsBlock title={t('display.hardware')} description={t('display.hardware_hint')}>
        <Paper sx={{ p: 2, mb: 2 }}>
          <Box
            display="flex"
            alignItems="center"
            justifyContent="space-between"
            flexWrap="wrap"
            gap={2}
          >
            <Box display="flex" alignItems="center" gap={2}>
              <Typography variant="overline" color="text.secondary">
                {t('display.enabled')}
              </Typography>
              <Switch
                checked={config.enabled}
                onChange={(_, checked) =>
                  setConfig((prev) => (prev ? { ...prev, enabled: checked } : prev))
                }
                color="primary"
              />
            </Box>
            {/* Inputs wrap on mobile to avoid overflow */}
            <Box display="flex" gap={1} alignItems="center" flexWrap="wrap">
              <TextField
                label={t('display.i2c_bus')}
                type="number"
                size="small"
                value={config.i2c_bus}
                onChange={(e) =>
                  setConfig((prev) =>
                    prev ? { ...prev, i2c_bus: parseInt(e.target.value, 10) || 1 } : prev
                  )
                }
                inputProps={{ min: 0, max: 9 }}
                sx={{ width: { xs: '100%', sm: 90 } }}
              />
              <TextField
                label={t('display.i2c_address')}
                type="number"
                size="small"
                value={config.i2c_address}
                onChange={(e) =>
                  setConfig((prev) =>
                    prev
                      ? { ...prev, i2c_address: parseInt(e.target.value, 10) || 60 }
                      : prev
                  )
                }
                inputProps={{ min: 0, max: 127 }}
                sx={{ width: { xs: '100%', sm: 100 } }}
              />
            </Box>
          </Box>
        </Paper>

        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? '…' : t('display.save_button')}
        </Button>
      </SettingsBlock>
    </Box>
  );
};
