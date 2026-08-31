import React from 'react';
import { Box, Typography } from '@mui/material';

interface SettingsBlockProps {
  title: string;
  /** Short explanation under the title - full sentences belong here, not in the title. */
  description?: string;
  children: React.ReactNode;
}

/**
 * Third level of the settings page: a thematic block *inside* a
 * `SettingsSection`.
 *
 * Every form used to reinvent this level - the codebase had four variants side
 * by side (`overline` with and without `text.secondary`, `subtitle1` bold in a
 * Paper, `subtitle2` secondary), sometimes two of them in the same file.
 * Explanatory text hung sometimes as a `caption` under the title, sometimes as
 * `body2` under the field.
 *
 * Rules this component enforces:
 * - Every block has a title - including the first of a section. The first
 *   fields of a section regularly stood there without a heading and you had to
 *   guess what they belonged to.
 * - Explanatory text sits directly under the title, never under the field.
 * - The title does not repeat the name of its group or section.
 */
export const SettingsBlock: React.FC<SettingsBlockProps> = ({
  title,
  description,
  children,
}) => (
  <Box sx={{ mb: 3 }}>
    <Typography
      variant="overline"
      color="text.secondary"
      sx={{ display: 'block', lineHeight: 1.6 }}
    >
      {title}
    </Typography>
    {description && (
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: 'block', mb: 0.5 }}
      >
        {description}
      </Typography>
    )}
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
      {children}
    </Box>
  </Box>
);
