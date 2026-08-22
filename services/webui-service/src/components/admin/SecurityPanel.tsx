import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import LockResetIcon from '@mui/icons-material/LockReset';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { AuthSection } from '@/components/admin/AuthSection';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';

export const SecurityPanel: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [sshStatus, setSshStatus] = useState<{ enabled: boolean; active: boolean } | null>(null);
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState('pi');
  const [passwordNew, setPasswordNew] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordConfirmDialogOpen, setPasswordConfirmDialogOpen] = useState(false);

  const loadSsh = useCallback(async () => {
    try {
      const st = await systemApi.getSshStatus();
      setSshStatus(st);
    } catch {
      setSshStatus(null);
    }
  }, []);

  useEffect(() => {
    loadSsh();
  }, [loadSsh]);

  const handleOpenPasswordConfirm = () => {
    if (passwordNew !== passwordConfirm || passwordNew.length < 8) return;
    setPasswordConfirmDialogOpen(true);
  };

  const handleApplyPassword = async () => {
    setPasswordConfirmDialogOpen(false);
    setPasswordSaving(true);
    setPasswordDialogOpen(false);
    try {
      await systemApi.setPassword(passwordUser, passwordNew);
      setPasswordNew('');
      setPasswordConfirm('');
      showSuccess(t('system.password_apply'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleSshToggle = async (enable: boolean) => {
    try {
      const next = await systemApi.setSshToggle(enable);
      setSshStatus({ enabled: next.enabled, active: next.active });
    } catch (err: unknown) {
      showError(translateApiError(t, i18n, err));
    }
  };

  return (
    <Box>
      <AuthSection />

      <SettingsBlock title={t('system.security_title')}>
        {sshStatus != null && (
          <>
            <FormControlLabel
              control={
                <Switch
                  checked={sshStatus.enabled || sshStatus.active}
                  onChange={(_, checked) => handleSshToggle(checked)}
                  color="primary"
                />
              }
              label={t('system.ssh_toggle')}
              sx={{ mt: 1 }}
            />
            <Typography variant="caption" display="block" color="text.secondary" sx={{ mb: 1 }}>
              {t('system.ssh_toggle_hint')}
            </Typography>
          </>
        )}
        <Box display="flex" flexWrap="wrap" gap={1}>
          <ActionButton
            actionType="secondary"
            startIcon={<LockResetIcon />}
            onClick={() => setPasswordDialogOpen(true)}
          >
            {t('system.password_change')}
          </ActionButton>
        </Box>
      </SettingsBlock>

      <ResponsiveDialog open={passwordDialogOpen} onClose={() => { setPasswordDialogOpen(false); setPasswordNew(''); setPasswordConfirm(''); }}>
        <DialogTitle>{t('system.password_change')}</DialogTitle>
        <DialogContent>
          <TextField autoFocus fullWidth margin="dense" label={t('system.password_user')} value={passwordUser} onChange={(e) => setPasswordUser(e.target.value)} sx={{ mt: 1 }} />
          <TextField fullWidth margin="dense" type="password" label={t('system.password_new')} value={passwordNew} onChange={(e) => setPasswordNew(e.target.value)} />
          <TextField fullWidth margin="dense" type="password" label={t('system.password_confirm')} value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <ActionButton
            actionType="secondary"
            onClick={() => { setPasswordDialogOpen(false); setPasswordNew(''); setPasswordConfirm(''); }}
          >
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="primary"
            onClick={handleOpenPasswordConfirm}
            disabled={passwordSaving || passwordNew.length < 8 || passwordNew !== passwordConfirm}
          >
            {t('system.password_apply')}
          </ActionButton>
        </DialogActions>
      </ResponsiveDialog>

      <Dialog open={passwordConfirmDialogOpen} onClose={() => setPasswordConfirmDialogOpen(false)}>
        <DialogTitle>{t('system.password_apply')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('system.password_confirm_dialog')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <ActionButton
            actionType="secondary"
            onClick={() => setPasswordConfirmDialogOpen(false)}
          >
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="primary" onClick={handleApplyPassword}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
