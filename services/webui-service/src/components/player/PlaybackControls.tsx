import React from 'react';
import { Box, CircularProgress, IconButton, Tooltip } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import StopIcon from '@mui/icons-material/Stop';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import SkipPreviousIcon from '@mui/icons-material/SkipPrevious';
import { useTranslation } from 'react-i18next';
import type { AudioState } from '@/types/api';

interface PlaybackControlsProps {
  state: AudioState;
  onPlay: () => void;
  onPause: () => void;
  onStop: () => void;
  onNext: () => void;
  onPrevious: () => void;
  loading?: boolean;
}

export const PlaybackControls: React.FC<PlaybackControlsProps> = ({
  state,
  onPlay,
  onPause,
  onStop,
  onNext,
  onPrevious,
  loading = false,
}) => {
  const { t } = useTranslation('player');
  const isPlaying = state === 'playing';
  const isStopped = state === 'stopped';

  return (
    <Box display="flex" alignItems="center" justifyContent="center" gap={1}>
      <Tooltip title={t('controls.previous')}>
        <span>
          <IconButton
            onClick={onPrevious}
            disabled={loading || isStopped}
            size="large"
            color="inherit"
          >
            <SkipPreviousIcon fontSize="large" />
          </IconButton>
        </span>
      </Tooltip>

      <Tooltip title={isPlaying ? t('controls.pause') : t('controls.play')}>
        <span>
          <IconButton
            onClick={isPlaying ? onPause : onPlay}
            disabled={loading}
            size="large"
            color="primary"
            sx={{
              bgcolor: 'primary.main',
              color: 'primary.contrastText',
              width: 64,
              height: 64,
              '&:hover': { bgcolor: 'primary.dark' },
              '&.Mui-disabled': { bgcolor: 'action.disabledBackground' },
            }}
          >
            {loading ? (
              <CircularProgress size={28} color="inherit" />
            ) : isPlaying ? (
              <PauseIcon sx={{ fontSize: 32 }} />
            ) : (
              <PlayArrowIcon sx={{ fontSize: 32 }} />
            )}
          </IconButton>
        </span>
      </Tooltip>

      <Tooltip title={t('controls.stop')}>
        <span>
          <IconButton
            onClick={onStop}
            disabled={loading || isStopped}
            size="large"
            color="inherit"
          >
            <StopIcon fontSize="large" />
          </IconButton>
        </span>
      </Tooltip>

      <Tooltip title={t('controls.next')}>
        <span>
          <IconButton
            onClick={onNext}
            disabled={loading || isStopped}
            size="large"
            color="inherit"
          >
            <SkipNextIcon fontSize="large" />
          </IconButton>
        </span>
      </Tooltip>
    </Box>
  );
};
