import React, { useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

interface PasswordDialogProps {
  open: boolean;
}

export const PasswordDialog: React.FC<PasswordDialogProps> = ({ open }) => {
  const { t } = useTranslation('admin');
  const navigate = useNavigate();
  const { login } = useAuth();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!password.trim()) return;
    try {
      await login(password.trim());
      setPassword('');
    } catch {
      setError(t('auth.wrong_password'));
    }
  };

  const handleCancel = () => {
    setPassword('');
    setError(null);
    navigate('/player');
  };

  return (
    <Dialog open={open} onClose={handleCancel} maxWidth="xs" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle>{t('auth.password_required')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {t('auth.password_prompt')}
          </DialogContentText>
          <TextField
            autoFocus
            fullWidth
            type="password"
            label={t('auth.password_label')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={!!error}
            helperText={error ?? undefined}
            margin="dense"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancel}>{t('auth.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={!password.trim()}>
            {t('auth.submit')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};
