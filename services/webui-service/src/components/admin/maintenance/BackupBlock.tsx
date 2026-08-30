import React, { useState } from 'react';
import {
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Typography,
} from '@mui/material';
import BackupIcon from '@mui/icons-material/Backup';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';

/** Datenbank, Konfiguration und Zustand als ZIP - herunterladen und zurueckspielen. */
export const BackupBlock: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restorePending, setRestorePending] = useState(false);

  const handleDownload = async () => {
    try {
      const blob = await systemApi.downloadBackup();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `minabox-backup-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      showSuccess(t('system.backup_download_success'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    }
  };

  const closeRestore = () => {
    setRestoreDialogOpen(false);
    setRestoreFile(null);
  };

  const handleRestore = async () => {
    if (!restoreFile) return;
    setRestorePending(true);
    setRestoreDialogOpen(false);
    try {
      await systemApi.restoreBackup(restoreFile);
      setRestoreFile(null);
      showSuccess(t('system.backup_restore_success'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setRestorePending(false);
    }
  };

  return (
    <SettingsBlock title={t('system.backup_title')}>
      <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
        <ActionButton
          actionType="secondary"
          startIcon={<CloudDownloadIcon />}
          onClick={handleDownload}
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
      </Box>

      <Dialog open={restoreDialogOpen} onClose={closeRestore}>
        <DialogTitle>{t('system.backup_restore')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {t('system.backup_restore_confirm')}
          </DialogContentText>
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
          {restoreFile && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {restoreFile.name}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={closeRestore}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleRestore} disabled={!restoreFile}>
            {t('system.backup_restore')}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </SettingsBlock>
  );
};
