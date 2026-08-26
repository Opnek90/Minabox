import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Paper,
  Slider,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { configApi } from '@/api/config';
import type { DisplayBrightness, DisplayConfig } from '@/types/api';
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

  // The service fills these in when the file leaves them out, so the form has
  // to as well - otherwise the first save would write nulls over them.
  const brightness: DisplayBrightness = {
    day: 255,
    night: 40,
    night_from: '20:00',
    night_to: '07:00',
    off_at_night: false,
    ...(config.brightness ?? {}),
  };

  const setBrightness = (patch: Partial<DisplayBrightness>) =>
    setConfig((prev) =>
      prev ? { ...prev, brightness: { ...brightness, ...patch } } : prev
    );

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

      </SettingsBlock>

      <SettingsBlock
        title={t('display.brightness')}
        description={t('display.brightness_hint')}
      >
        <Paper sx={{ p: 2, mb: 2 }}>
          <Box display="flex" flexDirection="column" gap={2}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('display.brightness_day')}
              </Typography>
              <Slider
                value={brightness.day}
                min={0}
                max={255}
                valueLabelDisplay="auto"
                onChange={(_, value) => setBrightness({ day: value as number })}
              />
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('display.brightness_night')}
              </Typography>
              <Slider
                value={brightness.night}
                min={0}
                max={255}
                valueLabelDisplay="auto"
                onChange={(_, value) => setBrightness({ night: value as number })}
              />
            </Box>
            <Box display="flex" gap={1} alignItems="center" flexWrap="wrap">
              <TextField
                label={t('display.night_from')}
                type="time"
                size="small"
                value={brightness.night_from}
                onChange={(e) => setBrightness({ night_from: e.target.value })}
                InputLabelProps={{ shrink: true }}
                sx={{ width: { xs: '100%', sm: 140 } }}
              />
              <TextField
                label={t('display.night_to')}
                type="time"
                size="small"
                value={brightness.night_to}
                onChange={(e) => setBrightness({ night_to: e.target.value })}
                InputLabelProps={{ shrink: true }}
                sx={{ width: { xs: '100%', sm: 140 } }}
              />
            </Box>
            <Box display="flex" alignItems="center" gap={1}>
              <Switch
                checked={brightness.off_at_night}
                onChange={(_, checked) => setBrightness({ off_at_night: checked })}
                color="primary"
              />
              <Typography variant="body2">{t('display.off_at_night')}</Typography>
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
