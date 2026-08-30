import React from 'react';
import { Box, Typography } from '@mui/material';

interface StatTileProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  /** Native tooltip for a value that may be truncated. */
  title?: string;
  /** When set, the tile becomes a button. */
  onClick?: () => void;
}

/**
 * One number with a caption and an icon.
 *
 * Was defined twice - once in the parent dashboard, once in the system status -
 * with the same markup and two different sets of props. This is the union of
 * both: `title` and `onClick` are optional, so the plain read-only tile stays a
 * `div` and only a tile that does something becomes a `button`.
 */
export const StatTile: React.FC<StatTileProps> = ({ icon, label, value, title, onClick }) => (
  <Box
    component={onClick ? 'button' : 'div'}
    type={onClick ? 'button' : undefined}
    onClick={onClick}
    sx={{
      display: 'flex',
      alignItems: 'center',
      gap: 1.5,
      p: 1.5,
      m: 0,
      borderRadius: 2,
      bgcolor: 'background.paper',
      border: '1px solid',
      borderColor: 'divider',
      boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
      width: '100%',
      textAlign: 'left',
      font: 'inherit',
      cursor: onClick ? 'pointer' : undefined,
      '&:hover': onClick ? { bgcolor: 'action.hover' } : undefined,
    }}
  >
    <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center', flexShrink: 0 }}>
      {icon}
    </Box>
    <Box minWidth={0}>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600} noWrap title={title}>
        {value}
      </Typography>
    </Box>
  </Box>
);
