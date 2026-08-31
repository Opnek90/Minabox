import React, { useEffect, useRef } from 'react';
import {
  Box,
  IconButton,
  LinearProgress,
  Paper,
  Tooltip,
  Typography,
} from '@mui/material';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAudioStatus } from '@/hooks/useAudioStatus';
import { useSleepTimer } from '@/hooks/useSleepTimer';
import { audioApi } from '@/api/audio';
import { MOBILE_BOTTOM_NAV_HEIGHT, SAFE_AREA_BOTTOM } from '@/components/common/Navigation';

// Height of the MiniPlayer bar (progress bar 3px + content row ~61px).
// Exported so other fixed-position elements (e.g. MediaFab) can offset themselves.
export const MINI_PLAYER_HEIGHT = 64;

// ── Sleep-Timer Ring ─────────────────────────────────────────────────────────
interface SleepRingProps {
  remainingMs: number;
  totalMs: number;
  size?: number;
}

const SleepRing: React.FC<SleepRingProps> = ({ remainingMs, totalMs, size = 36 }) => {
  const { t } = useTranslation('player');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ratio = totalMs > 0 ? Math.max(0, Math.min(remainingMs / totalMs, 1)) : 0;

  // Draw arc on each render
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const r = size / 2 - 3;
    const startAngle = -Math.PI / 2;
    const endAngle = startAngle + 2 * Math.PI * ratio;

    ctx.clearRect(0, 0, size, size);

    // Track ring
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 2 * Math.PI);
    ctx.strokeStyle = 'rgba(128,128,128,0.2)';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Progress arc
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = '#ff9800';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.stroke();
  }, [ratio, size]);

  const minutes = Math.ceil(remainingMs / 60000);

  return (
    <Tooltip title={t('sleep_timer.remaining_tooltip', { minutes })}>
      <Box
        sx={{
          position: 'relative',
          width: size,
          height: size,
          flexShrink: 0,
          cursor: 'default',
        }}
      >
        <canvas
          ref={canvasRef}
          style={{ width: size, height: size, display: 'block' }}
        />
        {/* Minute label inside ring */}
        <Typography
          variant="caption"
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '0.6rem',
            fontWeight: 700,
            color: 'warning.main',
            lineHeight: 1,
            pointerEvents: 'none',
          }}
        >
          {minutes}
        </Typography>
      </Box>
    </Tooltip>
  );
};

// ── MiniPlayer ───────────────────────────────────────────────────────────────
export const MiniPlayer: React.FC = () => {
  const { t } = useTranslation('player');
  const navigate = useNavigate();
  const audioStatus = useAudioStatus();
  const sleepTimer = useSleepTimer();

  if (!audioStatus || audioStatus.state === 'stopped') return null;

  const { state, track_title, track_artist, position_ms, duration_ms } = audioStatus;
  const progress =
    duration_ms && duration_ms > 0 ? (position_ms / duration_ms) * 100 : 0;

  const showSleepRing =
    sleepTimer?.active === true && (sleepTimer.remaining_ms ?? 0) > 0;

  // Best-effort total: use first observed remaining when timer starts
  // We approximate total from a common preset bucket (15/30/45/60 min)
  const PRESET_MS = [15, 30, 45, 60].map((m) => m * 60 * 1000);
  const remaining = sleepTimer?.remaining_ms ?? 0;
  const totalMs = PRESET_MS.find((p) => p >= remaining) ?? remaining;

  return (
    <Paper
      elevation={8}
      sx={{
        position: 'fixed',
        // Sits directly above the mobile BottomNavigation; flush with the
        // bottom edge on desktop, where there is no bottom nav. On mobile the
        // device safe area is added, which the BottomNav carries as padding -
        // without it the MiniPlayer would overlap it.
        // sm instead of md: from the tablet level the icon rail takes over, the
        // BottomNav only exists at phone widths.
        bottom: {
          xs: `calc(${MOBILE_BOTTOM_NAV_HEIGHT}px + ${SAFE_AREA_BOTTOM})`,
          sm: 0,
        },
        left: 0,
        right: 0,
        zIndex: 1200,
        borderRadius: 0,
        borderTop: 1,
        borderColor: 'divider',
      }}
    >
      {/* Progress bar */}
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
        {/* Sleep-Timer Ring oder Music-Icon */}
        {showSleepRing ? (
          <Box onClick={(e) => e.stopPropagation()}>
            <SleepRing remainingMs={remaining} totalMs={totalMs} size={36} />
          </Box>
        ) : null}

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
          <Tooltip
            title={state === 'playing' ? t('controls.pause') : t('controls.play')}
          >
            <IconButton
              size="small"
              onClick={() =>
                state === 'playing' ? audioApi.pause() : audioApi.play()
              }
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
