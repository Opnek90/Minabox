import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Fade,
  IconButton,
  List,
  ListItemButton,
  Popover,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import HotelIcon from '@mui/icons-material/Hotel';
import CancelIcon from '@mui/icons-material/Cancel';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { TrackInfo } from '@/components/player/TrackInfo';
import { PlaybackControls } from '@/components/player/PlaybackControls';
import { ProgressBar } from '@/components/player/ProgressBar';
import { VolumeControl } from '@/components/player/VolumeControl';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useToast } from '@/contexts/ToastContext';
import { useAudioStatus } from '@/hooks/useAudioStatus';
import { useWebSocket } from '@/contexts/WebSocketContext';
import { audioApi } from '@/api/audio';
import { configApi } from '@/api/config';
import type { AudioConfig } from '@/types/api';


const SLEEP_PRESETS = [15, 30, 45, 60];

const BUTTON_ACTION_LABELS: Record<string, string> = {
  play_pause:         '⏯ Play / Pause',
  next:               '⏭ Next',
  prev:               '⏮ Previous',
  volume_up:          '🔊 Volume +',
  volume_down:        '🔉 Volume –',
  mute_toggle:        '🔇 Mute',
  stop:               '⏹ Stop',
  sleep_timer_toggle: '🌙 Sleep Timer',
};


export const PlayerPage: React.FC = () => {
  const { t } = useTranslation('player');
  const { showError } = useToast();
  const theme = useTheme();
  const isSmall = useMediaQuery(theme.breakpoints.down('sm'));
  const navigate = useNavigate();
  const audioStatus = useAudioStatus();
  const { lastMessage } = useWebSocket();
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioConfig, setAudioConfig] = useState<AudioConfig | null>(null);
  const [optimisticVolume, setOptimisticVolume] = useState<number | null>(null);
  const optimisticTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [sleepAnchor, setSleepAnchor] = useState<HTMLElement | null>(null);
  const [sleepRemainingMs, setSleepRemainingMs] = useState<number | null>(null);
  const sleepDisplayRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [buttonFeedback, setButtonFeedback] = useState<string | null>(null);
  const buttonFeedbackTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    configApi.getAudio().then(setAudioConfig).catch(() => null);
    audioApi.getSleepTimer().then((status) => {
      if (status.active && status.remaining_ms !== null) {
        startDisplayCountdown(status.remaining_ms);
      }
    }).catch(() => null);
  }, []);

  useEffect(() => {
    return () => {
      if (optimisticTimeoutRef.current) clearTimeout(optimisticTimeoutRef.current);
      if (sleepDisplayRef.current) clearInterval(sleepDisplayRef.current);
      if (buttonFeedbackTimeout.current) clearTimeout(buttonFeedbackTimeout.current);
    };
  }, []);

  useEffect(() => {
    if (audioStatus?.volume == null || optimisticVolume === null) return;
    if (Math.abs(audioStatus.volume - optimisticVolume) <= 2) {
      setOptimisticVolume(null);
      if (optimisticTimeoutRef.current) {
        clearTimeout(optimisticTimeoutRef.current);
        optimisticTimeoutRef.current = null;
      }
    }
  }, [audioStatus?.volume, optimisticVolume]);

  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === 'sleep_timer_status') {
      const status = lastMessage.data as { active: boolean; remaining_ms: number | null };
      if (status.active && status.remaining_ms !== null) {
        startDisplayCountdown(status.remaining_ms);
      } else {
        stopDisplayCountdown();
      }
    } else if (lastMessage.type === 'button_action') {
      const action = (lastMessage.data as { action?: string }).action ?? '';
      const actionKey = action.replace(/-/g, '_');
      const label = BUTTON_ACTION_LABELS[actionKey] ?? BUTTON_ACTION_LABELS[action] ?? action;
      setButtonFeedback(label);
      if (buttonFeedbackTimeout.current) clearTimeout(buttonFeedbackTimeout.current);
      buttonFeedbackTimeout.current = setTimeout(() => setButtonFeedback(null), 1800);
    }
  }, [lastMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  const startDisplayCountdown = (initialMs: number) => {
    if (sleepDisplayRef.current) clearInterval(sleepDisplayRef.current);
    const endMs = Date.now() + initialMs;
    setSleepRemainingMs(initialMs);
    setSleepAnchor(null);
    sleepDisplayRef.current = setInterval(() => {
      const remaining = endMs - Date.now();
      if (remaining <= 0) {
        if (sleepDisplayRef.current) clearInterval(sleepDisplayRef.current);
        setSleepRemainingMs(null);
      } else {
        setSleepRemainingMs(remaining);
      }
    }, 1000);
  };

  const stopDisplayCountdown = () => {
    if (sleepDisplayRef.current) clearInterval(sleepDisplayRef.current);
    setSleepRemainingMs(null);
  };

  const handleStartSleepTimer = (minutes: number) => {
    setSleepAnchor(null);
    audioApi.startSleepTimer(minutes).catch(() =>
      showError(t('sleep_timer.error', { defaultValue: 'Sleep Timer konnte nicht gesetzt werden' }))
    );
  };

  const handleCancelSleepTimer = () => {
    audioApi.cancelSleepTimer().catch(() =>
      showError(t('sleep_timer.cancel_error', { defaultValue: 'Sleep Timer konnte nicht abgebrochen werden' }))
    );
  };

  const formatSleepRemaining = (ms: number) => {
    const m = Math.floor(ms / 60_000);
    const s = Math.floor((ms % 60_000) / 1000);
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  const handleAction = useCallback(async (fn: () => Promise<void>) => {
    setActionLoading(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error';
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  }, []);

  const handlePlay     = () => handleAction(audioApi.play);
  const handlePause    = () => handleAction(audioApi.pause);
  const handleStop     = () => handleAction(audioApi.stop);
  const handleNext     = () => handleAction(audioApi.next);
  const handlePrevious = () => handleAction(audioApi.previous);

  const handleVolumeChange = useCallback((volume: number) => {
    setOptimisticVolume(volume);
    if (optimisticTimeoutRef.current) clearTimeout(optimisticTimeoutRef.current);
    optimisticTimeoutRef.current = setTimeout(() => setOptimisticVolume(null), 4000);
    handleAction(() => audioApi.setVolume(volume));
  }, [handleAction]);

  if (!audioStatus) {
    return <LoadingSpinner message={t('title')} fullPage />;
  }

  const { state, track_title, track_artist, track_album, position_ms, duration_ms, volume } = audioStatus;
  const displayVolume = optimisticVolume ?? volume ?? 0;

  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent={isSmall ? 'flex-start' : 'center'}
      sx={{
        minHeight: isSmall ? 'calc(100vh - 120px)' : '70vh',
        p: isSmall ? 1.5 : 2,
        pb: 2,
      }}
    >
      {error && (
        <Alert
          severity="error"
          onClose={() => setError(null)}
          sx={{ mb: 1.5, width: '100%', maxWidth: 480 }}
        >
          {error}
        </Alert>
      )}

      <Card
        sx={{
          width: '100%',
          maxWidth: 480,
          borderRadius: isSmall ? 2 : 4,
          boxShadow: isSmall ? 2 : 6,
        }}
      >
        <CardContent
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: isSmall ? 1.5 : 2,
            p: isSmall ? 1.5 : 2,
            pb: '16px !important',
          }}
        >
          {/* Status row: state chip + sleep timer + kiosk */}
          <Box display="flex" justifyContent="space-between" alignItems="center" minWidth={0}>
            <Chip
              label={t(`states.${state}`)}
              color={state === 'playing' ? 'success' : state === 'error' ? 'error' : 'default'}
              size="small"
            />
            <Box display="flex" alignItems="center" gap={0.5} flexShrink={0}>
              {sleepRemainingMs !== null ? (
                <Chip
                  icon={<HotelIcon fontSize="small" />}
                  label={formatSleepRemaining(sleepRemainingMs)}
                  size="small"
                  color="primary"
                  variant="outlined"
                  onDelete={handleCancelSleepTimer}
                  deleteIcon={<CancelIcon />}
                />
              ) : (
                <IconButton
                  size="small"
                  onClick={(e) => setSleepAnchor(e.currentTarget)}
                  title={t('sleep_timer.title')}
                >
                  <HotelIcon fontSize="small" />
                </IconButton>
              )}
              <IconButton
                size="small"
                onClick={() => navigate('/kiosk')}
                title={t('kiosk_mode')}
              >
                <FullscreenIcon fontSize="small" />
              </IconButton>
            </Box>
          </Box>

          {/* Sleep timer popover */}
          <Popover
            open={Boolean(sleepAnchor)}
            anchorEl={sleepAnchor}
            onClose={() => setSleepAnchor(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <List dense sx={{ py: 0.5, minWidth: 160 }}>
              {SLEEP_PRESETS.map((min) => (
                <ListItemButton key={min} onClick={() => handleStartSleepTimer(min)}>
                  <Typography variant="body2">
                    {t('sleep_timer.preset', { minutes: min })}
                  </Typography>
                </ListItemButton>
              ))}
            </List>
          </Popover>

          {/* Track Info */}
          <TrackInfo
            title={state !== 'stopped' ? track_title : null}
            artist={state !== 'stopped' ? track_artist : null}
            album={state !== 'stopped' ? track_album : null}
            playlistCurrent={state !== 'stopped' ? (audioStatus.playlist_position ?? null) : null}
            playlistTotal={state !== 'stopped' ? (audioStatus.playlist_total ?? null) : null}
            stopped={state === 'stopped'}
          />

          {/* Progress Bar */}
          <ProgressBar positionMs={position_ms} durationMs={duration_ms} />

          {/* Playback Controls */}
          <PlaybackControls
            state={state}
            onPlay={handlePlay}
            onPause={handlePause}
            onStop={handleStop}
            onNext={handleNext}
            onPrevious={handlePrevious}
            loading={actionLoading}
          />

          {/* Volume Control */}
          <VolumeControl
            volume={displayVolume}
            maxVolume={audioConfig?.max_volume ?? 100}
            onVolumeChange={handleVolumeChange}
          />
        </CardContent>
      </Card>

      {/* Button action feedback overlay */}
      <Fade in={buttonFeedback !== null} timeout={300}>
        <Box
          sx={{
            position: 'fixed',
            bottom: 80,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 1400,
            pointerEvents: 'none',
          }}
        >
          <Chip
            label={buttonFeedback ?? ''}
            color="primary"
            sx={{ fontSize: '1rem', px: 2, py: 0.5, fontWeight: 600, boxShadow: 4 }}
          />
        </Box>
      </Fade>
    </Box>
  );
};
