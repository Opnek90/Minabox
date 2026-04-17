import React, { useMemo } from 'react';
import { Box, Slider, Typography } from '@mui/material';

interface VolumeSliderProps {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  snapToStep?: boolean;
  label?: string;
  onChange: (value: number) => void;
}

/**
 * Shared volume slider component.
 * Defaults to 5-step increments and automatically snaps incoming
 * values (e.g. previously stored uneven config values) to the
 * nearest multiple of `step` before display.
 */
export const VolumeSlider: React.FC<VolumeSliderProps> = ({
  value,
  min = 0,
  max = 100,
  step = 5,
  snapToStep = true,
  label,
  onChange,
}) => {
  const snapped = useMemo(() => {
    if (!snapToStep || step <= 0) return value;
    return Math.round(value / step) * step;
  }, [value, step, snapToStep]);

  const clamped = Math.max(min, Math.min(max, snapped));

  return (
    <Box>
      {label && (
        <Typography variant="body2" gutterBottom>
          {label}: {clamped}%
        </Typography>
      )}
      <Slider
        value={clamped}
        min={min}
        max={max}
        step={step}
        marks
        valueLabelDisplay="auto"
        onChange={(_, v) => onChange(Array.isArray(v) ? v[0] : v)}
      />
    </Box>
  );
};
