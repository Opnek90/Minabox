import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  FormControlLabel,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import { setPassword, updateAuthConfig } from '@/api/auth';

const PATH_TO_AREA: Record<string, string> = {
  '/admin': 'admin',
  '/media': 'media',
  '/dashboard': 'dashboard',
};

function pathsToAreas(protectedPaths: string[]): string[] {
  return protectedPaths
    .map((p) => PATH_TO_AREA[p])
    .filter((a): a is string => !!a);
}

export const AuthSection: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const { authEnabled, protectedPaths, login, logout, refreshConfig } = useAuth();

  const [adminProtected, setAdminProtected] = useState(false);
  const [mediaProtected, setMediaProtected] = useState(false);
  const [dashboardProtected, setDashboardProtected] = useState(false);
  const [savingAreas, setSavingAreas] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);

  useEffect(() => {
    const areas = pathsToAreas(protectedPaths);
    setAdminProtected(areas.includes('admin'));
    setMediaProtected(areas.includes('media'));
    setDashboardProtected(areas.includes('dashboard'));
  }, [protectedPaths]);

  const handleSaveAreas = async () => {
    setSavingAreas(true);
    try {
      const areas: string[] = [];
      if (adminProtected) areas.push('admin');
      if (mediaProtected) areas.push('media');
      if (dashboardProtected) areas.push('dashboard');
      await updateAuthConfig({ protected_areas: areas });
      await refreshConfig();
      showSuccess(t('auth.areas_saved'));
    } catch (e) {
      showError(t('auth.areas_save_failed'));
    } finally {
      setSavingAreas(false);
    }
  };

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 4) {
      showError(t('auth.password_too_short'));
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
      if (!authEnabled) login(newPassword);
    } catch (err: unknown) {
      const ax = err as { response?: { data?: unknown; status?: number }; message?: string };
      if (import.meta.env.DEV) {
        console.error('[AuthSection] setPassword error:', ax);
      }
      const res = ax?.response;
      const data = res?.data;
      const status = res?.status;
      const rawDetail =
        data != null && typeof data === 'object' && 'detail' in data
          ? (data as { detail?: string | unknown[] }).detail
          : undefined;
      const detail =
        typeof rawDetail === 'string'
          ? rawDetail
          : Array.isArray(rawDetail) && rawDetail.length > 0
            ? String((rawDetail[0] as { msg?: string }).msg ?? rawDetail[0])
            : null;
      if (status === 401 && detail === 'Authentication required') {
        showError(t('auth.session_expired'));
      } else if (status === 400 && (detail === 'Current password required' || (detail && String(detail).includes('current')))) {
        showError(t('auth.current_password_required'));
      } else if (status === 401) {
        showError(t('auth.wrong_password'));
      } else if (detail) {
        showError(detail);
      } else if (status != null) {
        showError(`${t('auth.password_save_failed')} (HTTP ${status})`);
      } else {
        showError(t('auth.password_save_failed'));
      }
    } finally {
      setSavingPassword(false);
    }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Typography variant="h6" gutterBottom>
        {t('auth.tab_title')}
      </Typography>

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {t('auth.protected_areas_title')}
        </Typography>
        <FormControlLabel
          control={
            <Switch
              checked={adminProtected}
              onChange={(_, v) => setAdminProtected(v)}
            />
          }
          label={t('auth.protected_admin')}
        />
        <FormControlLabel
          control={
            <Switch
              checked={mediaProtected}
              onChange={(_, v) => setMediaProtected(v)}
            />
          }
          label={t('auth.protected_media')}
        />
        <FormControlLabel
          control={
            <Switch
              checked={dashboardProtected}
              onChange={(_, v) => setDashboardProtected(v)}
            />
          }
          label={t('auth.protected_dashboard')}
        />
        <Box sx={{ mt: 1 }}>
          <Button
            variant="contained"
            onClick={handleSaveAreas}
            disabled={savingAreas}
          >
            {t('auth.save_areas')}
          </Button>
        </Box>
      </Box>

      <Box component="form" onSubmit={handleSetPassword} sx={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 400 }}>
        <Typography variant="subtitle2">
          {authEnabled ? t('auth.change_password') : t('auth.set_password')}
        </Typography>
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
        <Button type="submit" variant="contained" disabled={savingPassword}>
          {authEnabled ? t('auth.change_password_submit') : t('auth.set_password_submit')}
        </Button>
      </Box>

      {authEnabled && (
        <Box>
          <Button variant="outlined" color="secondary" onClick={() => logout()}>
            {t('auth.logout')}
          </Button>
        </Box>
      )}
    </Box>
  );
}
