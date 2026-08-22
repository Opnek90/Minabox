import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { ActionButton } from '@/components/ui/ActionButton';

interface FolderCreateDialogProps {
  open: boolean;
  /** When provided, the dialog operates in rename mode */
  initialName?: string;
  onClose: () => void;
  onSubmit: (name: string) => Promise<void>;
}

export const FolderCreateDialog: React.FC<FolderCreateDialogProps> = ({
  open,
  initialName,
  onClose,
  onSubmit,
}) => {
  const { t } = useTranslation('media');
  const isRename = initialName !== undefined;
  const [name, setName] = useState(initialName ?? '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setName(initialName ?? '');
  }, [open, initialName]);

  const handleSubmit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await onSubmit(trimmed);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        {isRename
          ? t('folders.rename_title')
          : t('folders.create_title')}
      </DialogTitle>
      <DialogContent sx={{ pt: '16px !important' }}>
        <TextField
          autoFocus
          label={t('folders.name_label')}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void handleSubmit(); }}
          fullWidth
          size="small"
        />
      </DialogContent>
      <DialogActions>
        <ActionButton actionType="secondary" onClick={onClose} disabled={saving}>
          {t('cancel', { ns: 'common' })}
        </ActionButton>
        <ActionButton
          actionType="primary"
          onClick={handleSubmit}
          loading={saving}
          disabled={!name.trim() || saving}
        >
          {isRename
            ? t('folders.rename_confirm')
            : t('folders.create_confirm')}
        </ActionButton>
      </DialogActions>
    </Dialog>
  );
};
