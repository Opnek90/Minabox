import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Slider,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import SaveIcon from '@mui/icons-material/Save';
import UploadIcon from '@mui/icons-material/Upload';
import DeleteIcon from '@mui/icons-material/Delete';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import { systemApi } from '@/api/system';
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
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [config, setConfig] = useState<AudioConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    configApi
      .getAudio()
      .then(setConfig)
      .catch(() => setError(t('load_error', { defaultValue: 'Laden fehlgeschlagen' })))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (!config) return;
      const updated = await configApi.updateAudio(config);
      setConfig(updated);
      showSuccess(t('audio.save_success'));
    });

  if (loading || !config) return null;

  return (
    <Box display="flex" flexDirection="column" maxWidth={560} sx={{ gap: { xs: 2, sm: 3 } }}>
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
          min={0} max={100} step={5} marks
          onChange={(_, v) => setConfig((p) => p ? { ...p, max_volume: v as number } : p)}
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
          step={5} marks
          onChange={(_, v) => setConfig((p) => p ? { ...p, default_volume: v as number } : p)}
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
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </Button>
      </Box>
    </Box>
  );
};


// ============================================================================
// RFID Config Form
// ============================================================================

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
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </Button>
      </Box>
    </Box>
  );
};


// ============================================================================
// Design Settings
// ============================================================================

export const DesignSettingsForm: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const { mode, colorPreset, toggleMode, setColorPreset } = useThemeContext();
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [logoUploading, setLogoUploading] = useState(false);
  const logoInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch('/static/logo.png', { method: 'HEAD' })
      .then((r) => { if (r.ok) setLogoUrl('/static/logo.png?t=' + Date.now()); })
      .catch(() => null);
  }, []);

  const handleLogoUpload = async (file: File) => {
    setLogoUploading(true);
    try {
      await configApi.uploadLogo(file);
      setLogoUrl('/static/logo.png?t=' + Date.now());
      showSuccess(t('general.logo_upload_success', { defaultValue: 'Logo hochgeladen' }));
    } catch {
      showError(t('general.logo_upload_error', { defaultValue: 'Logo-Upload fehlgeschlagen' }));
    } finally {
      setLogoUploading(false);
    }
  };

  const handleLogoDelete = async () => {
    try {
      await configApi.deleteLogo();
      setLogoUrl(null);
      showSuccess(t('general.logo_delete_success', { defaultValue: 'Logo gelöscht' }));
    } catch {
      showError(t('general.logo_delete_error', { defaultValue: 'Logo konnte nicht gelöscht werden' }));
    }
  };

  const handleLanguageChange = (lng: string) => {
    void i18n.changeLanguage(lng);
    localStorage.setItem('minabox-language', lng);
  };

  return (
    <Box display="flex" flexDirection="column" maxWidth={480} sx={{ gap: { xs: 2, sm: 3 } }}>
      <Box>
        <Typography variant="subtitle2" gutterBottom>{t('general.logo')}</Typography>
        <Box display="flex" alignItems="center" gap={2} flexWrap="wrap">
          {logoUrl && (
            <Box
              component="img"
              src={logoUrl}
              alt="Logo"
              sx={{
                height: 48,
                maxWidth: 160,
                objectFit: 'contain',
                borderRadius: 1,
                border: '1px solid',
                borderColor: 'divider',
              }}
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

      <Typography variant="subtitle2" color="text.secondary">
        {t('general.appearance')}
      </Typography>

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
                  boxShadow:
                    colorPreset === key
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
    </Box>
  );
};


// ============================================================================
// General Settings
// ============================================================================

export const GeneralSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const { saving, error, setError, run } = useFormState();

  const [general, setGeneral] = useState<GeneralConfig | null>(null);
  const [audioPath, setAudioPath] = useState<string | null>(null);
  const [newAudioPath, setNewAudioPath] = useState('');
  const [audioPathSaving, setAudioPathSaving] = useState(false);
  const [audioPathError, setAudioPathError] = useState<string | null>(null);
  const [mediaPathDialogOpen, setMediaPathDialogOpen] = useState(false);
  const [moveProgressOpen, setMoveProgressOpen] = useState(false);
  const [moveProgress, setMoveProgress] = useState<{
    status: string;
    total: number;
    current: number;
    error: string | null;
  }>({ status: 'idle', total: 0, current: 0, error: null });

  useEffect(() => {
    configApi.getGeneral().then(setGeneral).catch(() => setError('Laden fehlgeschlagen'));
    systemApi.getAudioPath().then((r) => setAudioPath(r.path)).catch(() => setAudioPath(null));
  }, []);

  const extractDetail = (err: unknown): string | null =>
    err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? null
      : null;

  const saveAudioPathAndMaybeRestart = async (doRestart: boolean) => {
    const path = newAudioPath.trim();
    if (!path) return;
    setMediaPathDialogOpen(false);
    setAudioPathSaving(true);
    setAudioPathError(null);
    try {
      await systemApi.putAudioPath(path);
      setAudioPath(path);
      setNewAudioPath('');
      if (doRestart) {
        showSuccess(t('general.media_path_success_restart'));
        await systemApi.restart();
      } else {
        showSuccess(t('general.media_path_success'));
      }
    } catch (err) {
      setAudioPathError(extractDetail(err) ?? t('general.media_path_error'));
    } finally {
      setAudioPathSaving(false);
    }
  };

  const runMoveAndRestart = async () => {
    const path = newAudioPath.trim();
    const source = audioPath;
    if (!path || !source) return;
    setMediaPathDialogOpen(false);
    setAudioPathSaving(true);
    setAudioPathError(null);
    setMoveProgressOpen(true);
    setMoveProgress({ status: 'running', total: 0, current: 0, error: null });
    try {
      await systemApi.moveAudio(source, path);
      const pollId = setInterval(async () => {
        try {
          const st = await systemApi.getMoveStatus();
          setMoveProgress({ status: st.status, total: st.total, current: st.current, error: st.error ?? null });
          if (st.status === 'done') {
            clearInterval(pollId);
            try {
              await systemApi.putAudioPath(path);
              setAudioPath(path);
              setNewAudioPath('');
              setMoveProgress((p) => ({ ...p, status: 'rebooting' }));
              await systemApi.rebootHost();
              setMoveProgressOpen(false);
              showSuccess(t('general.media_path_success_moved'));
            } catch (err) {
              const detail = extractDetail(err);
              setMoveProgress((p) => ({
                ...p,
                status: 'error',
                error: detail
                  ? `${t('general.media_path_reboot_failed')}: ${detail}`
                  : t('general.media_path_reboot_failed'),
              }));
            }
            setAudioPathSaving(false);
          } else if (st.status === 'error') {
            clearInterval(pollId);
            setAudioPathSaving(false);
          }
        } catch {
          // poll errors are non-fatal, keep polling
        }
      }, 1000);
    } catch (err) {
      setMoveProgress({
        status: 'error',
        total: 0,
        current: 0,
        error: extractDetail(err) ?? t('general.media_path_move_error'),
      });
      setAudioPathSaving(false);
    }
  };

  const handleSaveGeneral = () =>
    run(async () => {
      if (!general) return;
      const updated = await configApi.updateGeneral(general);
      setGeneral(updated);
      showSuccess(t('general.save_success'));
    });

  const handleCopyPath = async () => {
    if (!audioPath) return;
    try {
      await navigator.clipboard.writeText(audioPath);
      showSuccess(t('general.media_path_copied'));
    } catch {
      showError(t('general.media_path_copy_error', { defaultValue: 'Kopieren fehlgeschlagen' }));
    }
  };

  return (
    <Box display="flex" flexDirection="column" maxWidth={480} sx={{ gap: { xs: 2, sm: 3 } }}>

      {/* ─── Medienverzeichnis ─────────────────────────────────── */}
      <Typography variant="subtitle2" color="text.secondary">
        {t('general.media_path_title')}
      </Typography>
      {audioPath != null && (
        <Box display="flex" alignItems="center" gap={0.5} flexWrap="wrap">
          <Typography variant="body2" color="text.secondary">
            {t('general.media_path_current')}: <strong>{audioPath}</strong>
          </Typography>
          <Tooltip title={t('general.media_path_copy')}>
            <IconButton size="small" onClick={handleCopyPath} aria-label={t('general.media_path_copy')}>
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      )}
      <TextField
        label={t('general.media_path_new')}
        value={newAudioPath}
        onChange={(e) => setNewAudioPath(e.target.value)}
        placeholder="/media/usb0/music"
        size="small"
        fullWidth
        helperText={t('general.media_path_restart_hint')}
      />
      <Button
        variant="outlined"
        startIcon={<SaveIcon />}
        onClick={() => setMediaPathDialogOpen(true)}
        disabled={audioPathSaving || !newAudioPath.trim()}
      >
        {t('general.media_path_save')}
      </Button>
      {audioPathError && <Alert severity="error">{audioPathError}</Alert>}

      {/* Media Path Dialog */}
      <Dialog open={mediaPathDialogOpen} onClose={() => setMediaPathDialogOpen(false)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('general.media_path_restart_dialog_title')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>{t('general.media_path_restart_dialog_message')}</DialogContentText>
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap', gap: 0.5 }}>
          <Button onClick={() => setMediaPathDialogOpen(false)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button onClick={() => saveAudioPathAndMaybeRestart(false)} disabled={audioPathSaving}>
            {t('general.media_path_save_only')}
          </Button>
          {audioPath && (
            <Button onClick={runMoveAndRestart} variant="contained" disabled={audioPathSaving}>
              {t('general.media_path_move_and_restart')}
            </Button>
          )}
          <Button onClick={() => saveAudioPathAndMaybeRestart(true)} variant="contained" disabled={audioPathSaving}>
            {t('general.media_path_save_and_restart')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Move Progress Dialog */}
      <Dialog
        open={moveProgressOpen}
        onClose={() => {}}
        disableEscapeKeyDown
        maxWidth="sm"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3, overflow: 'hidden' } }}
      >
        <DialogTitle component="div" sx={{ fontSize: '1.25rem', fontWeight: 600, pb: 0, pt: 2.5, px: 3 }}>
          {moveProgress.status === 'rebooting'
            ? t('general.media_path_move_rebooting_title')
            : moveProgress.status === 'error'
              ? t('general.media_path_move_error')
              : t('general.media_path_move_progress_title')}
        </DialogTitle>
        <DialogContent sx={{ px: 3, pt: 1.5, pb: 3 }}>
          {moveProgress.status === 'error' ? (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                {t('general.media_path_move_error_detail')}
              </Typography>
              <Alert severity="error" variant="outlined" sx={{ borderRadius: 2 }}>
                {moveProgress.error}
              </Alert>
            </Box>
          ) : (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {moveProgress.status === 'rebooting'
                  ? t('general.media_path_move_rebooting_subtitle')
                  : t('general.media_path_move_progress_subtitle')}
              </Typography>
              <Box sx={{ p: 2, borderRadius: 2, bgcolor: 'action.hover', border: '1px solid', borderColor: 'divider' }}>
                <LinearProgress
                  variant={moveProgress.total > 0 ? 'determinate' : 'indeterminate'}
                  value={moveProgress.total > 0 ? (100 * moveProgress.current) / moveProgress.total : 0}
                  sx={{
                    height: 8,
                    borderRadius: 1,
                    mb: moveProgress.total > 0 ? 1.5 : 0,
                    '& .MuiLinearProgress-bar': { borderRadius: 1 },
                  }}
                />
                {moveProgress.total > 0 && (
                  <Typography variant="caption" color="text.secondary">
                    {t('general.media_path_move_files_count', {
                      current: moveProgress.current,
                      total: moveProgress.total,
                    })}
                  </Typography>
                )}
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, pt: 0 }}>
          {moveProgress.status === 'error' && (
            <Button variant="contained" onClick={() => setMoveProgressOpen(false)}>
              {t('close', { ns: 'common' })}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      <Divider />

      {/* ─── Sleep Timer ───────────────────────────────────────── */}
      <Typography variant="subtitle2" color="text.secondary">
        {t('general.sleep_timer')}
      </Typography>
      {general && (
        <TextField
          label={t('general.sleep_timer_minutes')}
          type="number"
          value={general.sleep_timer_minutes ?? 30}
          onChange={(e) =>
            setGeneral((p) =>
              p ? { ...p, sleep_timer_minutes: Math.max(1, parseInt(e.target.value, 10) || 30) } : p
            )
          }
          size="small"
          fullWidth
          inputProps={{ min: 1, max: 480 }}
          helperText={t('general.sleep_timer_minutes_hint')}
        />
      )}

      <Divider />

      {/* ─── Allgemein ─────────────────────────────────────────── */}
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
            onChange={(e) =>
              setGeneral((p) => p ? { ...p, mqtt_port: parseInt(e.target.value, 10) || 1883 } : p)
            }
            size="small"
            fullWidth
            inputProps={{ min: 1, max: 65535 }}
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
    </Box>
  );
};
