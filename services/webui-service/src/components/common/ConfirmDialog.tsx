import React from 'react';
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { ActionButton } from '@/components/ui/ActionButton';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  /** One sentence saying what happens. */
  message: string;
  /** Red confirm button for anything that interrupts playback or deletes. */
  destructive?: boolean;
  /** Overrides the default "Confirm". */
  confirmLabel?: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * Title, one sentence, cancel, confirm.
 *
 * The maintenance page alone had five of these written out by hand, differing
 * only in which two translation keys they used. Anything that needs more - a
 * checkbox, a file picker, a typed confirmation word - stays its own dialog;
 * this is for the plain question.
 */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  message,
  destructive = false,
  confirmLabel,
  busy = false,
  onCancel,
  onConfirm,
}) => {
  const { t } = useTranslation('common');

  return (
    <Dialog open={open} onClose={onCancel}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText>{message}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <ActionButton actionType="secondary" onClick={onCancel} disabled={busy}>
          {t('actions.cancel')}
        </ActionButton>
        <ActionButton
          actionType={destructive ? 'destructive' : 'primary'}
          onClick={onConfirm}
          disabled={busy}
          loading={busy}
        >
          {confirmLabel ?? t('actions.confirm')}
        </ActionButton>
      </DialogActions>
    </Dialog>
  );
};
