import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Collapse,
  Fade,
  FormControl,
  List,
  ListItemButton,
  MenuItem,
  Select,
  Popover,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import RepeatIcon from '@mui/icons-material/Repeat';
import ShuffleIcon from '@mui/icons-material/Shuffle';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import HotelIcon from '@mui/icons-material/Hotel';
import CancelIcon from '@mui/icons-material/Cancel';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ActionButton } from '@/components/ui/ActionButton';
import { TrackInfo } from '@/components/player/TrackInfo';
import { PlaybackControls } from '@/components/player/PlaybackControls';
import { ProgressBar } from '@/components/player/ProgressBar';
import { VolumeControl } from '@/components/player/VolumeControl';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useToast } from '@/contexts/ToastContext';
import { useAudioStatus } from '@/hooks/useAudioStatus';
import { useWebSocket } from '@/contexts/WebSocketContext';
import { useThemeContext } from '@/contexts/ThemeContext';
import { audioApi } from '@/api/audio';
import { configApi } from '@/api/config';
import type {
  AudioDeviceItem,
  QueueItem,
  RepeatMode,
} from '@/types/api';


const SLEEP_PRESETS = [15, 30, 45, 60];

const UpNextCollapse: React.FC<{ queue: QueueItem[] }> = ({ queue }) => {
  const { t } = useTranslation('player');
  const [expanded, setExpanded] = useState(false);
  const n = queue.length;
  return (
    <Box>
      <ListItemButton
        dense
        onClick={() => setExpanded((e) => !e)}
        sx={{ py: 0.25, minHeight: 32 }}
      >
        <Typography variant="caption" color="text.secondary">
          {t('player.up_next_count', { defaultValue: 'Up next ({{count}})', count: n })}
        </Typography>
        {expanded ? <ExpandLessIcon fontSize="small" sx={{ ml: 0.5 }} /> : <ExpandMoreIcon fontSize="small" sx={{ ml: 0.5 }} />}
      </ListItemButton>
      <Collapse in={expanded}>
        <List dense disablePadding sx={{ maxHeight: 140, overflow: 'auto' }}>
          {queue.map((q) => (
            <ListItemButton key={`${q.track_id}-${q.index}`} dense disableRipple>
              <Typography variant="body2" noWrap>
                {q.title}
                {q.artist ? ` · ${q.artist}` : ''}
              </Typography>
            </ListItemButton>
          ))}
        </List>
      </Collapse>
    </Box>
  );
};

const BUTTON_ACTION_LABELS: Record<string, string> = {
  play_pause:         '⏯ Play / Pause',
  next:               '⏭ Next',
  prev:               '⏮ Previous',
  volume_up:          '🔊 Volume +',
  volume_down:        '🔉 Volume –',
  mute_toggle:        '🔇 Mute',
  stop:               '⏹ Stop',
  sleep_timer_toggle: '🌙 Sleep Timer',
  repeat_cycle:       '🔁 Repeat',
  shuffle_toggle:     '🔀 Shuffle',
  next_output_device: '🔊 Next output device',
};


export const PlayerPage: React.FC = () => {
  const { t } = useTranslation('player');
  const { showError } = useToast();
  const theme = useTheme();
  const isSmall = useMediaQuery(theme.breakpoints.down('sm'));
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const audioStatus = useAudioStatus();
  const { sleepTimerStatus, isConnected } = useWebSocket();
  const { primaryColor } = useThemeContext();
  const [error, setError] = useState<string | null>(null);
  
  const [optimisticVolume, setOptimisticVolume] = useState<number | null>(null);
  const optimisticTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [sleepAnchor, setSleepAnchor] = useState<HTMLElement | null>(null);
  const [sleepRemainingMs, setSleepRemainingMs] = useState<number | null>(null);
  const sleepDisplayRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [buttonFeedback, setButtonFeedback] = useState<string | null>(null);
  const buttonFeedbackTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Queries
  const { data: audioConfig } = useQuery({
    queryKey: ['config', 'audio'],
    queryFn: configApi.getAudio,
    enabled: isConnected,
  });

  const { data: outputDevicesData, isFetching: outputDevicesLoading, refetch: refetchDevices } = useQuery({
    queryKey: ['audio', 'devices'],
    queryFn: () => audioApi.getDevices(true),
    enabled: isConnected,
  });
  
  const outputDevices = outputDevicesData?.devices ?? [];

  // Session query - auto refetch when playing state changes
  const isPlaying = audioStatus?.state === 'playing' || audioStatus?.state === 'paused';
  const { data: session } = useQuery({
    queryKey: ['audio', 'session'],
    queryFn: audioApi.getSession,
    enabled: isConnected && isPlaying,
    staleTime: 10000,
  });

  // Init Sleep Timer countdown from initial fetch or ws
  useEffect(() => {
    if (isConnected) {
      audioApi.getSleepTimer().then((status) => {
        if (status.active && status.remaining_ms !== null) {
          startDisplayCountdown(status.remaining_ms);
        }
      }).catch(() => null);
    }
  }, [isConnected]);

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

  // Handle WebSocket updates
  useEffect(() => {
    if (sleepTimerStatus) {
      if (sleepTimerStatus.active && sleepTimerStatus.remaining_ms !== null) {
        startDisplayCountdown(sleepTimerStatus.remaining_ms);
      } else {
        stopDisplayCountdown();
      }
    }
  }, [sleepTimerStatus]);

  // Hook into generic messages for feedback via custom event
  useEffect(() => {
    const handleWsMessage = (event: Event) => {
      const customEvent = event as CustomEvent;
      const lastMessage = customEvent.detail;
      
      if (lastMessage.type === 'button_action') {
        const action = (lastMessage.data as { action?: string }).action ?? '';
        const actionKey = action.replace(/-/g, '_');
        const label = BUTTON_ACTION_LABELS[actionKey] ?? BUTTON_ACTION_LABELS[action] ?? action;
        setButtonFeedback(label);
        if (buttonFeedbackTimeout.current) clearTimeout(buttonFeedbackTimeout.current);
        buttonFeedbackTimeout.current = setTimeout(() => setButtonFeedback(null), 1800);
      } else if (lastMessage.type === 'repeat_mode') {
        const data = lastMessage.data as { repeat_mode?: RepeatMode };
        if (data?.repeat_mode != null) {
          queryClient.setQueryData(['audio', 'session'], (old: any) => 
            old ? { ...old, repeat_mode: data.repeat_mode } : old
          );
        }
      } else if (lastMessage.type === 'shuffle_mode') {
        const data = lastMessage.data as { shuffle?: boolean };
        if (data?.shuffle !== undefined) {
          queryClient.setQueryData(['audio', 'session'], (old: any) => 
            old ? { ...old, shuffle: Boolean(data.shuffle) } : old
          );
        }
      }
    };

    window.addEventListener('ws_message', handleWsMessage);
    return () => window.removeEventListener('ws_message', handleWsMessage);
  }, [queryClient]);

  // Clear session cache when stopped
  useEffect(() => {
    if (audioStatus?.state === 'stopped' && !audioStatus?.track_id) {
      queryClient.setQueryData(['audio', 'session'], null);
    }
  }, [audioStatus?.state, audioStatus?.track_id, queryClient]);

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

  // Mutations
  const playMutation = useMutation({ mutationFn: audioApi.play });
  const pauseMutation = useMutation({ mutationFn: audioApi.pause });
  const stopMutation = useMutation({ mutationFn: audioApi.stop });
  const nextMutation = useMutation({ mutationFn: audioApi.next });
  const prevMutation = useMutation({ mutationFn: audioApi.previous });
  const seekMutation = useMutation({
    mutationFn: audioApi.seek,
    onError: () => showError(t('player.seek_error', { defaultValue: 'Seek fehlgeschlagen' })),
  });
  
  const volumeMutation = useMutation({ 
    mutationFn: audioApi.setVolume,
    onError: (err: Error) => setError(err instanceof Error ? err.message : 'Error') 
  });
  
  const startSleepTimerMutation = useMutation({
    mutationFn: audioApi.startSleepTimer,
    onError: () => showError(t('sleep_timer.error', { defaultValue: 'Sleep Timer konnte nicht gesetzt werden' }))
  });

  const cancelSleepTimerMutation = useMutation({
    mutationFn: audioApi.cancelSleepTimer,
    onError: () => showError(t('sleep_timer.cancel_error', { defaultValue: 'Sleep Timer konnte nicht abgebrochen werden' }))
  });

  const switchDeviceMutation = useMutation({
    mutationFn: audioApi.switchDevice,
    onSuccess: (_: unknown, variables: string) => {
      queryClient.setQueryData(['config', 'audio'], (old: unknown) => 
        old && typeof old === 'object' && 'output_device_name' in old
          ? { ...(old as Record<string, unknown>), output_device_name: variables }
          : old
      );
    },
    onError: () => showError(t('player.output_device', { defaultValue: 'Could not switch device' }))
  });

  const repeatMutation = useMutation({
    mutationFn: audioApi.setRepeatMode,
    onSuccess: (_: unknown, mode: RepeatMode) => {
      queryClient.setQueryData(['audio', 'session'], (old: unknown) => 
        old && typeof old === 'object' ? { ...(old as Record<string, unknown>), repeat_mode: mode } : old
      );
    }
  });

  const shuffleMutation = useMutation({
    mutationFn: audioApi.setShuffle,
    onSuccess: (_: unknown, shuffle: boolean) => {
      queryClient.setQueryData(['audio', 'session'], (old: unknown) => 
        old && typeof old === 'object' ? { ...(old as Record<string, unknown>), shuffle } : old
      );
    }
  });

  const handleStartSleepTimer = (minutes: number) => {
    setSleepAnchor(null);
    startSleepTimerMutation.mutate(minutes);
  };

  const handleCancelSleepTimer = () => {
    cancelSleepTimerMutation.mutate();
  };

  const formatSleepRemaining = (ms: number) => {
    const m = Math.floor(ms / 60_000);
    const s = Math.floor((ms % 60_000) / 1000);
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  const handlePlay     = () => playMutation.mutate(undefined);
  const handlePause    = () => pauseMutation.mutate();
  const handleStop     = () => stopMutation.mutate();
  const handleNext     = () => nextMutation.mutate();
  const handlePrevious = () => prevMutation.mutate();
  const handleSeek     = useCallback((positionMs: number) => seekMutation.mutate(positionMs), [seekMutation]);

  const handleVolumeChange = useCallback((volume: number) => {
    setOptimisticVolume(volume);
    if (optimisticTimeoutRef.current) clearTimeout(optimisticTimeoutRef.current);
    optimisticTimeoutRef.current = setTimeout(() => setOptimisticVolume(null), 4000);
    volumeMutation.mutate(volume);
  }, [volumeMutation]);

  const actionLoading = playMutation.isPending || pauseMutation.isPending || 
                        stopMutation.isPending || nextMutation.isPending || 
                        prevMutation.isPending;

  if (!audioStatus) {
    return <LoadingSpinner message={t('title')} fullPage />;
  }

  const { state, track_title, track_artist, track_album, track_cover_art_url, position_ms, duration_ms, volume } = audioStatus;
  const displayVolume = optimisticVolume ?? volume ?? 0;
  const canSeek = Boolean(duration_ms && duration_ms > 0);

  // Active-state colorOverride: use accent color from ThemeContext
  const activeColorOverride = { main: primaryColor.main, dark: primaryColor.dark, foreground: primaryColor.contrastText };

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
                <Tooltip title={t('sleep_timer.title')}>
                  <span>
                    <ActionButton
                      actionType="icon"
                      aria-label={t('sleep_timer.title')}
                      onClick={(e) => setSleepAnchor(e.currentTarget)}
                    >
                      <HotelIcon fontSize="small" />
                    </ActionButton>
                  </span>
                </Tooltip>
              )}
              <Tooltip title={t('kiosk_mode')}>
                <span>
                  <ActionButton
                    actionType="icon"
                    aria-label={t('kiosk_mode')}
                    onClick={() => navigate('/kiosk')}
                  >
                    <FullscreenIcon fontSize="small" />
                  </ActionButton>
                </span>
              </Tooltip>
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
            coverArtUrl={state !== 'stopped' ? track_cover_art_url : null}
            playlistCurrent={state !== 'stopped' ? (audioStatus.playlist_position ?? null) : null}
            playlistTotal={state !== 'stopped' ? (audioStatus.playlist_total ?? null) : null}
            stopped={state === 'stopped'}
          />

          {/* Progress Bar */}
          <ProgressBar
            positionMs={position_ms}
            durationMs={duration_ms}
            onSeek={canSeek ? handleSeek : undefined}
          />

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
            minVolume={audioConfig?.min_volume ?? 0}
            maxVolume={audioConfig?.max_volume ?? 100}
            onVolumeChange={handleVolumeChange}
          />

          {/* Output device selector */}
          <Box display="flex" alignItems="center" gap={0.5} sx={{ width: '100%', px: 0.5 }}>
            <FormControl size="small" sx={{ minWidth: 140, flex: 1 }}>
              <Select
                value={audioConfig?.output_device_name ?? ''}
                displayEmpty
                renderValue={(v) => {
                  const d = outputDevices.find((x: AudioDeviceItem) => x.alsa_device === v);
                  return d ? d.name : (v || t('player.output_device', { defaultValue: 'Output device' }));
                }}
                onChange={(e) => {
                  const v = e.target.value as string;
                  if (!v) return;
                  switchDeviceMutation.mutate(v);
                }}
                disabled={outputDevicesLoading || switchDeviceMutation.isPending}
                aria-label={t('player.output_device', { defaultValue: 'Output device' })}
              >
                {outputDevices.map((d: AudioDeviceItem) => (
                  <MenuItem key={d.alsa_device} value={d.alsa_device}>
                    {d.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Tooltip title={t('player.output_device_refresh', { defaultValue: 'Refresh devices' })}>
              <span>
                <ActionButton
                  actionType="icon"
                  onClick={() => refetchDevices()}
                  disabled={outputDevicesLoading}
                  aria-label={t('player.output_device_refresh', { defaultValue: 'Refresh devices' })}
                >
                  <RefreshIcon fontSize="small" />
                </ActionButton>
              </span>
            </Tooltip>
          </Box>

          {/* Repeat + Shuffle (icon buttons) and Up next (collapsible) */}
          {session && (
            <Box sx={{ pt: 0.5, borderTop: 1, borderColor: 'divider' }}>
              <Box display="flex" alignItems="center" gap={0.5} sx={{ mb: 0.5 }}>
                <Tooltip title={session.repeat_mode === 'all'
                  ? t('player.repeat_all', { defaultValue: 'Repeat all' })
                  : t('player.repeat_off', { defaultValue: 'Repeat off' })
                }>
                  <span>
                    <ActionButton
                      actionType="icon"
                      aria-label={session.repeat_mode === 'all' ? 'Repeat all' : 'Repeat off'}
                      colorOverride={session.repeat_mode === 'all' ? activeColorOverride : undefined}
                      onClick={() => {
                        const mode = session.repeat_mode === 'all' ? 'none' : 'all';
                        repeatMutation.mutate(mode);
                      }}
                    >
                      <RepeatIcon fontSize="small" />
                    </ActionButton>
                  </span>
                </Tooltip>
                <Tooltip title={session.shuffle
                  ? t('player.shuffle_on',  { defaultValue: 'Shuffle on' })
                  : t('player.shuffle_off', { defaultValue: 'Shuffle off' })
                }>
                  <span>
                    <ActionButton
                      actionType="icon"
                      aria-label={session.shuffle ? 'Shuffle on' : 'Shuffle off'}
                      colorOverride={session.shuffle ? activeColorOverride : undefined}
                      onClick={() => {
                        const next = !session.shuffle;
                        shuffleMutation.mutate(next);
                      }}
                    >
                      <ShuffleIcon fontSize="small" />
                    </ActionButton>
                  </span>
                </Tooltip>
              </Box>
              {session.queue.filter((q: QueueItem) => !q.is_current).length > 0 && (
                <UpNextCollapse queue={session.queue.filter((q: QueueItem) => !q.is_current).slice(0, 8)} />
              )}
            </Box>
          )}
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
