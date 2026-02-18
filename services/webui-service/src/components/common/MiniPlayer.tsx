import React from 'react';
import { Box, IconButton, LinearProgress, Paper, Tooltip, Typography } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import StopIcon from '@mui/icons-material/Stop';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAudioStatus } from '@/hooks/useAudioStatus';
import { audioApi } from '@/api/audio';

export const MiniPlayer: React.FC = () => {
  const { t } = useTranslation('player');
  const navigate = useNavigate();
  const audioStatus = useAudioStatus();

  if (!audioStatus || audioStatus.state === 'stopped') return null;

  const { state, track_title, track_artist, position_ms, duration_ms } = audioStatus;
  const progress = duration_ms && duration_ms > 0 ? (position_ms / duration_ms) * 100 : 0;

  return (
    <Paper
      elevation={8}
      sx={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 1200,
        borderRadius: 0,
        borderTop: 1,
        borderColor: 'divider',
      }}
    >
      {/* Progress bar at top edge */}
      {duration_ms && duration_ms > 0 && (
        <LinearProgress
          variant="determinate"
          value={progress}
          sx={{ height: 3, borderRadius: 0 }}
        />
      )}

      <Box
        display="flex"
        alignItems="center"
        gap={1.5}
        px={2}
        py={1}
        sx={{ cursor: 'pointer' }}
        onClick={() => navigate('/player')}
      >
        {/* Icon */}
        <MusicNoteIcon fontSize="small" color="primary" sx={{ flexShrink: 0 }} />

        {/* Track info */}
        <Box flex={1} minWidth={0}>
          <Typography
            variant="body2"
            fontWeight={600}
            noWrap
            sx={{ lineHeight: 1.2 }}
          >
            {track_title ?? t('unknown_track')}
          </Typography>
          {track_artist && (
            <Typography variant="caption" color="text.secondary" noWrap>
              {track_artist}
            </Typography>
          )}
        </Box>

        {/* Controls */}
        <Box display="flex" alignItems="center" onClick={(e) => e.stopPropagation()}>
          <Tooltip title={state === 'playing' ? t('controls.pause') : t('controls.play')}>
            <IconButton
              size="small"
              onClick={() => (state === 'playing' ? audioApi.pause() : audioApi.play())}
            >
              {state === 'playing' ? (
                <PauseIcon fontSize="small" />
              ) : (
                <PlayArrowIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
          <Tooltip title={t('controls.stop')}>
            <IconButton size="small" onClick={() => audioApi.stop()}>
              <StopIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>
    </Paper>
  );
};
