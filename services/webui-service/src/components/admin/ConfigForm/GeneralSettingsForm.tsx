import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import { systemApi } from '@/api/system';
import type { GeneralConfig, AllowedUsageTimeSlot } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';

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
    configApi.getGeneral().then((data) => {
      const g = data as GeneralConfig;
      const times = Array.isArray(g.allowed_usage_times) ? g.allowed_usage_times : [];
      const slots: AllowedUsageTimeSlot[] = [];
      for (let wd = 0; wd <= 6; wd++) {
        const existing = times.find((s) => s.weekday === wd);
        slots.push(existing ?? { weekday: wd, start: '07:00', end: '19:00' });
      }
      setGeneral({ ...g, allowed_usage_times: slots });
    }).catch(() => setError('Laden fehlgeschlagen'));
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
    <Box display="flex" flexDirection="column" maxWidth={560} sx={{ gap: { xs: 2, sm: 3 } }}>
      <Typography variant="overline" color="text.secondary">
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
      <ActionButton
        actionType="secondary"
        startIcon={<SaveIcon />}
        onClick={() => setMediaPathDialogOpen(true)}
        disabled={audioPathSaving || !newAudioPath.trim()}
      >
        {t('general.media_path_save')}
      </ActionButton>
      {audioPathError && <Alert severity="error">{audioPathError}</Alert>}

      <Dialog open={mediaPathDialogOpen} onClose={() => setMediaPathDialogOpen(false)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('general.media_path_restart_dialog_title')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>{t('general.media_path_restart_dialog_message')}</DialogContentText>
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap', gap: 0.5 }}>
          <ActionButton actionType="secondary" onClick={() => setMediaPathDialogOpen(false)}>
            {t('cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="secondary"
            onClick={() => saveAudioPathAndMaybeRestart(false)}
            disabled={audioPathSaving}
          >
            {t('general.media_path_save_only')}
          </ActionButton>
          {audioPath && (
            <ActionButton
              actionType="primary"
              onClick={runMoveAndRestart}
              disabled={audioPathSaving}
            >
              {t('general.media_path_move_and_restart')}
            </ActionButton>
          )}
          <ActionButton
            actionType="primary"
            onClick={() => saveAudioPathAndMaybeRestart(true)}
            disabled={audioPathSaving}
          >
            {t('general.media_path_save_and_restart')}
          </ActionButton>
        </DialogActions>
      </Dialog>

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
            <ActionButton actionType="primary" onClick={() => setMoveProgressOpen(false)}>
              {t('actions.close', { ns: 'common' })}
            </ActionButton>
          )}
        </DialogActions>
      </Dialog>

      <Divider />

      {general && (
        <>
          <Typography variant="overline" color="text.secondary">
            {t('general.connection')}
          </Typography>
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
          <ActionButton
            actionType="primary"
            startIcon={<SaveIcon />}
            onClick={handleSaveGeneral}
            disabled={saving}
          >
            {t('save', { ns: 'common' })}
          </ActionButton>
        </>
      )}
    </Box>
  );
};
