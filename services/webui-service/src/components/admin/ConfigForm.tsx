import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Snackbar,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { configApi } from '@/api/config';
import type { AudioConfig, RFIDConfig, GeneralConfig } from '@/types/api';

// ============================================================================
// Audio Config Form
// ============================================================================

export const AudioConfigForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const [config, setConfig] = useState<AudioConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    configApi.getAudio().then(setConfig).catch(() => setError('Laden fehlgeschlagen')).finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await configApi.updateAudio(config);
      setConfig(updated);
      setSuccess(true);
    } catch {
      setError('Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  if (loading || !config) return null;

  return (
    <Box display="flex" flexDirection="column" gap={3} maxWidth={560}>
      <TextField
        label={t('audio.output_device_type')}
        value={config.output_device_type}
        onChange={(e) => setConfig((p) => p ? { ...p, output_device_type: e.target.value } : p)}
        size="small"
        fullWidth
      />
      <TextField
        label={t('audio.output_device_name')}
        placeholder={t('audio.output_device_name_placeholder')}
        value={config.output_device_name}
        onChange={(e) => setConfig((p) => p ? { ...p, output_device_name: e.target.value } : p)}
        size="small"
        fullWidth
      />
      <Box>
        <Typography gutterBottom variant="body2">
          {t('audio.max_volume')}: {config.max_volume}%
        </Typography>
        <Slider
          value={config.max_volume}
          min={0}
          max={100}
          step={5}
          onChange={(_, v) => setConfig((p) => p ? { ...p, max_volume: v as number } : p)}
          marks
          valueLabelDisplay="auto"
        />
      </Box>
      <Box>
        <Typography gutterBottom variant="body2">
          {t('audio.default_volume')}: {config.default_volume}%
        </Typography>
        <Slider
          value={config.default_volume}
          min={0}
          max={config.max_volume}
          step={5}
          onChange={(_, v) => setConfig((p) => p ? { ...p, default_volume: v as number } : p)}
          marks
          valueLabelDisplay="auto"
        />
      </Box>
      {config.resume_on_startup !== undefined && (
        <FormControlLabel
          control={
            <Switch
              checked={config.resume_on_startup}
              onChange={(e) =>
                setConfig((p) => p ? { ...p, resume_on_startup: e.target.checked } : p)
              }
            />
          }
          label={t('audio.resume_on_startup')}
        />
      )}
      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          {t('save', { ns: 'common' })}
        </Button>
      </Box>
      <Snackbar open={success} autoHideDuration={3000} onClose={() => setSuccess(false)} message={t('audio.save_success')} />
    </Box>
  );
};

// Default RFID config so fields are never empty if API returns partial/empty
const DEFAULT_RFID_CONFIG: RFIDConfig = {
  reader_type: 'PN532',
  interface: 'I2C',
  scan_interval_ms: 200,
  duplicate_suppression_ms: 2000,
};

// ============================================================================
// RFID Config Form
// ============================================================================

export const RFIDConfigForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const [config, setConfig] = useState<RFIDConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    configApi
      .getRfid()
      .then((data) => setConfig({ ...DEFAULT_RFID_CONFIG, ...data }))
      .catch(() => setError('Laden fehlgeschlagen'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await configApi.updateRfid(config);
      setConfig(updated);
      setSuccess(true);
    } catch {
      setError('Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  if (loading || !config) return null;

  return (
    <Box display="flex" flexDirection="column" gap={3} maxWidth={560}>
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
        size="small"
        fullWidth
        inputProps={{ min: 100, step: 100 }}
      />

      <TextField
        label={t('rfid.fields.duplicate_suppression_ms')}
        type="number"
        value={config.duplicate_suppression_ms}
        onChange={(e) =>
          setConfig((p) => p ? { ...p, duplicate_suppression_ms: parseInt(e.target.value) || 0 } : p)
        }
        size="small"
        fullWidth
        inputProps={{ min: 0, step: 100 }}
      />

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </Button>
      </Box>
      <Snackbar open={success} autoHideDuration={3000} onClose={() => setSuccess(false)} message={t('rfid.save_success')} />
    </Box>
  );
};

// ============================================================================
// General Settings (Language + central config)
// ============================================================================

export const GeneralSettingsForm: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const [general, setGeneral] = useState<GeneralConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    configApi.getGeneral().then(setGeneral).catch(() => setError('Laden fehlgeschlagen'));
  }, []);

  const handleLanguageChange = (lng: string) => {
    void i18n.changeLanguage(lng);
    localStorage.setItem('minabox-language', lng);
  };

  const handleSaveGeneral = async () => {
    if (!general) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await configApi.updateGeneral(general);
      setGeneral(updated);
      setSuccess(true);
    } catch {
      setError('Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box display="flex" flexDirection="column" gap={3} maxWidth={480}>
      <FormControl fullWidth size="small">
        <InputLabel>{t('general.language')}</InputLabel>
        <Select
          value={i18n.language.startsWith('de') ? 'de' : 'en'}
          label={t('general.language')}
          onChange={(e) => handleLanguageChange(e.target.value)}
        >
          <MenuItem value="de">{t('general.language_de')}</MenuItem>
          <MenuItem value="en">{t('general.language_en')}</MenuItem>
        </Select>
      </FormControl>

      {general && (
        <>
          <Typography variant="subtitle2" color="text.secondary">
            {t('general.title')} (zentral)
          </Typography>
          <TextField
            label={t('general.device_id')}
            value={general.minabox_device_id}
            onChange={(e) => setGeneral((p) => p ? { ...p, minabox_device_id: e.target.value } : p)}
            size="small"
            fullWidth
          />
          <FormControl fullWidth size="small">
            <InputLabel>{t('general.log_level')}</InputLabel>
            <Select
              value={general.log_level}
              label={t('general.log_level')}
              onChange={(e) => setGeneral((p) => p ? { ...p, log_level: e.target.value } : p)}
            >
              {['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].map((lvl) => (
                <MenuItem key={lvl} value={lvl}>{lvl}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label={t('general.mqtt_broker')}
            value={general.mqtt_broker}
            onChange={(e) => setGeneral((p) => p ? { ...p, mqtt_broker: e.target.value } : p)}
            size="small"
            fullWidth
          />
          <TextField
            label={t('general.mqtt_port')}
            type="number"
            value={general.mqtt_port}
            onChange={(e) => setGeneral((p) => p ? { ...p, mqtt_port: parseInt(e.target.value, 10) || 1883 } : p)}
            size="small"
            fullWidth
            inputProps={{ min: 1, max: 65535 }}
          />
          <FormControlLabel
            control={
              <Switch
                checked={general.disable_gpio}
                onChange={(e) => setGeneral((p) => p ? { ...p, disable_gpio: e.target.checked } : p)}
              />
            }
            label={t('general.disable_gpio')}
          />
          <Typography variant="caption" color="text.secondary">
            {t('general.restart_required')}
          </Typography>
          {error && <Alert severity="error">{error}</Alert>}
          <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSaveGeneral} disabled={saving}>
            {t('save', { ns: 'common' })}
          </Button>
        </>
      )}
      <Snackbar open={success} autoHideDuration={3000} onClose={() => setSuccess(false)} message={t('general.save_success')} />
    </Box>
  );
};
