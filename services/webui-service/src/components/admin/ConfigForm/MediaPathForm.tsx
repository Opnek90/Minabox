import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  LinearProgress,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';

/** Wo die Musik auf dem Gerät liegt – inklusive Umzug auf einen anderen Datenträger. */
export const MediaPathForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
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
    <Box display="flex" flexDirection="column" sx={{ gap: { xs: 2, sm: 3 } }}>
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
      <Box>
        <ActionButton
          actionType="secondary"
          startIcon={<SaveIcon />}
          onClick={() => setMediaPathDialogOpen(true)}
          disabled={audioPathSaving || !newAudioPath.trim()}
        >
          {t('general.media_path_save')}
        </ActionButton>
      </Box>
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
    </Box>
  );
};
