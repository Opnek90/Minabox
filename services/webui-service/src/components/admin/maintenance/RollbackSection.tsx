import React, { useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Tooltip,
  Typography,
} from '@mui/material';
import UndoIcon from '@mui/icons-material/Undo';
import { useTranslation } from 'react-i18next';
import type { RollbackCandidate } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { HelpTip } from '@/components/ui/HelpTip';

/**
 * The way back: per service, the version it ran before the last update.
 *
 * This exists so a bad release does not mean console work on a box that a
 * family uses every day - and the person who has to do it is usually not the
 * person who built it.
 *
 * A service whose step back would cross a database migration is shown, but
 * its button is disabled and says why. Hiding it would leave the same question
 * unanswered ("why can I not go back?") one screen further away.
 */
export const RollbackSection: React.FC<{
  candidates: RollbackCandidate[];
  disabled: boolean;
  onRollback: (service: string) => void;
}> = ({ candidates, disabled, onRollback }) => {
  const { t } = useTranslation('admin');
  const [pending, setPending] = useState<RollbackCandidate | null>(null);

  if (candidates.length === 0) return null;

  const confirm = () => {
    const service = pending?.service;
    setPending(null);
    if (service) onRollback(service);
  };

  return (
    <Box sx={{ mt: 2 }}>
      <Box display="flex" alignItems="center" gap={0.5} sx={{ mb: 1 }}>
        <Typography variant="subtitle2">{t('system.rollback_title')}</Typography>
        <HelpTip title={t('system.rollback_hint')} label={t('system.rollback_title')} />
      </Box>

      {candidates.map((candidate) => (
        <Box
          key={candidate.service}
          display="flex"
          alignItems="center"
          gap={1}
          sx={{ mb: 0.5, minWidth: 0 }}
        >
          <Typography
            variant="body2"
            sx={{ textTransform: 'capitalize', flex: 1, minWidth: 0 }}
            noWrap
          >
            {candidate.service}
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {candidate.installed} → {candidate.target}
          </Typography>
          {/* A disabled button swallows its own tooltip, so the span carries it. */}
          <Tooltip
            title={
              candidate.allowed
                ? ''
                : t(`system.rollback_reason_${candidate.reason ?? 'unknown'}`)
            }
          >
            <span>
              <ActionButton
                actionType="secondary"
                size="small"
                startIcon={<UndoIcon />}
                disabled={disabled || !candidate.allowed}
                onClick={() => setPending(candidate)}
              >
                {t('system.rollback_action', { version: candidate.target })}
              </ActionButton>
            </span>
          </Tooltip>
        </Box>
      ))}

      <Dialog open={pending !== null} onClose={() => setPending(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('system.rollback_title')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {t('system.rollback_confirm', {
              service: pending?.service ?? '',
              version: pending?.target ?? '',
            })}
          </DialogContentText>
          <Alert severity="info">{t('system.update_backup_hint')}</Alert>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setPending(null)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="primary" onClick={confirm}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
