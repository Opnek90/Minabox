import React, { useState } from 'react';
import {
  Alert,
  Box,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Typography,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useTranslation } from 'react-i18next';
import type { UpdateStatusResponse } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';

interface UpdateProgressDialogProps {
  open: boolean;
  running: boolean;
  status: UpdateStatusResponse | null;
  onClose: () => void;
}

/** Was gerade mit der Box passiert, waehrend sie sich selbst aktualisiert. */
export const UpdateProgressDialog: React.FC<UpdateProgressDialogProps> = ({
  open,
  running,
  status,
  onClose,
}) => {
  const { t } = useTranslation('admin');
  const [logOpen, setLogOpen] = useState(false);

  const succeeded = !running && status?.exit_code === 0;
  const failed = !running && status?.exit_code != null && status.exit_code !== 0;

  // Als Werte statt als Flag: ein `boolean` daneben verengt die beiden
  // `number | null` fuer TypeScript nicht, und t() nimmt kein null als count.
  const step = status?.step ?? null;
  const stepCount = status?.step_count ?? null;
  const stepLabel =
    step !== null && stepCount !== null && stepCount > 0
      ? t('system.update_step', { step, count: stepCount })
      : t('system.update_starting');
  const percent =
    step !== null && stepCount !== null && stepCount > 0 ? (step / stepCount) * 100 : null;

  return (
    <Dialog
      open={open}
      // Kein Schliessen per Klick daneben, solange es laeuft: das Fenster ist
      // die einzige Stelle, an der man sieht, was gerade mit der Box passiert.
      onClose={() => { if (!running) onClose(); }}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>{t('system.update_progress_title')}</DialogTitle>
      <DialogContent>
        <Box display="flex" alignItems="center" gap={1.5} sx={{ mb: 1 }}>
          {running ? (
            <CircularProgress size={22} />
          ) : succeeded ? (
            <CheckCircleIcon color="success" />
          ) : (
            <ErrorOutlineIcon color="error" />
          )}
          <Box minWidth={0}>
            <Typography variant="body2">{stepLabel}</Typography>
            <Typography variant="caption" color="text.secondary">
              {succeeded
                ? t('system.update_success')
                : failed
                  ? t('system.update_failed')
                  : status?.step_key
                    // step_key kommt vom Orchestrierungsskript und ist nicht an
                    // eine feste Werte-Menge gebunden - statisch pruefbar ist er nicht.
                    ? t(`system.update_step_${status.step_key}` as never)
                    : ''}
            </Typography>
          </Box>
        </Box>

        {running && (
          <LinearProgress
            variant={percent === null ? 'indeterminate' : 'determinate'}
            value={percent ?? undefined}
            sx={{ mb: 1.5, height: 6, borderRadius: 3 }}
          />
        )}

        {status?.unreachable && running && (
          // Genau das ist der Neustart der Dienste - kein Fehler, sondern der
          // erwartete Teil des Updates.
          <Alert severity="info" sx={{ mb: 1.5 }}>
            {t('system.update_reconnecting')}
          </Alert>
        )}

        <ActionButton
          actionType="secondary"
          startIcon={
            <ExpandMoreIcon
              sx={{ transform: logOpen ? 'rotate(180deg)' : 'none', transition: '0.2s' }}
            />
          }
          onClick={() => setLogOpen((v) => !v)}
        >
          {logOpen ? t('system.update_details_hide') : t('system.update_details_show')}
        </ActionButton>

        <Collapse in={logOpen}>
          <Box
            component="pre"
            sx={{
              whiteSpace: 'pre-wrap',
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              maxHeight: 360,
              overflow: 'auto',
              p: 1,
              mt: 1,
              bgcolor: 'action.hover',
              borderRadius: 1,
            }}
          >
            {status?.log || t('system.update_os_log_empty')}
          </Box>
        </Collapse>
      </DialogContent>
      <DialogActions>
        <ActionButton actionType="secondary" onClick={onClose} disabled={running}>
          {t('actions.close', { ns: 'common' })}
        </ActionButton>
      </DialogActions>
    </Dialog>
  );
};
