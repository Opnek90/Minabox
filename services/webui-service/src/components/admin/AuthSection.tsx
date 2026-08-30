import React, { useEffect, useState } from 'react';
import {
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  FormHelperText,
  Switch,
  TextField,
} from '@mui/material';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import { setPassword, updateAuthConfig, resetAuth } from '@/api/auth';
import { ActionButton } from '@/components/ui/ActionButton';
import { apiErrorCode, translateApiError } from '@/utils/apiError';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { MIN_PASSWORD_LENGTH } from '@/utils/validators';

// Ein Bereich kann mehrere Seiten abdecken: „Player" schuetzt auch die
// Karten-Seite, weil beide auf denselben Backend-Routen sitzen.
const PATH_TO_AREA: Record<string, string> = {
  '/admin': 'admin',
  '/media': 'media',
  '/dashboard': 'dashboard',
  '/player': 'player',
  '/rfid': 'player',
};

function pathsToAreas(protectedPaths: string[]): string[] {
  return protectedPaths
    .map((p) => PATH_TO_AREA[p])
    .filter((a): a is string => !!a);
}

export const AuthSection: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const { authEnabled, protectedPaths, login, logout, refreshConfig } = useAuth();

  const [adminProtected, setAdminProtected] = useState(false);
  const [mediaProtected, setMediaProtected] = useState(false);
  const [dashboardProtected, setDashboardProtected] = useState(false);
  const [playerProtected, setPlayerProtected] = useState(false);
  const [savingAreas, setSavingAreas] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    const areas = pathsToAreas(protectedPaths);
    setAdminProtected(areas.includes('admin'));
    setMediaProtected(areas.includes('media'));
    setDashboardProtected(areas.includes('dashboard'));
    setPlayerProtected(areas.includes('player'));
  }, [protectedPaths]);

  const handleSaveAreas = async () => {
    setSavingAreas(true);
    try {
      const areas: string[] = [];
      if (adminProtected) areas.push('admin');
      if (mediaProtected) areas.push('media');
      if (dashboardProtected) areas.push('dashboard');
      if (playerProtected) areas.push('player');
      await updateAuthConfig({ protected_areas: areas });
      await refreshConfig();
      showSuccess(t('auth.areas_saved'));
    } catch {
      showError(t('auth.areas_save_failed'));
    } finally {
      setSavingAreas(false);
    }
  };

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      showError(t('auth.password_too_short', { min: MIN_PASSWORD_LENGTH }));
      return;
    }
    if (newPassword !== confirmPassword) {
      showError(t('auth.password_mismatch'));
      return;
    }
    setSavingPassword(true);
    try {
      await setPassword({
        ...(authEnabled ? { current_password: currentPassword } : {}),
        new_password: newPassword,
      });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      showSuccess(t('auth.password_saved'));
      await refreshConfig();
      if (!authEnabled) await login(newPassword);
    } catch (err: unknown) {
      const code = apiErrorCode(err);
      if (code === 'auth_required') {
        showError(t('auth.session_expired'));
      } else if (code === 'current_password_required') {
        showError(t('auth.current_password_required'));
      } else if (code === 'current_password_invalid') {
        showError(t('auth.wrong_password'));
      } else {
        showError(translateApiError(t, i18n, err));
      }
    } finally {
      setSavingPassword(false);
    }
  };

  const handleResetAuth = async () => {
    setResetDialogOpen(false);
    setResetting(true);
    try {
      await resetAuth();
      await updateAuthConfig({ protected_areas: [] });
      await refreshConfig();
      showSuccess(t('auth.reset_success'));
    } catch {
      showError(t('auth.reset_failed'));
    } finally {
      setResetting(false);
    }
  };

  return (
    <Box>
      {/* ── Geschützte Bereiche ────────────────────────────────────────────── */}
      <SettingsBlock title={t('auth.protected_areas_title')}>
        <FormControlLabel
          control={<Switch checked={adminProtected} onChange={(_, v) => setAdminProtected(v)} />}
          label={t('auth.protected_admin')}
        />
        <FormControlLabel
          control={<Switch checked={mediaProtected} onChange={(_, v) => setMediaProtected(v)} />}
          label={t('auth.protected_media')}
        />
        <FormControlLabel
          control={<Switch checked={dashboardProtected} onChange={(_, v) => setDashboardProtected(v)} />}
          label={t('auth.protected_dashboard')}
        />
        <FormControlLabel
          control={<Switch checked={playerProtected} onChange={(_, v) => setPlayerProtected(v)} />}
          label={t('auth.protected_player')}
        />
        <FormHelperText>{t('auth.protected_player_hint')}</FormHelperText>
        <Box sx={{ mt: 1 }}>
          <ActionButton
            actionType="primary"
            onClick={handleSaveAreas}
            disabled={savingAreas}
            loading={savingAreas}
          >
            {t('auth.save_areas')}
          </ActionButton>
        </Box>
      </SettingsBlock>

      {/* ── Passwort festlegen / ändern ───────────────────────────────────── */}
      <SettingsBlock title={authEnabled ? t('auth.change_password') : t('auth.set_password')}>
      <Box component="form" onSubmit={handleSetPassword} sx={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 400 }}>
        {authEnabled && (
          <TextField
            fullWidth
            type="password"
            label={t('auth.current_password')}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            margin="dense"
          />
        )}
        <TextField
          fullWidth
          type="password"
          label={t('auth.new_password')}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          margin="dense"
          required
          helperText={t('auth.password_hint', { min: MIN_PASSWORD_LENGTH })}
        />
        <TextField
          fullWidth
          type="password"
          label={t('auth.confirm_password')}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          margin="dense"
          required
        />
        <ActionButton
          actionType="primary"
          type="submit"
          loading={savingPassword}
          disabled={savingPassword}
        >
          {authEnabled ? t('auth.change_password_submit') : t('auth.set_password_submit')}
        </ActionButton>
        <Box sx={{ mt: 1 }}>
          <ActionButton
            actionType="destructive"
            startIcon={<DeleteForeverIcon />}
            onClick={() => setResetDialogOpen(true)}
            disabled={resetting || !authEnabled}
          >
            {t('auth.reset_button')}
          </ActionButton>
        </Box>
      </Box>
      </SettingsBlock>

      {/* ── Logout ────────────────────────────────────────────────────────── */}
      {authEnabled && (
        <Box>
          <ActionButton actionType="secondary" onClick={() => logout()}>
            {t('auth.logout')}
          </ActionButton>
        </Box>
      )}

      {/* ── Reset Dialog ──────────────────────────────────────────────────── */}
      <Dialog open={resetDialogOpen} onClose={() => setResetDialogOpen(false)}>
        <DialogTitle>{t('auth.reset_button')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('auth.reset_confirm_text')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setResetDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleResetAuth}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
