import React from 'react';
import { Box, Button, Stack, Typography } from '@mui/material';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

/**
 * Starts the first-run wizard again.
 *
 * Useful after a hardware change or when the box is passed on. The existing
 * values are kept and are pre-filled in the steps - the wizard resets nothing.
 */
export const SetupWizardRestart: React.FC = () => {
  const { t } = useTranslation('setup');
  const navigate = useNavigate();

  return (
    <Stack spacing={1}>
      <Typography variant="body2" color="text.secondary">
        {t('subtitle')}
      </Typography>
      <Box>
        <Button
          variant="outlined"
          startIcon={<RestartAltIcon />}
          onClick={() => navigate('/setup')}
        >
          {t('title')}
        </Button>
      </Box>
    </Stack>
  );
};
