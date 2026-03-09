import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, Slider, Typography } from '@mui/material';
import { formatTime } from '@/utils/formatTime';

interface ProgressBarProps {
  positionMs: number;
  durationMs: number | null | undefined;
  /** Called with the target position in ms when the user finishes dragging / clicks. */
  onSeek?: (positionMs: number) => void;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ positionMs, durationMs, onSeek }) => {
  const seekable = Boolean(onSeek && durationMs && durationMs > 0);

  // During drag we show the dragged value; after commit we reset to null so
  // the real position from props takes over again.
  const [dragging, setDragging] = useState<number | null>(null);
  const commitTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset optimistic value once the real position catches up (within 2 s).
  useEffect(() => {
    if (dragging === null) return;
    commitTimeout.current = setTimeout(() => setDragging(null), 2000);
    return () => {
      if (commitTimeout.current) clearTimeout(commitTimeout.current);
    };
  }, [positionMs]);

  const displayMs = dragging !== null ? dragging : positionMs;
  const value = durationMs && durationMs > 0 ? Math.min((displayMs / durationMs) * 100, 100) : 0;

  const handleChange = useCallback(
    (_: Event, newValue: number | number[]) => {
      if (!seekable || !durationMs) return;
      const pct = Array.isArray(newValue) ? newValue[0] : newValue;
      setDragging(Math.round((pct / 100) * durationMs));
    },
    [seekable, durationMs],
  );

  const handleChangeCommitted = useCallback(
    (_: React.SyntheticEvent | Event, newValue: number | number[]) => {
      if (!seekable || !durationMs || !onSeek) return;
      const pct = Array.isArray(newValue) ? newValue[0] : newValue;
      const targetMs = Math.round((pct / 100) * durationMs);
      setDragging(targetMs);
      onSeek(targetMs);
    },
    [seekable, durationMs, onSeek],
  );

  return (
    <Box sx={{ width: '100%', px: 1 }}>
      <Slider
        value={value}
        min={0}
        max={100}
        step={0.1}
        onChange={handleChange}
        onChangeCommitted={handleChangeCommitted}
        disabled={!seekable}
        aria-label="Playback position"
        size="small"
        sx={{
          display: 'block',
          height: 6,
          padding: '10px 0',
          color: seekable ? 'primary.main' : 'action.disabled',
          '& .MuiSlider-thumb': {
            width: seekable ? 14 : 0,
            height: seekable ? 14 : 0,
            transition: 'none',
          },
          '& .MuiSlider-track': { transition: 'none', borderRadius: 3 },
          '& .MuiSlider-rail': { borderRadius: 3, opacity: 0.3 },
        }}
      />
      <Box display="flex" justifyContent="space-between" mt={-0.5}>
        <Typography variant="caption" color="text.secondary">
          {formatTime(displayMs)}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {formatTime(durationMs)}
        </Typography>
      </Box>
    </Box>
  );
};
