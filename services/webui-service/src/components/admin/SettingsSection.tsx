import React from 'react';
import { Box, Divider, Typography } from '@mui/material';
import { HelpTip } from '@/components/ui/HelpTip';

interface SettingsSectionProps {
  title: string;
  /** Short explanation under the title - as in `SettingsBlock`, one level up. */
  description?: string;
  /** Background knowledge behind a question mark - as in `SettingsBlock`. */
  help?: string;
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
  help,
  children,
}) => (
  <Box sx={{ mb: 4, maxWidth: 720 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: description ? 0 : 0.5 }}>
      <Typography variant="subtitle1" fontWeight={600}>
        {title}
      </Typography>
      {help && <HelpTip title={help} label={title} />}
    </Box>
    {description && (
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        {description}
      </Typography>
    )}
    <Divider sx={{ mb: 2.5 }} />
    {children}
  </Box>
);
