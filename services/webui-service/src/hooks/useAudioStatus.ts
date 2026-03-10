import { useEffect, useRef, useState } from 'react';
import { useWebSocket, useWebSocketEvent } from '@/contexts/WebSocketContext';
import type { AudioStatus, AudioStatusMessage } from '@/types/api';

const TICK_MS = 1000;

/**
 * Extrapolate the current position_ms from a cached status.
 * When state === 'playing', add the elapsed time since the cache was received.
 * This corrects the stale position without any network call.
 */
function extrapolatePosition(status: AudioStatus, receivedAt: number): AudioStatus {
  if (status.state !== 'playing' || status.position_ms == null) return status;
  const elapsedMs = Math.round(performance.now() - receivedAt);
  if (elapsedMs <= 0) return status;
  const duration = status.duration_ms ?? Infinity;
  const correctedMs = Math.min((status.position_ms ?? 0) + elapsedMs, duration);
  return { ...status, position_ms: correctedMs };
}

export const useAudioStatus = (): AudioStatus | null => {
  const { cachedAudioStatus } = useWebSocket();

  // Synchronous lazy initializer: compute the correct position_ms immediately
  // on first render using the WS cache + elapsed time since it was received.
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(() => {
    if (!cachedAudioStatus) return null;
    return extrapolatePosition(cachedAudioStatus.status, cachedAudioStatus.receivedAt);
  });

  const interpolatedRef = useRef<AudioStatus | null>(audioStatus);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Live updates from WebSocket
  useWebSocketEvent('audio_status', (message: AudioStatusMessage) => {
    const data = message.data;
    interpolatedRef.current = { ...data };
    setAudioStatus({ ...data });
  });

  // Client-side tick: advance position_ms every second while playing
  useEffect(() => {
    if (!audioStatus || audioStatus.state !== 'playing') {
      if (tickRef.current) {
        clearInterval(tickRef.current);
        tickRef.current = null;
      }
      return;
    }
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    tickRef.current = setInterval(() => {
      setAudioStatus((prev) => {
        if (!prev || prev.state !== 'playing') return prev;
        const current = prev.position_ms ?? 0;
        const duration = prev.duration_ms ?? Infinity;
        const nextMs = Math.min(current + TICK_MS, duration);
        const next = { ...prev, position_ms: nextMs };
        interpolatedRef.current = next;
        return next;
      });
    }, TICK_MS);
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, [audioStatus?.state]);

  return audioStatus;
};
