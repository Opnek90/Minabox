import React, { useCallback, useState } from 'react';
import { Box, IconButton, Tooltip, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import SkipPreviousIcon from '@mui/icons-material/SkipPrevious';
import StopIcon from '@mui/icons-material/Stop';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAudioStatus } from '@/hooks/useAudioStatus';
import { audioApi } from '@/api/audio';

export const KioskPage: React.FC = () => {
  const { t } = useTranslation('player');
  const navigate = useNavigate();
  const audioStatus = useAudioStatus();
  const [loading, setLoading] = useState(false);

  const handleAction = useCallback(async (fn: () => Promise<void>) => {
    setLoading(true);
    try { await fn(); } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  const state = audioStatus?.state ?? 'stopped';
  const title = audioStatus?.track_title ?? (state !== 'stopped' ? t('unknown_track') : t('nothing_playing'));
  const artist = audioStatus?.track_artist;

  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        bgcolor: 'background.default',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4,
        p: 4,
        zIndex: 1300,
      }}
    >
      {/* Exit button */}
      <Box sx={{ position: 'absolute', top: 16, right: 16 }}>
        <Tooltip title={t('kiosk_exit')}>
          <IconButton
            onClick={() => navigate('/player')}
            size="large"
            sx={{ bgcolor: 'action.hover' }}
          >
            <CloseIcon />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Album art placeholder */}
      <Box
        sx={{
          width: { xs: 180, sm: 240 },
          height: { xs: 180, sm: 240 },
          borderRadius: 4,
          bgcolor: 'primary.main',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: 8,
        }}
      >
        <MusicNoteIcon sx={{ fontSize: 96, color: 'primary.contrastText', opacity: 0.7 }} />
      </Box>

      {/* Track info */}
      <Box textAlign="center" maxWidth={480}>
        <Typography variant="h4" fontWeight={700} gutterBottom>
          {title}
        </Typography>
        {artist && (
          <Typography variant="h6" color="text.secondary">
            {artist}
          </Typography>
        )}
      </Box>

      {/* Controls */}
      <Box display="flex" alignItems="center" gap={2}>
        <IconButton
          onClick={() => handleAction(audioApi.previous)}
          disabled={loading}
          sx={{ width: 64, height: 64 }}
        >
          <SkipPreviousIcon sx={{ fontSize: 40 }} />
        </IconButton>

        <IconButton
          onClick={() => handleAction(state === 'playing' ? audioApi.pause : audioApi.play)}
          disabled={loading}
          color="primary"
          sx={{
            width: 96,
            height: 96,
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            '&:hover': { bgcolor: 'primary.dark' },
            '&:disabled': { bgcolor: 'action.disabled' },
          }}
        >
          {state === 'playing' ? (
            <PauseIcon sx={{ fontSize: 56 }} />
          ) : (
            <PlayArrowIcon sx={{ fontSize: 56 }} />
          )}
        </IconButton>

        <IconButton
          onClick={() => handleAction(audioApi.next)}
          disabled={loading}
          sx={{ width: 64, height: 64 }}
        >
          <SkipNextIcon sx={{ fontSize: 40 }} />
        </IconButton>
      </Box>

      <IconButton
        onClick={() => handleAction(audioApi.stop)}
        disabled={loading || state === 'stopped'}
        size="large"
      >
        <StopIcon sx={{ fontSize: 32 }} />
      </IconButton>
    </Box>
  );
};
