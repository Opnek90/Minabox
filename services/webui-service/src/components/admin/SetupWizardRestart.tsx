import React from 'react';
import { Box, Button, Stack, Typography } from '@mui/material';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

/**
 * Startet den Ersteinrichtungs-Assistenten erneut.
 *
 * Nuetzlich nach einem Hardware-Umbau oder wenn die Box weitergegeben wird.
 * Die bestehenden Werte bleiben erhalten und sind in den Schritten
 * vorausgefuellt - der Assistent setzt nichts zurueck.
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
