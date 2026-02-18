import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Card, CardContent, Chip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { TrackInfo } from '@/components/player/TrackInfo';
import { PlaybackControls } from '@/components/player/PlaybackControls';
import { ProgressBar } from '@/components/player/ProgressBar';
import { VolumeControl } from '@/components/player/VolumeControl';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useAudioStatus } from '@/hooks/useAudioStatus';
import { audioApi } from '@/api/audio';
import { configApi } from '@/api/config';
import type { AudioConfig } from '@/types/api';

export const PlayerPage: React.FC = () => {
  const { t } = useTranslation('player');
  const audioStatus = useAudioStatus();
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioConfig, setAudioConfig] = useState<AudioConfig | null>(null);
  // Optimistic volume: show new value immediately when user moves slider; clear when WebSocket confirms
  const [optimisticVolume, setOptimisticVolume] = useState<number | null>(null);
  const optimisticTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load audio config to get max_volume
  useEffect(() => {
    configApi.getAudio().then(setAudioConfig).catch(() => null);
  }, []);

  useEffect(() => {
    return () => {
      if (optimisticTimeoutRef.current) clearTimeout(optimisticTimeoutRef.current);
    };
  }, []);

  // Clear optimistic volume when WebSocket confirms (received volume matches what we set) or after 4s
  useEffect(() => {
    if (audioStatus?.volume == null || optimisticVolume === null) return;
    const received = audioStatus.volume;
    if (Math.abs(received - optimisticVolume) <= 2) {
      setOptimisticVolume(null);
      if (optimisticTimeoutRef.current) {
        clearTimeout(optimisticTimeoutRef.current);
        optimisticTimeoutRef.current = null;
      }
    }
  }, [audioStatus?.volume, optimisticVolume]);

  const handleAction = useCallback(async (fn: () => Promise<void>) => {
    setActionLoading(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler');
    } finally {
      setActionLoading(false);
    }
  }, []);

  const handlePlay = () => handleAction(audioApi.play);
  const handlePause = () => handleAction(audioApi.pause);
  const handleStop = () => handleAction(audioApi.stop);
  const handleNext = () => handleAction(audioApi.next);
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

  const { state, track_title, track_artist, track_album, position_ms, duration_ms, volume } =
    audioStatus;
  const displayVolume = optimisticVolume ?? volume ?? 0;

  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent="center"
      sx={{ minHeight: '70vh', p: 2 }}
    >
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2, width: '100%', maxWidth: 480 }}>
          {error}
        </Alert>
      )}

      <Card sx={{ width: '100%', maxWidth: 480, borderRadius: 4, boxShadow: 6 }}>
        <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pb: '16px !important' }}>
          {/* Status Chip */}
          <Box display="flex" justifyContent="center">
            <Chip
              label={t(`states.${state}`)}
              color={
                state === 'playing' ? 'success' : state === 'error' ? 'error' : 'default'
              }
              size="small"
            />
          </Box>

          {/* Track Info – always visible; shows placeholder when stopped */}
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

          {/* Volume Control: use optimistic volume so slider updates immediately */}
          <VolumeControl
            volume={displayVolume}
            maxVolume={audioConfig?.max_volume ?? 100}
            onVolumeChange={handleVolumeChange}
          />
        </CardContent>
      </Card>
    </Box>
  );
};
