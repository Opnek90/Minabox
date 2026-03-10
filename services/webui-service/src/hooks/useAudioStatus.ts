import { useEffect, useRef, useState } from 'react';
import { useWebSocket, useWebSocketEvent } from '@/contexts/WebSocketContext';
import { audioApi } from '@/api/audio';
import type { AudioStatus, AudioStatusMessage } from '@/types/api';

const TICK_MS = 1000;

export const useAudioStatus = (): AudioStatus | null => {
  const { lastAudioStatus } = useWebSocket();
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(null);
  const interpolatedRef = useRef<AudioStatus | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (lastAudioStatus) {
      // Phase 1: render metadata immediately from cache (no 'Unknown Track' flash)
      // position_ms in cache may be stale (up to several seconds old) — patch below.
      interpolatedRef.current = lastAudioStatus;
      setAudioStatus(lastAudioStatus);

      // Phase 2: fetch fresh position_ms via REST concurrently and patch it in.
      // This fixes the progress bar jump (T4) without causing a metadata flicker.
      // Only patch position_ms (and duration_ms) — leave all other fields from cache.
      audioApi.getStatus().then((fresh) => {
        setAudioStatus((prev) => {
          if (!prev) return fresh; // fallback: use full REST response
          const patched: AudioStatus = {
            ...prev,
            position_ms: fresh.position_ms,
            duration_ms: fresh.duration_ms,
            state: fresh.state,
          };
          interpolatedRef.current = patched;
          return patched;
        });
      }).catch(() => null); // REST failure is non-fatal — cache value stays
    } else {
      // No cache yet (first app load / hard reload): full REST fetch
      audioApi.getStatus().then((data) => {
        interpolatedRef.current = data;
        setAudioStatus(data);
      }).catch(() => null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // only on mount — lastAudioStatus intentionally not in deps

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
