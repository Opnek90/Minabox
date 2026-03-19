import React from 'react';
import { Box, Divider, Typography } from '@mui/material';

interface SettingsSectionProps {
  title: string;
  children: React.ReactNode;
}

export const SettingsSection: React.FC<SettingsSectionProps> = ({ title, children }) => (
  <Box sx={{ mb: 4 }}>
    <Typography variant="subtitle1" fontWeight={600} gutterBottom>
      {title}
    </Typography>
    <Divider sx={{ mb: 2.5 }} />
    {children}
  </Box>
);
