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

export const SecurityPanel: React.FC = () => {
  const { t } = useTranslation('admin');
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
    } catch {
      showError(t('system.logs_unavailable'));
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleSshToggle = async (enable: boolean) => {
    try {
      const next = await systemApi.setSshToggle(enable);
      setSshStatus({ enabled: next.enabled, active: next.active });
    } catch (err: unknown) {
      const ax = err && typeof err === 'object' && 'response' in err ? (err as { response?: { status?: number; data?: unknown } }).response : undefined;
      const data = ax && typeof ax === 'object' && 'data' in ax ? (ax as { data?: unknown }).data : undefined;
      const d = data && typeof data === 'object' && data !== null && 'detail' in data ? (data as { detail: unknown }).detail : undefined;
      let msg: string;
      if (typeof d === 'string') msg = d;
      else if (Array.isArray(d)) msg = d.map((x: { msg?: string }) => x?.msg ?? String(x)).filter(Boolean).join(' ') || t('system.ssh_toggle_failed');
      else if (d && typeof d === 'object' && ('detail' in d || 'message' in d)) msg = String((d as { detail?: string; message?: string }).detail ?? (d as { message?: string }).message);
      else msg = t('system.ssh_toggle_failed');
      showError(msg);
    }
  };

  return (
    <Box>
      <AuthSection />

      <Box sx={{ mt: 3, mb: 3 }}>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 600 }}>
          {t('system.security_title')}
        </Typography>
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
      </Box>

      {/* ── Passwort Dialog ────────────────────────────────────────────────── */}
      <Dialog open={passwordDialogOpen} onClose={() => { setPasswordDialogOpen(false); setPasswordNew(''); setPasswordConfirm(''); }}>
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
      </Dialog>

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
