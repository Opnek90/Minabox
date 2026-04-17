import React, { useCallback, useMemo, useState } from 'react';
import { Box, Tooltip, Typography } from '@mui/material';
import VolumeDownIcon from '@mui/icons-material/VolumeDown';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import VolumeMuteIcon from '@mui/icons-material/VolumeMute';
import { useTranslation } from 'react-i18next';
import { VolumeSlider } from '@/components/ui/VolumeSlider';

interface VolumeControlProps {
  volume: number;
  minVolume?: number;
  maxVolume?: number;
  onVolumeChange: (volume: number) => void;
}

export const VolumeControl: React.FC<VolumeControlProps> = ({
  volume,
  minVolume = 0,
  maxVolume = 100,
  onVolumeChange,
}) => {
  const { t } = useTranslation('player');

  // Snap incoming volume to nearest 5-step for local display
  const snappedInitial = useMemo(() => Math.round(volume / 5) * 5, [volume]);
  const [localVolume, setLocalVolume] = useState<number>(snappedInitial);

  React.useEffect(() => {
    setLocalVolume(Math.round(volume / 5) * 5);
  }, [volume]);

  const handleChange = useCallback((v: number) => {
    setLocalVolume(v);
    onVolumeChange(v);
  }, [onVolumeChange]);

  const VolumeIcon =
    localVolume <= minVolume ? VolumeMuteIcon : localVolume < 50 ? VolumeDownIcon : VolumeUpIcon;

  return (
    <Box display="flex" alignItems="center" gap={1} sx={{ width: '100%', px: 1 }}>
      <Tooltip title={t('volume')}>
        <VolumeIcon color="action" />
      </Tooltip>
      <VolumeSlider
        value={localVolume}
        min={minVolume}
        max={maxVolume}
        onChange={handleChange}
      />
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 36, textAlign: 'right' }}>
        {localVolume}%
      </Typography>
    </Box>
  );
};
