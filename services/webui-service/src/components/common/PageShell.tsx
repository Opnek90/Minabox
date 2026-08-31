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
  // `isCompact` covers phone *and* tablet: the title may wrap there and
  // actions may move to the next line. The padding, by contrast, is staggered
  // in three levels, because a 24px margin on an 834px tablet costs noticeable
  // width.
  const { isMobile, isCompact, pagePadding } = useLayout();

  return (
    <Box
      sx={{
        pt: pagePadding,
        pr: pagePadding,
        pb: pagePadding,
        // From tablet up the navigation sits permanently on the left as a
        // rail/drawer - a full page margin is no longer needed there; on mobile
        // (no sidebar) it stays at the full value.
        pl: isMobile ? pagePadding : pagePadding / 2,
        maxWidth: maxWidth ?? 'none',
        mx: maxWidth ? 'auto' : undefined,
        // No overflowX:hidden here - that would clip badges and buttons. Width
        // overflow is prevented instead via minWidth:0 on grid/flex children.
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
