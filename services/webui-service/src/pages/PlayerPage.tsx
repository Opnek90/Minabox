import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Collapse,
  Divider,
  Dialog,
  DialogContent,
  DialogTitle,
  Fade,
  FormControl,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Select,
  Popover,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import RefreshIcon from '@mui/icons-material/Refresh';
import RepeatIcon from '@mui/icons-material/Repeat';
import ShuffleIcon from '@mui/icons-material/Shuffle';
import SpeakerIcon from '@mui/icons-material/Speaker';
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
import { useWebSocket, useWebSocketEvent } from '@/contexts/WebSocketContext';
import { audioApi } from '@/api/audio';
import { configApi } from '@/api/config';
import type {
  AudioDeviceItem,
  AudioSessionResponse,
  QueueItem,
  RepeatMode,
  WebSocketMessage,
} from '@/types/api';
import { useLayout } from '@/hooks/useLayout';


const SLEEP_PRESETS = [15, 30, 45, 60];

// Grenzen des Backends (SleepTimerRequest: ge=1, le=480). Hier gespiegelt,
// damit das Feld gar nicht erst einen Wert anbietet, den der Server ablehnt.
const SLEEP_MIN_MINUTES = 1;
const SLEEP_MAX_MINUTES = 480;

// `queue` is the full session in list order (past tracks included), so
// filtering out only `is_current` left already-played tracks ahead of the
// actually upcoming ones. "Up next" means everything after the current index.
const upNextQueue = (queue: QueueItem[]): QueueItem[] => {
  const currentIndex = queue.find((q) => q.is_current)?.index ?? -1;
  return queue.filter((q) => q.index > currentIndex);
};

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
          {t('player.up_next_count', { count: n })}
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
  const isSmall = useLayout().isMobile;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const audioStatus = useAudioStatus();
  const { sleepTimerStatus, isConnected } = useWebSocket();
  const [error, setError] = useState<string | null>(null);
  
  const [optimisticVolume, setOptimisticVolume] = useState<number | null>(null);
  const optimisticTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [sleepAnchor, setSleepAnchor] = useState<HTMLElement | null>(null);
  const [sleepCustom, setSleepCustom] = useState('');
  const [sleepRemainingMs, setSleepRemainingMs] = useState<number | null>(null);
  const sleepDisplayRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Overflow menu (kiosk, sleep-timer entry, output device, repeat/shuffle) —
  // keeps the main card to cover + controls + volume
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const [outputDialogOpen, setOutputDialogOpen] = useState(false);

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

  // Messages that arrive without the player having asked for them: someone
  // pressed a button on the box, or changed repeat/shuffle from the rotary
  // knob or a second browser session.
  //
  // These used to hang on window.addEventListener('ws_message'), while the
  // context dispatches on its own wsEventTarget - so none of them ever fired.
  // useWebSocketEvent is the hook the seven other listeners in the app use.
  // The callbacks are memoised because the hook has `callback` among its
  // dependencies and would otherwise re-subscribe on every render.

  const handleButtonAction = useCallback((message: WebSocketMessage) => {
    const action = (message.data as { action?: string }).action ?? '';
    // The box sends kebab-case, the label table is keyed snake_case.
    const actionKey = action.replace(/-/g, '_');
    setButtonFeedback(BUTTON_ACTION_LABELS[actionKey] ?? BUTTON_ACTION_LABELS[action] ?? action);
    if (buttonFeedbackTimeout.current) clearTimeout(buttonFeedbackTimeout.current);
    buttonFeedbackTimeout.current = setTimeout(() => setButtonFeedback(null), 1800);
  }, []);
  useWebSocketEvent('button_action', handleButtonAction);

  const handleRepeatMode = useCallback((message: WebSocketMessage) => {
    const { repeat_mode } = message.data as { repeat_mode?: RepeatMode };
    if (repeat_mode == null) return;
    queryClient.setQueryData<AudioSessionResponse | null>(['audio', 'session'], (old) =>
      old ? { ...old, repeat_mode } : old
    );
  }, [queryClient]);
  useWebSocketEvent('repeat_mode', handleRepeatMode);

  const handleShuffleMode = useCallback((message: WebSocketMessage) => {
    const { shuffle } = message.data as { shuffle?: boolean };
    if (shuffle === undefined) return;
    queryClient.setQueryData<AudioSessionResponse | null>(['audio', 'session'], (old) =>
      old ? { ...old, shuffle: Boolean(shuffle) } : old
    );
  }, [queryClient]);
  useWebSocketEvent('shuffle_mode', handleShuffleMode);

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
    onError: () => showError(t('player.seek_error')),
  });
  
  const volumeMutation = useMutation({ 
    mutationFn: audioApi.setVolume,
    onError: (err: Error) => setError(err instanceof Error ? err.message : 'Error') 
  });
  
  const startSleepTimerMutation = useMutation({
    mutationFn: audioApi.startSleepTimer,
    onError: () => showError(t('sleep_timer.error'))
  });

  const cancelSleepTimerMutation = useMutation({
    mutationFn: audioApi.cancelSleepTimer,
    onError: () => showError(t('sleep_timer.cancel_error'))
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
    onError: () => showError(t('player.output_device_switch_error'))
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
    setSleepCustom('');
    startSleepTimerMutation.mutate(minutes);
  };

  // Freie Eingabe neben den vier Vorgaben: 25 Minuten bis zum Kita-Abholen
  // oder 90 fuer ein Hoerspiel liessen sich vorher nicht einstellen.
  const sleepCustomMinutes = parseInt(sleepCustom, 10);
  const sleepCustomValid =
    Number.isFinite(sleepCustomMinutes) &&
    sleepCustomMinutes >= SLEEP_MIN_MINUTES &&
    sleepCustomMinutes <= SLEEP_MAX_MINUTES;

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

  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent={isSmall ? 'flex-start' : 'center'}
      sx={{
        minHeight: isSmall ? 'calc(100vh - 120px)' : '70vh',
        ...(isSmall && {
          '@supports (min-height: 100dvh)': { minHeight: 'calc(100dvh - 120px)' },
        }),
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
          {/* Status row: state chip + active sleep-timer chip + overflow menu */}
          <Box display="flex" justifyContent="space-between" alignItems="center" minWidth={0}>
            <Chip
              label={t(`states.${state}`)}
              color={state === 'playing' ? 'success' : state === 'error' ? 'error' : 'default'}
              size="small"
            />
            <Box display="flex" alignItems="center" gap={0.5} flexShrink={0}>
              {/* Repeat und Shuffle standen nur im Ueberlaufmenue - man musste
                  es oeffnen, um zu sehen, ob sie an sind. Jetzt stehen sie in
                  der Statuszeile: eingefaerbt heisst an, blass heisst aus, und
                  ein Tippen schaltet um. Deshalb sind sie unten aus dem Menue
                  verschwunden statt doppelt zu existieren. */}
              {session && (
                <>
                  <Tooltip
                    title={
                      session.repeat_mode === 'all'
                        ? t('player.repeat_all')
                        : t('player.repeat_off')
                    }
                  >
                    <span>
                      <ActionButton
                        actionType="icon"
                        aria-label={t('player.repeat_all')}
                        aria-pressed={session.repeat_mode === 'all'}
                        onClick={() =>
                          repeatMutation.mutate(session.repeat_mode === 'all' ? 'none' : 'all')
                        }
                      >
                        <RepeatIcon
                          fontSize="small"
                          color={session.repeat_mode === 'all' ? 'primary' : 'disabled'}
                        />
                      </ActionButton>
                    </span>
                  </Tooltip>
                  <Tooltip
                    title={session.shuffle ? t('player.shuffle_on') : t('player.shuffle_off')}
                  >
                    <span>
                      <ActionButton
                        actionType="icon"
                        aria-label={t('player.shuffle_on')}
                        aria-pressed={session.shuffle}
                        onClick={() => shuffleMutation.mutate(!session.shuffle)}
                      >
                        <ShuffleIcon
                          fontSize="small"
                          color={session.shuffle ? 'primary' : 'disabled'}
                        />
                      </ActionButton>
                    </span>
                  </Tooltip>
                </>
              )}
              {sleepRemainingMs !== null && (
                <Chip
                  icon={<HotelIcon fontSize="small" />}
                  label={formatSleepRemaining(sleepRemainingMs)}
                  size="small"
                  color="primary"
                  variant="outlined"
                  onDelete={handleCancelSleepTimer}
                  deleteIcon={<CancelIcon />}
                />
              )}
              <Tooltip title={t('more_options')}>
                <span>
                  <ActionButton
                    ref={moreButtonRef}
                    actionType="icon"
                    aria-label={t('more_options')}
                    onClick={() => setMoreMenuOpen(true)}
                  >
                    <MoreVertIcon fontSize="small" />
                  </ActionButton>
                </span>
              </Tooltip>
            </Box>
          </Box>

          {/* Overflow menu: kiosk mode, sleep timer, output device, repeat/shuffle.
              Kept out of the main card so the player stays cover + controls + volume
              for the child using this page day-to-day. */}
          <Menu
            anchorEl={moreButtonRef.current}
            open={moreMenuOpen}
            onClose={() => setMoreMenuOpen(false)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <MenuItem onClick={() => { setMoreMenuOpen(false); navigate('/kiosk'); }}>
              <ListItemIcon><FullscreenIcon fontSize="small" /></ListItemIcon>
              <ListItemText>{t('kiosk_mode')}</ListItemText>
            </MenuItem>
            {sleepRemainingMs === null && (
              <MenuItem onClick={() => { setMoreMenuOpen(false); setSleepAnchor(moreButtonRef.current); }}>
                <ListItemIcon><HotelIcon fontSize="small" /></ListItemIcon>
                <ListItemText>{t('sleep_timer.title')}</ListItemText>
              </MenuItem>
            )}
            <MenuItem onClick={() => { setMoreMenuOpen(false); setOutputDialogOpen(true); }}>
              <ListItemIcon><SpeakerIcon fontSize="small" /></ListItemIcon>
              <ListItemText>{t('player.output_device')}</ListItemText>
            </MenuItem>
          </Menu>

          {/* Sleep timer popover, anchored to the overflow-menu button */}
          <Popover
            open={Boolean(sleepAnchor)}
            anchorEl={sleepAnchor}
            onClose={() => setSleepAnchor(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <List dense sx={{ py: 0.5, minWidth: 200 }}>
              {SLEEP_PRESETS.map((min) => (
                <ListItemButton key={min} onClick={() => handleStartSleepTimer(min)}>
                  <Typography variant="body2">
                    {t('sleep_timer.preset', { minutes: min })}
                  </Typography>
                </ListItemButton>
              ))}
              <Divider sx={{ my: 0.5 }} />
              <Box
                component="form"
                onSubmit={(e: React.FormEvent) => {
                  e.preventDefault();
                  if (sleepCustomValid) handleStartSleepTimer(sleepCustomMinutes);
                }}
                sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1.5, py: 1 }}
              >
                <TextField
                  type="number"
                  size="small"
                  autoComplete="off"
                  value={sleepCustom}
                  onChange={(e) => setSleepCustom(e.target.value)}
                  label={t('sleep_timer.custom_label')}
                  inputProps={{
                    min: SLEEP_MIN_MINUTES,
                    max: SLEEP_MAX_MINUTES,
                    'aria-label': t('sleep_timer.custom_label'),
                  }}
                  sx={{ width: 110 }}
                />
                <ActionButton actionType="primary" type="submit" disabled={!sleepCustomValid}>
                  {t('sleep_timer.custom_start')}
                </ActionButton>
              </Box>
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

          {/* Up next (collapsible) — Output device, Repeat, Shuffle live in the
              overflow menu above */}
          {session && upNextQueue(session.queue).length > 0 && (
            <Box sx={{ pt: 0.5, borderTop: 1, borderColor: 'divider' }}>
              <UpNextCollapse queue={upNextQueue(session.queue).slice(0, 8)} />
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Output device dialog (moved out of the main card, see B2) */}
      <Dialog open={outputDialogOpen} onClose={() => setOutputDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('player.output_device')}</DialogTitle>
        <DialogContent sx={{ pt: '8px !important' }}>
          <Box display="flex" alignItems="center" gap={0.5} sx={{ width: '100%' }}>
            <FormControl size="small" sx={{ minWidth: 140, flex: 1 }}>
              <Select
                value={audioConfig?.output_device_name ?? ''}
                displayEmpty
                renderValue={(v) => {
                  const d = outputDevices.find((x: AudioDeviceItem) => x.alsa_device === v);
                  return d ? d.name : (v || t('player.output_device'));
                }}
                onChange={(e) => {
                  const v = e.target.value as string;
                  if (!v) return;
                  switchDeviceMutation.mutate(v);
                }}
                disabled={outputDevicesLoading || switchDeviceMutation.isPending}
                aria-label={t('player.output_device')}
              >
                {outputDevices.map((d: AudioDeviceItem) => (
                  <MenuItem key={d.alsa_device} value={d.alsa_device}>
                    {d.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Tooltip title={t('player.output_device_refresh')}>
              <span>
                <ActionButton
                  actionType="icon"
                  onClick={() => refetchDevices()}
                  disabled={outputDevicesLoading}
                  aria-label={t('player.output_device_refresh')}
                >
                  <RefreshIcon fontSize="small" />
                </ActionButton>
              </span>
            </Tooltip>
          </Box>
        </DialogContent>
      </Dialog>

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
