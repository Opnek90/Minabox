import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Divider,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Snackbar,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import UploadIcon from '@mui/icons-material/Upload';
import DeleteIcon from '@mui/icons-material/Delete';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import { useTranslation } from 'react-i18next';
import { configApi } from '@/api/config';
import { useThemeContext, COLOR_PRESETS, type ColorPresetKey } from '@/contexts/ThemeContext';
import type { AudioConfig, RFIDConfig, GeneralConfig } from '@/types/api';

const COLOR_PRESET_LABELS: Record<ColorPresetKey, string> = {
  orange: 'Orange',
  blue: 'Blue',
  green: 'Green',
  purple: 'Purple',
  red: 'Red',
};

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
  const { mode, colorPreset, toggleMode, setColorPreset } = useThemeContext();
  const [general, setGeneral] = useState<GeneralConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [logoUploading, setLogoUploading] = useState(false);
  const logoInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    configApi.getGeneral().then(setGeneral).catch(() => setError('Laden fehlgeschlagen'));
    // Check if logo exists
    fetch('/static/logo.png', { method: 'HEAD' })
      .then((r) => { if (r.ok) setLogoUrl('/static/logo.png?t=' + Date.now()); })
      .catch(() => null);
  }, []);

  const handleLogoUpload = async (file: File) => {
    setLogoUploading(true);
    try {
      await configApi.uploadLogo(file);
      setLogoUrl('/static/logo.png?t=' + Date.now());
    } catch {
      setError('Logo upload failed');
    } finally {
      setLogoUploading(false);
    }
  };

  const handleLogoDelete = async () => {
    try {
      await configApi.deleteLogo();
      setLogoUrl(null);
    } catch {
      setError('Logo deletion failed');
    }
  };

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
      {/* Logo Upload */}
      <Box>
        <Typography variant="subtitle2" gutterBottom>{t('general.logo')}</Typography>
        <Box display="flex" alignItems="center" gap={2} flexWrap="wrap">
          {logoUrl && (
            <Box
              component="img"
              src={logoUrl}
              alt="Logo"
              sx={{ height: 48, maxWidth: 160, objectFit: 'contain', borderRadius: 1, border: '1px solid', borderColor: 'divider' }}
            />
          )}
          <input
            ref={logoInputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleLogoUpload(f); }}
          />
          <Button
            variant="outlined"
            size="small"
            startIcon={<UploadIcon />}
            onClick={() => logoInputRef.current?.click()}
            disabled={logoUploading}
          >
            {t('general.logo_upload')}
          </Button>
          {logoUrl && (
            <Button
              variant="outlined"
              size="small"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={handleLogoDelete}
            >
              {t('general.logo_delete')}
            </Button>
          )}
        </Box>
      </Box>

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

      <Divider />

      {/* ─── Appearance ─────────────────────────────────────────── */}
      <Typography variant="subtitle2" color="text.secondary">
        {t('general.appearance')}
      </Typography>

      {/* Dark / Light toggle */}
      <Box display="flex" alignItems="center" justifyContent="space-between">
        <Typography variant="body2">{t('general.color_mode')}</Typography>
        <ToggleButtonGroup
          value={mode}
          exclusive
          onChange={(_, v) => { if (v) toggleMode(); }}
          size="small"
        >
          <ToggleButton value="light">
            <LightModeIcon fontSize="small" sx={{ mr: 0.5 }} />
            {t('general.theme_light')}
          </ToggleButton>
          <ToggleButton value="dark">
            <DarkModeIcon fontSize="small" sx={{ mr: 0.5 }} />
            {t('general.theme_dark')}
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Accent color */}
      <Box>
        <Typography variant="body2" gutterBottom>{t('general.accent_color')}</Typography>
        <Box display="flex" gap={1.5} flexWrap="wrap">
          {(Object.keys(COLOR_PRESETS) as ColorPresetKey[]).map((key) => (
            <Tooltip key={key} title={COLOR_PRESET_LABELS[key]}>
              <Box
                onClick={() => setColorPreset(key)}
                sx={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  bgcolor: COLOR_PRESETS[key].main,
                  cursor: 'pointer',
                  border: colorPreset === key ? '3px solid white' : '3px solid transparent',
                  boxShadow: colorPreset === key
                    ? `0 0 0 2px ${COLOR_PRESETS[key].main}`
                    : '0 1px 3px rgba(0,0,0,0.3)',
                  transition: 'transform 0.15s',
                  '&:hover': { transform: 'scale(1.15)' },
                }}
              />
            </Tooltip>
          ))}
        </Box>
      </Box>

      <Divider />

      {/* ─── Sleep Timer ──────────────────────────────────────────── */}
      <Typography variant="subtitle2" color="text.secondary">
        {t('general.sleep_timer')}
      </Typography>
      {general && (
        <TextField
          label={t('general.sleep_timer_minutes')}
          type="number"
          value={general.sleep_timer_minutes ?? 30}
          onChange={(e) => setGeneral((p) => p ? { ...p, sleep_timer_minutes: Math.max(1, parseInt(e.target.value, 10) || 30) } : p)}
          size="small"
          fullWidth
          inputProps={{ min: 1, max: 480 }}
          helperText={t('general.sleep_timer_minutes_hint')}
        />
      )}

      <Divider />

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
