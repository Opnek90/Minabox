import React from 'react';
import { Box, Divider, Typography } from '@mui/material';

interface SettingsSectionProps {
  title: string;
  /** Short explanation under the title - as in `SettingsBlock`, one level up. */
  description?: string;
  children: React.ReactNode;
}

/**
 * Second level of the settings page: a section within a group. The blocks
 * inside it are rendered by `SettingsBlock`.
 *
 * The width limit deliberately sits here instead of in the forms: only 6 of 21
 * panels used to limit to 560px, the rest ran across the full width - on the
 * desktop that left a narrow form directly next to an edge-to-edge panel.
 */
export const SettingsSection: React.FC<SettingsSectionProps> = ({
  title,
  description,
  children,
}) => (
  <Box sx={{ mb: 4, maxWidth: 720 }}>
    <Typography variant="subtitle1" fontWeight={600} gutterBottom={!description}>
      {title}
    </Typography>
    {description && (
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        {description}
      </Typography>
    )}
    <Divider sx={{ mb: 2.5 }} />
    {children}
  </Box>
);
