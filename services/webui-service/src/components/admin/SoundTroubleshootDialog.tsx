import React, { useCallback, useState } from 'react';
import {
  Alert,
  Box,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { translateApiError } from '@/utils/apiError';
import type { AudioTroubleshootResult } from '@/types/api';

/**
 * "Fix sound problem" (docs/services/Offene-Punkte.md 1.7).
 *
 * The box walks the check chain, repairs what it safely can, plays a tone and
 * then asks the only question that actually settles it: do you hear anything?
 *
 * What the user never sees: pactl, role names, sink indices. Those are in the
 * debug export, not in this dialog. What they do see is one sentence naming
 * what it was, and - if it is still silent - the two things only a human can
 * check.
 */

/** Where the conversation stands. */
type Phase =
  | 'idle'
  /** The chain is running; it ends with the tone. */
  | 'checking'
  /** Tone played, waiting for "do you hear it?". */
  | 'asking'
  | 'fixed'
  /** Still nothing. Offer to restart the audio service. */
  | 'escalate_restart'
  | 'restarting'
  /** Restarted, tone played again, asking once more. */
  | 'asking_after_restart'
  /** Nothing left the box can do by itself: cable, power, reboot. */
  | 'escalate_human'
  | 'rebooting';

interface Props {
  open: boolean;
  onClose: () => void;
}

export const SoundTroubleshootDialog: React.FC<Props> = ({ open, onClose }) => {
  const { t, i18n } = useTranslation('admin');
  const [phase, setPhase] = useState<Phase>('idle');
  const [result, setResult] = useState<AudioTroubleshootResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runChain = useCallback(async (next: Phase) => {
    setError(null);
    setPhase('checking');
    try {
      const data = await audioApi.troubleshoot();
      setResult(data);
      setPhase(next);
    } catch (e) {
      setError(translateApiError(t, i18n, e));
      setPhase('idle');
    }
  }, [t, i18n]);

  const handleStart = useCallback(() => runChain('asking'), [runChain]);

  const handleYes = useCallback(() => setPhase('fixed'), []);

  // After the restart there is nothing left to restart: the next step is the
  // two things only a person standing at the box can check.
  const handleNo = useCallback(
    () =>
      setPhase((current) =>
        current === 'asking_after_restart' ? 'escalate_human' : 'escalate_restart'
      ),
    []
  );

  const handleRestart = useCallback(async () => {
    setError(null);
    setPhase('restarting');
    try {
      await audioApi.restartService();
      // The service needs a moment to come back before the tone means
      // anything - asking a container that is still starting proves nothing.
      await new Promise((resolve) => setTimeout(resolve, 8000));
      await runChain('asking_after_restart');
    } catch (e) {
      setError(translateApiError(t, i18n, e));
      setPhase('escalate_human');
    }
  }, [runChain, t, i18n]);

  const handleReboot = useCallback(async () => {
    setPhase('rebooting');
    try {
      await systemApi.rebootHost();
    } catch {
      /* the connection drops - that is the reboot working */
    }
  }, []);

  const handleClose = useCallback(() => {
    setPhase('idle');
    setResult(null);
    setError(null);
    onClose();
  }, [onClose]);

  // The one sentence naming what it was. Falls back to a neutral line rather
  // than inventing a cause: "it works now" is honest, "it was X" would not be.
  const causeText = result?.cause
    ? t(`system.sound_fix.cause.${result.cause}`, {
        defaultValue: t('system.sound_fix.cause.unknown'),
      })
    : t('system.sound_fix.cause.nothing_found');

  const busy = phase === 'checking' || phase === 'restarting' || phase === 'rebooting';

  const busyText =
    phase === 'restarting'
      ? t('system.sound_fix.restarting')
      : phase === 'rebooting'
        ? t('system.sound_fix.rebooting')
        : t('system.sound_fix.checking');

  return (
    <Dialog open={open} onClose={busy ? undefined : handleClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t('system.sound_fix.title')}</DialogTitle>

      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {phase === 'idle' && (
          <Typography variant="body2">{t('system.sound_fix.intro')}</Typography>
        )}

        {busy && (
          <Box display="flex" alignItems="center" gap={2} py={2}>
            <CircularProgress size={24} />
            <Typography variant="body2">{busyText}</Typography>
          </Box>
        )}

        {/* The question that settles it. Deliberately large and plain: this is
            the one thing the person in front of the box has to answer. */}
        {(phase === 'asking' || phase === 'asking_after_restart') && (
          <Box py={1}>
            <Typography variant="h6" component="p" gutterBottom>
              {t('system.sound_fix.question')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {result?.tone_played
                ? t('system.sound_fix.question_hint')
                : t('system.sound_fix.no_tone_hint')}
            </Typography>
            {result && !result.host_checks_available && (
              <Alert severity="info" sx={{ mt: 2 }}>
                {t('system.sound_fix.host_checks_missing')}
              </Alert>
            )}
          </Box>
        )}

        {phase === 'fixed' && (
          <Box display="flex" gap={1.5} py={1}>
            <CheckCircleIcon color="success" />
            <Box>
              <Typography variant="body1" gutterBottom>
                {t('system.sound_fix.solved')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {causeText}
              </Typography>
            </Box>
          </Box>
        )}

        {phase === 'escalate_restart' && (
          <Typography variant="body2">{t('system.sound_fix.try_restart')}</Typography>
        )}

        {phase === 'escalate_human' && (
          <Box>
            {/* The two things no software on this box can check for itself. */}
            <Typography variant="body2" gutterBottom>
              {t('system.sound_fix.check_yourself')}
            </Typography>
            <Typography component="ul" variant="body2" sx={{ pl: 2.5, mb: 2 }}>
              <li>{t('system.sound_fix.check_cable')}</li>
              <li>{t('system.sound_fix.check_power')}</li>
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('system.sound_fix.last_resort')}
            </Typography>
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        {phase === 'idle' && (
          <>
            <ActionButton actionType="secondary" onClick={handleClose}>
              {t('actions.cancel', { ns: 'common' })}
            </ActionButton>
            <ActionButton
              actionType="primary"
              startIcon={<VolumeUpIcon />}
              onClick={handleStart}
            >
              {t('system.sound_fix.start')}
            </ActionButton>
          </>
        )}

        {(phase === 'asking' || phase === 'asking_after_restart') && (
          <>
            <ActionButton actionType="secondary" onClick={handleNo}>
              {t('system.sound_fix.answer_no')}
            </ActionButton>
            <ActionButton actionType="primary" onClick={handleYes}>
              {t('system.sound_fix.answer_yes')}
            </ActionButton>
          </>
        )}

        {phase === 'fixed' && (
          <ActionButton actionType="primary" onClick={handleClose}>
            {t('actions.close', { ns: 'common' })}
          </ActionButton>
        )}

        {phase === 'escalate_restart' && (
          <>
            <ActionButton actionType="secondary" onClick={handleClose}>
              {t('actions.close', { ns: 'common' })}
            </ActionButton>
            <ActionButton
              actionType="primary"
              startIcon={<RestartAltIcon />}
              onClick={handleRestart}
            >
              {t('system.sound_fix.restart_audio')}
            </ActionButton>
          </>
        )}

        {phase === 'escalate_human' && (
          <>
            <ActionButton actionType="secondary" onClick={handleClose}>
              {t('actions.close', { ns: 'common' })}
            </ActionButton>
            <ActionButton
              actionType="destructive"
              startIcon={<PowerSettingsNewIcon />}
              onClick={handleReboot}
            >
              {t('system.sound_fix.reboot')}
            </ActionButton>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
};
