import React from 'react';
import {
  Box,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';

interface PageShellProps {
  title: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  maxWidth?: number | string;
}

export const PageShell: React.FC<PageShellProps> = ({
  title,
  actions,
  children,
  maxWidth,
}) => {
  const theme = useTheme();
  const isSmall = useMediaQuery(theme.breakpoints.down('sm'));

  return (
    <Box
      sx={{
        p: isSmall ? 1.5 : 3,
        maxWidth: maxWidth ?? 'none',
        mx: maxWidth ? 'auto' : undefined,
        // Prevent inner content (Grids, Toolbars) from creating horizontal scroll
        overflowX: 'hidden',
      }}
    >
      {/* Title row */}
      <Box
        display="flex"
        alignItems={isSmall ? 'flex-start' : 'center'}
        justifyContent="space-between"
        flexWrap="wrap"
        gap={1}
        mb={2.5}
      >
        <Typography
          variant={isSmall ? 'h6' : 'h5'}
          fontWeight={700}
          sx={{
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: '1 1 0',
            minWidth: 0,
          }}
        >
          {title}
        </Typography>
        {actions && (
          <Box
            display="flex"
            alignItems="center"
            gap={1}
            flexWrap="wrap"
            sx={{
              flex: isSmall ? '1 1 100%' : '0 0 auto',
              // Buttons sollen nie abgeschnitten werden
              overflow: 'visible',
            }}
          >
            {actions}
          </Box>
        )}
      </Box>

      {children}
    </Box>
  );
};
