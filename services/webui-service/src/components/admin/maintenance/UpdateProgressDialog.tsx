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

/** The part of a run this dialog reads. Update and component change agree on it. */
export interface ProgressStatus {
  step: number | null;
  step_count: number | null;
  step_key: string | null;
  exit_code: number | null;
  log: string;
  unreachable?: boolean;
}

interface UpdateProgressDialogProps {
  open: boolean;
  running: boolean;
  status: UpdateStatusResponse | ProgressStatus | null;
  onClose: () => void;
  /** Everything below is for the second caller, the component change. The
   *  defaults are the update wording, so that call site stays unchanged. */
  title?: string;
  successText?: string;
  failedText?: string;
  /** i18n key prefix for the step names; the step key is appended to it. */
  stepPrefix?: string;
}

/** What is happening to the box while it changes itself. */
export const UpdateProgressDialog: React.FC<UpdateProgressDialogProps> = ({
  open,
  running,
  status,
  onClose,
  title,
  successText,
  failedText,
  stepPrefix = 'system.update_step_',
}) => {
  const { t } = useTranslation('admin');
  const [logOpen, setLogOpen] = useState(false);

  const succeeded = !running && status?.exit_code === 0;
  const failed = !running && status?.exit_code != null && status.exit_code !== 0;

  // As values instead of a flag: a `boolean` alongside does not narrow the two
  // `number | null` for TypeScript, and t() does not take null as a count.
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
      // No closing by clicking outside while it runs: this window is the only
      // place you can see what is happening to the box.
      onClose={() => { if (!running) onClose(); }}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>{title ?? t('system.update_progress_title')}</DialogTitle>
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
                ? (successText ?? t('system.update_success'))
                : failed
                  ? (failedText ?? t('system.update_failed'))
                  : status?.step_key
                    // step_key comes from the orchestration script and is not
                    // bound to a fixed set of values - it is not statically checkable.
                    ? t(`${stepPrefix}${status.step_key}` as never)
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
          // This is exactly the service restart - not an error, but the
          // expected part of the update.
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
