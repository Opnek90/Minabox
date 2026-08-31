import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Checkbox,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { getAuthConfig, setPassword, updateAuthConfig } from '@/api/auth';
import { MIN_PASSWORD_LENGTH } from '@/utils/validators';

const AREAS = ['admin', 'media', 'dashboard', 'player'] as const;
type Area = (typeof AREAS)[number];

interface Props {
  /** Registers the save function with the wizard; false = input is not valid. */
  registerSave: (fn: () => Promise<boolean>) => void;
}

export const SecurityStep: React.FC<Props> = ({ registerSave }) => {
  const { t } = useTranslation('setup');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [areas, setAreas] = useState<Area[]>(['admin', 'media', 'dashboard']);
  const [alreadySet, setAlreadySet] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAuthConfig()
      .then((cfg) => setAlreadySet(cfg.authEnabled))
      .catch(() => setAlreadySet(false));
  }, []);

  useEffect(() => {
    registerSave(async () => {
      // Leer lassen ist erlaubt und bedeutet "uebersprungen" - der Hinweis
      // darauf steht unten sichtbar, es passiert also nichts stillschweigend.
      if (!pw && !pw2) return true;
      if (pw.length < MIN_PASSWORD_LENGTH) {
        setError(t('security.too_short', { min: MIN_PASSWORD_LENGTH }));
        return false;
      }
      if (pw !== pw2) {
        setError(t('security.mismatch'));
        return false;
      }
      try {
        await setPassword({ new_password: pw });
        await updateAuthConfig({ protected_areas: areas });
        setError(null);
        return true;
      } catch {
        setError(t('password_set_failed', { ns: 'errors' }));
        return false;
      }
    });
  }, [pw, pw2, areas, registerSave, t]);

  const toggle = (a: Area) =>
    setAreas((prev) => (prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]));

  return (
    <Stack spacing={2}>
      <Typography variant="h6">{t('security.heading')}</Typography>
      <Alert severity="info">{t('security.intro')}</Alert>

      {alreadySet && <Alert severity="success">{t('security.already_set')}</Alert>}

      <TextField
        label={t('security.password')}
        type="password"
        value={pw}
        onChange={(e) => setPw(e.target.value)}
        size="small"
        fullWidth
        autoComplete="new-password"
        helperText={t('security.password_hint', { min: MIN_PASSWORD_LENGTH })}
      />
      <TextField
        label={t('security.password_repeat')}
        type="password"
        value={pw2}
        onChange={(e) => setPw2(e.target.value)}
        size="small"
        fullWidth
        autoComplete="new-password"
        error={!!pw2 && pw !== pw2}
      />

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {t('security.areas')}
        </Typography>
        {AREAS.map((a) => (
          <FormControlLabel
            key={a}
            control={<Checkbox checked={areas.includes(a)} onChange={() => toggle(a)} />}
            label={t(`security.area_${a}`)}
          />
        ))}
      </Box>

      {error && <Alert severity="error">{error}</Alert>}
      {!pw && !alreadySet && <Alert severity="warning">{t('security.skip_note')}</Alert>}
    </Stack>
  );
};
