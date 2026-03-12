import React from 'react';
import { Box, CircularProgress, Dialog, DialogContent, Typography } from '@mui/material';
import NfcIcon from '@mui/icons-material/Nfc';
import CancelIcon from '@mui/icons-material/Cancel';
import { keyframes } from '@mui/system';
import { useTranslation } from 'react-i18next';
import { ActionButton } from '@/components/ui/ActionButton';

const pulse = keyframes`
  0%   { transform: scale(1);    opacity: 1; }
  50%  { transform: scale(1.15); opacity: 0.7; }
  100% { transform: scale(1);    opacity: 1; }
`;

interface LearnModeButtonProps {
  active: boolean;
  loading?: boolean;
  onActivate: () => void;
  onDeactivate: () => void;
}

export const LearnModeButton: React.FC<LearnModeButtonProps> = ({
  active,
  loading = false,
  onActivate,
  onDeactivate,
}) => {
  const { t } = useTranslation('rfid');

  return (
    <>
      <ActionButton
        actionType="primary"
        size="medium"
        startIcon={<NfcIcon />}
        onClick={onActivate}
        disabled={loading || active}
      >
        {t('learn_mode')}
      </ActionButton>

      {/* Full-screen overlay while waiting for a tag */}
      <Dialog
        open={active}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3, textAlign: 'center' } }}
      >
        <DialogContent sx={{ py: 5, px: 4, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
          <Box
            sx={{
              width: 96,
              height: 96,
              borderRadius: '50%',
              bgcolor: 'primary.light',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              mb: 1,
            }}
          >
            {loading ? (
              <CircularProgress size={48} />
            ) : (
              <NfcIcon
                sx={{
                  fontSize: 52,
                  color: 'primary.contrastText',
                  animation: `${pulse} 1.5s ease-in-out infinite`,
                }}
              />
            )}
          </Box>

          <Typography variant="h6" fontWeight={700}>
            {loading ? t('learn_mode_waiting') : t('learn_mode_active')}
          </Typography>

          <Typography variant="body2" color="text.secondary">
            {t('learn_mode_waiting')}
          </Typography>

          <ActionButton
            actionType="secondary"
            startIcon={<CancelIcon />}
            onClick={onDeactivate}
          >
            {t('learn_mode_cancel')}
          </ActionButton>
        </DialogContent>
      </Dialog>
    </>
  );
};
