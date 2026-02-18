import React from 'react';
import { Box, LinearProgress, Typography } from '@mui/material';
import { formatTime } from '@/utils/formatTime';

interface ProgressBarProps {
  positionMs: number;
  durationMs: number | null | undefined;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ positionMs, durationMs }) => {
  const progress =
    durationMs && durationMs > 0 ? Math.min((positionMs / durationMs) * 100, 100) : 0;

  return (
    <Box sx={{ width: '100%', px: 1 }}>
      <LinearProgress
        variant="determinate"
        value={progress}
        sx={{
          height: 6,
          borderRadius: 3,
          backgroundColor: 'action.hover',
          '& .MuiLinearProgress-bar': { borderRadius: 3 },
        }}
      />
      <Box display="flex" justifyContent="space-between" mt={0.5}>
        <Typography variant="caption" color="text.secondary">
          {formatTime(positionMs)}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {formatTime(durationMs)}
        </Typography>
      </Box>
    </Box>
  );
};
