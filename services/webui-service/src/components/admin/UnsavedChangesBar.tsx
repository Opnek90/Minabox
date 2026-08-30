import React from 'react';
import { Alert, Box, Typography } from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { ActionButton } from '@/components/ui/ActionButton';

interface UnsavedChangesBarProps {
  /** Nothing is shown while this is false. */
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  onDiscard: () => void;
}

/**
 * Says out loud that the panel is holding changes the box does not have yet.
 *
 * The LED and button panels edit a whole list and write it in one PUT, which is
 * right - the hardware services reload their config on every write, and a
 * reload per keystroke would make the lights flicker while somebody is typing.
 * What was wrong is that the dialog's own button said "Save" while only
 * touching local state, so closing the dialog and leaving the page threw the
 * work away without a word. The dialog now says "Apply" and this bar carries
 * the actual save.
 */
export const UnsavedChangesBar: React.FC<UnsavedChangesBarProps> = ({
  dirty,
  saving,
  onSave,
  onDiscard,
}) => {
  const { t } = useTranslation('common');

  if (!dirty) return null;

  return (
    <Alert
      severity="warning"
      icon={false}
      sx={{ mb: 2, '& .MuiAlert-message': { width: '100%' } }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" fontWeight={600}>
            {t('unsaved.title')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('unsaved.hint')}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexShrink: 0 }}>
          <ActionButton actionType="secondary" onClick={onDiscard} disabled={saving}>
            {t('actions.discard')}
          </ActionButton>
          <ActionButton
            actionType="primary"
            startIcon={<SaveIcon />}
            onClick={onSave}
            disabled={saving}
            loading={saving}
          >
            {t('actions.save')}
          </ActionButton>
        </Box>
      </Box>
    </Alert>
  );
};
