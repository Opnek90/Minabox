import React, { useCallback, useState } from 'react';
import { Box, Slider, Tooltip, Typography } from '@mui/material';
import VolumeDownIcon from '@mui/icons-material/VolumeDown';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import VolumeMuteIcon from '@mui/icons-material/VolumeMute';
import { useTranslation } from 'react-i18next';

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
  const [localVolume, setLocalVolume] = useState<number>(volume);

  // Sync with external state when it changes significantly
  React.useEffect(() => {
    setLocalVolume(volume);
  }, [volume]);

  const handleChange = useCallback(
    (_: Event, value: number | number[]) => {
      const v = Array.isArray(value) ? value[0] : value;
      setLocalVolume(v);
    },
    []
  );

  const handleChangeCommitted = useCallback(
    (_: React.SyntheticEvent | Event, value: number | number[]) => {
      const v = Array.isArray(value) ? value[0] : value;
      onVolumeChange(v);
    },
    [onVolumeChange]
  );

  const VolumeIcon =
    localVolume <= minVolume ? VolumeMuteIcon : localVolume < 50 ? VolumeDownIcon : VolumeUpIcon;

  return (
    <Box display="flex" alignItems="center" gap={1} sx={{ width: '100%', px: 1 }}>
      <Tooltip title={t('volume')}>
        <VolumeIcon color="action" />
      </Tooltip>
      <Slider
        value={localVolume}
        min={minVolume}
        max={maxVolume}
        step={1}
        onChange={handleChange}
        onChangeCommitted={handleChangeCommitted}
        aria-label={t('volume')}
        sx={{ flex: 1 }}
      />
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 36, textAlign: 'right' }}>
        {localVolume}%
      </Typography>
    </Box>
  );
};
