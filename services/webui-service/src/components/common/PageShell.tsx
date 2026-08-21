import React from 'react';
import { Box, Typography } from '@mui/material';
import { useLayout } from '@/hooks/useLayout';

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
  // `isCompact` deckt Handy *und* Tablet ab: der Titel darf dort umbrechen und
  // Aktionen duerfen in die naechste Zeile. Die Polsterung staffelt dagegen
  // dreistufig, weil 24px Rand auf einem 834px-Tablet spuerbar Breite kostet.
  const { isMobile, isCompact, pagePadding } = useLayout();

  return (
    <Box
      sx={{
        pt: pagePadding,
        pr: pagePadding,
        pb: pagePadding,
        // Ab Tablet steht die Navigation als Rail/Drawer permanent links -
        // dort braucht es keinen vollen Seitenrand mehr, auf Mobil (keine
        // Sidebar) bleibt es beim vollen Wert.
        pl: isMobile ? pagePadding : pagePadding / 2,
        maxWidth: maxWidth ?? 'none',
        mx: maxWidth ? 'auto' : undefined,
        // Kein overflowX:hidden hier – das wuerde Badges und Buttons abschneiden.
        // Breiten-Overflow wird stattdessen per minWidth:0 auf Grid/Flex-Kinder verhindert.
      }}
    >
      {/* Title row */}
      <Box
        display="flex"
        alignItems={isCompact ? 'flex-start' : 'center'}
        justifyContent="space-between"
        flexWrap="wrap"
        gap={1}
        mb={2.5}
      >
        <Typography
          variant={isMobile ? 'h6' : 'h5'}
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
              flex: isMobile ? '1 1 100%' : '0 0 auto',
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
