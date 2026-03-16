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
        // Kein overflowX:hidden hier – das wuerde Badges und Buttons abschneiden.
        // Breiten-Overflow wird stattdessen per minWidth:0 auf Grid/Flex-Kinder verhindert.
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
