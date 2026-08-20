import React, { useCallback, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Container,
  MenuItem,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { configApi } from '@/api/config';
import { useLayout } from '@/hooks/useLayout';
import { SETUP_VERSION } from '@/hooks/useSetupStatus';
import { SecurityStep } from '@/components/setup/SecurityStep';
import { AudioStep } from '@/components/setup/AudioStep';
import { HardwareStep } from '@/components/setup/HardwareStep';
import { ContentStep } from '@/components/setup/ContentStep';

type StepKey = 'welcome' | 'security' | 'audio' | 'hardware' | 'content' | 'done';
const STEPS: StepKey[] = ['welcome', 'security', 'audio', 'hardware', 'content', 'done'];

export const SetupWizardPage: React.FC = () => {
  const { t, i18n } = useTranslation('setup');
  const navigate = useNavigate();
  const isSmall = useLayout().isMobile;

  const [active, setActive] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);

  // Schritte melden hier ihre Speicherfunktion an. Ein Ref statt State, damit
  // das Anmelden keinen Renderdurchlauf ausloest und in eine Schleife laeuft.
  const saveRef = useRef<(() => Promise<boolean>) | null>(null);
  const registerSave = useCallback((fn: () => Promise<boolean>) => {
    saveRef.current = fn;
  }, []);

  const stepKey = STEPS[active];

  const goNext = async () => {
    setSaveError(null);
    if (saveRef.current) {
      const ok = await saveRef.current();
      if (!ok) return;
    }
    saveRef.current = null;
    setActive((a) => Math.min(a + 1, STEPS.length - 1));
  };

  const goSkip = () => {
    setSaveError(null);
    saveRef.current = null;
    setActive((a) => Math.min(a + 1, STEPS.length - 1));
  };

  const goBack = () => {
    setSaveError(null);
    saveRef.current = null;
    setActive((a) => Math.max(a - 1, 0));
  };

  const finish = async () => {
    setFinishing(true);
    try {
      await configApi.updateGeneral({
        setup_completed: true,
        setup_version: SETUP_VERSION,
      });
    } catch {
      // Der Assistent wuerde beim naechsten Start erneut erscheinen. Das ist
      // laestig, aber besser als hier haengen zu bleiben.
    } finally {
      setFinishing(false);
      navigate('/player');
    }
  };

  const leave = async () => {
    if (!window.confirm(t('close_confirm'))) return;
    navigate('/player');
  };

  const changeLanguage = (lng: string) => {
    void i18n.changeLanguage(lng);
    localStorage.setItem('minabox-language', lng);
  };

  return (
    <Container maxWidth="sm" sx={{ py: 3 }}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="h5">{t('title')}</Typography>
          <Typography variant="body2" color="text.secondary">
            {t('subtitle')}
          </Typography>
        </Box>

        {!isSmall && (
          <Stepper activeStep={active} alternativeLabel>
            {STEPS.map((s) => (
              <Step key={s}>
                <StepLabel>{t(`steps.${s}`)}</StepLabel>
              </Step>
            ))}
          </Stepper>
        )}
        {isSmall && (
          <Typography variant="caption" color="text.secondary">
            {active + 1} / {STEPS.length} · {t(`steps.${stepKey}`)}
          </Typography>
        )}

        <Paper variant="outlined" sx={{ p: 2 }}>
          {stepKey === 'welcome' && (
            <Stack spacing={2}>
              <Typography variant="h6">{t('welcome.heading')}</Typography>
              <Typography variant="body2">{t('welcome.body')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t('welcome.duration')}
              </Typography>
              <TextField
                select
                label={t('welcome.language')}
                value={i18n.resolvedLanguage ?? 'de'}
                onChange={(e) => changeLanguage(e.target.value)}
                size="small"
                sx={{ maxWidth: 240 }}
              >
                <MenuItem value="de">Deutsch</MenuItem>
                <MenuItem value="en">English</MenuItem>
              </TextField>
            </Stack>
          )}

          {stepKey === 'security' && <SecurityStep registerSave={registerSave} />}
          {stepKey === 'audio' && <AudioStep registerSave={registerSave} />}
          {stepKey === 'hardware' && <HardwareStep />}
          {stepKey === 'content' && <ContentStep />}

          {stepKey === 'done' && (
            <Stack spacing={2} alignItems="center" sx={{ py: 2 }}>
              <CheckCircleIcon color="success" sx={{ fontSize: 48 }} />
              <Typography variant="h6">{t('done.heading')}</Typography>
              <Typography variant="body2">{t('done.body')}</Typography>
              <Typography variant="caption" color="text.secondary" align="center">
                {t('done.restart_hint')}
              </Typography>
            </Stack>
          )}
        </Paper>

        {saveError && <Alert severity="error">{saveError}</Alert>}

        <Stack direction="row" spacing={1} justifyContent="space-between">
          <Button onClick={leave} color="inherit" size="small">
            {t('close')}
          </Button>

          <Stack direction="row" spacing={1}>
            {active > 0 && stepKey !== 'done' && <Button onClick={goBack}>{t('back')}</Button>}
            {stepKey !== 'welcome' && stepKey !== 'done' && (
              <Button onClick={goSkip} color="inherit">
                {t('skip')}
              </Button>
            )}
            {stepKey !== 'done' ? (
              <Button variant="contained" onClick={goNext}>
                {t('next')}
              </Button>
            ) : (
              <Button variant="contained" onClick={finish} disabled={finishing}>
                {t('done.to_player')}
              </Button>
            )}
          </Stack>
        </Stack>
      </Stack>
    </Container>
  );
};

export default SetupWizardPage;
