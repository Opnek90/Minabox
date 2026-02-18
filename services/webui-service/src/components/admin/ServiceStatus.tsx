import React from 'react';
import { Box, Chip, Typography } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { useTranslation } from 'react-i18next';
import type { ServiceStatus as ServiceStatusType } from '@/types/api';

interface ServiceStatusProps {
  service: ServiceStatusType;
}

export const ServiceStatusCard: React.FC<ServiceStatusProps> = ({ service }) => {
  const { t } = useTranslation('admin');

  const stateConfig = {
    online: { color: 'success' as const, icon: <CheckCircleIcon fontSize="small" />, label: t('system.status_online') },
    offline: { color: 'default' as const, icon: <HelpOutlineIcon fontSize="small" />, label: t('system.status_offline') },
    error: { color: 'error' as const, icon: <ErrorIcon fontSize="small" />, label: t('system.status_error') },
  };

  const config = stateConfig[service.state] ?? stateConfig.offline;

  return (
    <Box
      display="flex"
      alignItems="center"
      justifyContent="space-between"
      sx={{
        p: 1.5,
        borderRadius: 1,
        border: '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
    >
      <Typography variant="body2" fontWeight={500} sx={{ textTransform: 'capitalize' }}>
        {service.service}
      </Typography>
      <Chip
        icon={config.icon}
        label={config.label}
        color={config.color}
        size="small"
        variant="outlined"
      />
    </Box>
  );
};
