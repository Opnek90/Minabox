import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, Slider, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatTime } from '@/utils/formatTime';

interface ProgressBarProps {
  positionMs: number;
  durationMs: number | null | undefined;
  /** Called with the target position in ms when the user finishes dragging / clicks. */
  onSeek?: (positionMs: number) => void;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ positionMs, durationMs, onSeek }) => {
  const { t } = useTranslation('player');
  const seekable = Boolean(onSeek && durationMs && durationMs > 0);

  // During drag we show the dragged value; after commit we keep showing the
  // target until the reported position catches up or 2 s have elapsed.
  const [dragging, setDragging] = useState<number | null>(null);
  const activelyDraggingRef = useRef(false);
  const commitTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (commitTimeout.current) clearTimeout(commitTimeout.current);
    };
  }, []);

  useEffect(() => {
    if (dragging === null || activelyDraggingRef.current) return;
    if (Math.abs(positionMs - dragging) <= 1500) {
      if (commitTimeout.current) {
        clearTimeout(commitTimeout.current);
        commitTimeout.current = null;
      }
      setDragging(null);
    }
  }, [positionMs, dragging]);

  const displayMs = dragging !== null ? dragging : positionMs;
  const value = durationMs && durationMs > 0 ? Math.min((displayMs / durationMs) * 100, 100) : 0;

  const handleChange = useCallback(
    (_: Event, newValue: number | number[]) => {
      if (!seekable || !durationMs) return;
      activelyDraggingRef.current = true;
      if (commitTimeout.current) {
        clearTimeout(commitTimeout.current);
        commitTimeout.current = null;
      }
      const pct = Array.isArray(newValue) ? newValue[0] : newValue;
      setDragging(Math.round((pct / 100) * durationMs));
    },
    [seekable, durationMs],
  );

  const handleChangeCommitted = useCallback(
    (_: React.SyntheticEvent | Event, newValue: number | number[]) => {
      activelyDraggingRef.current = false;
      if (!seekable || !durationMs || !onSeek) return;
      const pct = Array.isArray(newValue) ? newValue[0] : newValue;
      const targetMs = Math.round((pct / 100) * durationMs);
      setDragging(targetMs);
      if (commitTimeout.current) clearTimeout(commitTimeout.current);
      commitTimeout.current = setTimeout(() => {
        commitTimeout.current = null;
        setDragging(null);
      }, 2000);
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
        aria-label={t('position')}
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
