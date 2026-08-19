import React, { useCallback, useState } from 'react';
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

  // In die erlaubte Skala zwingen: senken die Eltern das Limit unter die
  // laufende Lautstaerke, liefert der Status kurzzeitig (und bei gestopptem
  // Player dauerhaft) einen Wert oberhalb von maxVolume. MUI zeichnet den
  // Slider-Thumb dann ausserhalb der Schiene. Das 5er-Raster wird nach dem
  // Clamp angewendet, damit das Runden nicht wieder ueber das Limit schiebt.
  const snap = useCallback(
    (v: number) => {
      const clamped = Math.min(Math.max(v, minVolume), maxVolume);
      return Math.min(Math.max(Math.round(clamped / 5) * 5, minVolume), maxVolume);
    },
    [minVolume, maxVolume]
  );

  const [localVolume, setLocalVolume] = useState<number>(() => snap(volume));

  React.useEffect(() => {
    setLocalVolume(snap(volume));
  }, [volume, snap]);

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
      <Box sx={{ flex: 1 }}>
        <VolumeSlider
          value={localVolume}
          min={minVolume}
          max={maxVolume}
          onChange={handleChange}
        />
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 36, textAlign: 'right' }}>
        {localVolume}%
      </Typography>
    </Box>
  );
};
