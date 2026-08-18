import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  TextField,
  Typography,
} from '@mui/material';
import BackupIcon from '@mui/icons-material/Backup';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import ComputerIcon from '@mui/icons-material/Computer';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import RestoreIcon from '@mui/icons-material/Restore';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi, type VersionResponse } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

export const SystemMaintenanceSection: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [version, setVersion] = useState<VersionResponse | null>(null);
  const [restartDialogOpen, setRestartDialogOpen] = useState(false);
  const [rebootDialogOpen, setRebootDialogOpen] = useState(false);
  const [shutdownDialogOpen, setShutdownDialogOpen] = useState(false);
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restorePending, setRestorePending] = useState(false);
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [updateOsDialogOpen, setUpdateOsDialogOpen] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [updatingOs, setUpdatingOs] = useState(false);
  const [dockerPruneDialogOpen, setDockerPruneDialogOpen] = useState(false);
  const [dockerPrunePending, setDockerPrunePending] = useState(false);
  const [updateOsLogOpen, setUpdateOsLogOpen] = useState(false);
  const [updateOsLog, setUpdateOsLog] = useState('');
  const [updateOsLogRunning, setUpdateOsLogRunning] = useState(false);
  const [factoryResetDialogOpen, setFactoryResetDialogOpen] = useState(false);
  const [factoryResetDeleteAudio, setFactoryResetDeleteAudio] = useState(false);
  const [factoryResetConfirmText, setFactoryResetConfirmText] = useState('');
  const [factoryResetPending, setFactoryResetPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadVersion = useCallback(async () => {
    setError(null);
    try {
      const ver = await systemApi.getVersion().catch(() => null);
      setVersion(ver ?? null);
    } catch {
      setError('Version konnte nicht geladen werden');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadVersion(); }, [loadVersion]);

  const fetchUpdateOsLog = useCallback(async () => {
    try {
      const data = await systemApi.getUpdateOsLog();
      setUpdateOsLog(data.log ?? '');
      setUpdateOsLogRunning(data.running ?? false);
    } catch {
      setUpdateOsLogRunning(false);
    }
  }, []);

  useEffect(() => {
    if (!updateOsLogOpen) return;
    fetchUpdateOsLog();
    const interval = setInterval(fetchUpdateOsLog, 2000);
    return () => clearInterval(interval);
  }, [updateOsLogOpen, fetchUpdateOsLog]);

  const handleRestart = async () => {
    setRestartDialogOpen(false);
    try { await systemApi.restart(); } catch { /* restarting */ }
  };

  const handleReboot = async () => {
    setRebootDialogOpen(false);
    try { await systemApi.rebootHost(); } catch { /* connection drops */ }
  };

  const handleShutdown = async () => {
    setShutdownDialogOpen(false);
    try { await systemApi.shutdownHost(); } catch { /* connection drops */ }
  };

  const handleDownloadBackup = async () => {
    try {
      const blob = await systemApi.downloadBackup();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `minabox-backup-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      showSuccess(t('system.backup_restore_success'));
    } catch {
      showError(t('system.logs_unavailable'));
    }
  };

  const handleRestoreBackup = async () => {
    if (!restoreFile) return;
    setRestorePending(true);
    setRestoreDialogOpen(false);
    try {
      await systemApi.restoreBackup(restoreFile);
      setRestoreFile(null);
      showSuccess(t('system.backup_restore_success'));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setRestorePending(false);
    }
  };

  const handleUpdateMinabox = async () => {
    setUpdateDialogOpen(false);
    setUpdating(true);
    try {
      await systemApi.updateMinabox();
      showSuccess(t('system.update_success'));
      const ver = await systemApi.getVersion();
      setVersion(ver ?? null);
    } catch (err: unknown) {
      const ax = err && typeof err === 'object' && 'response' in err ? (err as { response?: { data?: { detail?: string } } }).response : undefined;
      const detail = ax?.data?.detail;
      showError(typeof detail === 'string' && detail ? detail : t('system.logs_unavailable'));
    } finally {
      setUpdating(false);
    }
  };

  const handleUpdateOs = async () => {
    setUpdateOsDialogOpen(false);
    setUpdatingOs(true);
    try {
      await systemApi.updateOs();
      showSuccess(t('system.update_os_success'));
      setUpdateOsLogOpen(true);
    } catch (err: unknown) {
      const ax = err && typeof err === 'object' && 'response' in err ? (err as { response?: { data?: { detail?: string } } }).response : undefined;
      const detail = ax?.data?.detail;
      showError(typeof detail === 'string' && detail ? detail : t('system.logs_unavailable'));
    } finally {
      setUpdatingOs(false);
    }
  };

  const handleDockerPrune = async () => {
    setDockerPruneDialogOpen(false);
    setDockerPrunePending(true);
    try {
      await systemApi.dockerPrune();
      showSuccess(t('system.cleanup_success'));
    } catch (err: unknown) {
      const ax = err && typeof err === 'object' && 'response' in err ? (err as { response?: { data?: { detail?: string } } }).response : undefined;
      const detail = ax?.data?.detail;
      showError(typeof detail === 'string' && detail ? detail : t('system.logs_unavailable'));
    } finally {
      setDockerPrunePending(false);
    }
  };

  const handleFactoryReset = async () => {
    const confirmWord = t('system.factory_reset_confirm_word');
    if (factoryResetConfirmText.trim() !== confirmWord) return;
    setFactoryResetDialogOpen(false);
    setFactoryResetConfirmText('');
    setFactoryResetPending(true);
    try {
      await systemApi.factoryReset(factoryResetDeleteAudio);
      showSuccess(t('system.factory_reset_success'));
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setFactoryResetPending(false);
    }
  };

  const factoryResetConfirmValid = factoryResetConfirmText.trim() === t('system.factory_reset_confirm_word');

  if (loading && !version) return null;

  return (
    <Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Sicherung ───────────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.backup_title')}>
        <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
          <ActionButton
            actionType="secondary"
            startIcon={<CloudDownloadIcon />}
            onClick={handleDownloadBackup}
          >
            {t('system.backup_download')}
          </ActionButton>
          <ActionButton
            actionType="secondary"
            startIcon={<BackupIcon />}
            onClick={() => setRestoreDialogOpen(true)}
            disabled={restorePending}
            loading={restorePending}
          >
            {t('system.backup_restore')}
          </ActionButton>
          <Typography component="span" variant="caption" color="text.secondary">
            {restoreFile ? restoreFile.name : t('system.backup_restore_select')}
          </Typography>
        </Box>
      </SettingsBlock>

      {/* ── Wartung ──────────────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.maintenance_title')}>
        <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
          <Typography variant="body2">
            {t('system.version')}: {version?.current_version ?? version?.current_commit ?? '–'}
          </Typography>
          {version?.update_available && (
            <>
              <Chip label={t('system.update_available')} color="primary" size="small" />
              <ActionButton
                actionType="primary"
                onClick={() => setUpdateDialogOpen(true)}
                disabled={updating}
                loading={updating}
              >
                {t('system.update_minabox')}
              </ActionButton>
            </>
          )}
          <ActionButton
            actionType="secondary"
            onClick={() => setUpdateOsDialogOpen(true)}
            disabled={updatingOs}
            loading={updatingOs}
          >
            {t('system.update_os')}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={() => setDockerPruneDialogOpen(true)}
            disabled={dockerPrunePending}
          >
            {t('system.cleanup')}
          </ActionButton>
        </Box>
      </SettingsBlock>

      {/* ── Neustart ─────────────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.restart_group')}>
        <Box display="flex" flexWrap="wrap" gap={1}>
          <ActionButton actionType="secondary" startIcon={<RestartAltIcon />} onClick={() => setRestartDialogOpen(true)}>
            {t('system.restart')}
          </ActionButton>
          <ActionButton actionType="secondary" startIcon={<ComputerIcon />} onClick={() => setRebootDialogOpen(true)}>
            {t('system.reboot')}
          </ActionButton>
          <ActionButton actionType="destructive" startIcon={<PowerSettingsNewIcon />} onClick={() => setShutdownDialogOpen(true)}>
            {t('system.shutdown')}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            startIcon={<RestoreIcon />}
            onClick={() => { setFactoryResetDialogOpen(true); setFactoryResetConfirmText(''); }}
            disabled={factoryResetPending}
          >
            {t('system.factory_reset')}
          </ActionButton>
        </Box>
      </SettingsBlock>

      {/* ── Dialogs ─────────────────────────────────────────────────────────── */}
      <Dialog open={restartDialogOpen} onClose={() => setRestartDialogOpen(false)}>
        <DialogTitle>{t('system.restart')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.restart_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setRestartDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleRestart}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={rebootDialogOpen} onClose={() => setRebootDialogOpen(false)}>
        <DialogTitle>{t('system.reboot')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.reboot_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setRebootDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleReboot}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={shutdownDialogOpen} onClose={() => setShutdownDialogOpen(false)}>
        <DialogTitle>{t('system.shutdown')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.shutdown_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setShutdownDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleShutdown}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={factoryResetDialogOpen} onClose={() => { setFactoryResetDialogOpen(false); setFactoryResetConfirmText(''); }}>
        <DialogTitle>{t('system.factory_reset')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('system.factory_reset_warning')}</DialogContentText>
          <FormControlLabel control={<Checkbox checked={factoryResetDeleteAudio} onChange={(_, c) => setFactoryResetDeleteAudio(c)} color="primary" />} label={t('system.factory_reset_delete_audio')} sx={{ display: 'block', mb: 2 }} />
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{t('system.factory_reset_type_prompt')}</Typography>
          <TextField fullWidth size="small" value={factoryResetConfirmText} onChange={(e) => setFactoryResetConfirmText(e.target.value)} placeholder={t('system.factory_reset_confirm_word')} autoComplete="off" />
        </DialogContent>
        <DialogActions>
          <ActionButton
            actionType="secondary"
            onClick={() => { setFactoryResetDialogOpen(false); setFactoryResetConfirmText(''); }}
          >
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={handleFactoryReset}
            disabled={!factoryResetConfirmValid || factoryResetPending}
          >
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={restoreDialogOpen} onClose={() => { setRestoreDialogOpen(false); setRestoreFile(null); }}>
        <DialogTitle>{t('system.backup_restore')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('system.backup_restore_confirm')}</DialogContentText>
          <Box
            component="label"
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: 40,
              px: 2.5,
              py: 0.75,
              fontSize: '0.9rem',
              fontWeight: 600,
              letterSpacing: 0,
              border: '1px solid',
              borderColor: 'primary.main',
              color: 'primary.main',
              borderRadius: 1,
              cursor: 'pointer',
              width: '100%',
              '&:hover': { bgcolor: 'action.hover' },
            }}
          >
            {t('system.backup_restore_select')}
            <input
              type="file"
              hidden
              accept=".zip"
              onChange={(e) => setRestoreFile(e.target.files?.[0] ?? null)}
            />
          </Box>
          {restoreFile && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{restoreFile.name}</Typography>}
        </DialogContent>
        <DialogActions>
          <ActionButton
            actionType="secondary"
            onClick={() => { setRestoreDialogOpen(false); setRestoreFile(null); }}
          >
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={handleRestoreBackup}
            disabled={!restoreFile}
          >
            {t('system.backup_restore')}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={updateDialogOpen} onClose={() => setUpdateDialogOpen(false)}>
        <DialogTitle>{t('system.update_minabox')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.update_minabox_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setUpdateDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="primary" onClick={handleUpdateMinabox}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={updateOsDialogOpen} onClose={() => setUpdateOsDialogOpen(false)}>
        <DialogTitle>{t('system.update_os')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.update_os_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setUpdateOsDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="primary"
            onClick={handleUpdateOs}
            disabled={updatingOs}
          >
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={updateOsLogOpen} onClose={() => setUpdateOsLogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>{t('system.update_os_log_title')}</DialogTitle>
        <DialogContent>
          {updateOsLogRunning && <Typography variant="caption" color="primary" display="block" sx={{ mb: 1 }}>{t('system.update_os_log_running')}</Typography>}
          <Box component="pre" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.75rem', maxHeight: 400, overflow: 'auto', p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
            {updateOsLog || t('system.update_os_log_empty')}
          </Box>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setUpdateOsLogOpen(false)}>
            {t('actions.close', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={dockerPruneDialogOpen} onClose={() => setDockerPruneDialogOpen(false)}>
        <DialogTitle>{t('system.cleanup')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.cleanup_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setDockerPruneDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={handleDockerPrune}
            disabled={dockerPrunePending}
          >
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
