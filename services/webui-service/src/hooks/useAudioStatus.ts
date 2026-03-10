import { useEffect, useRef, useState } from 'react';
import { useWebSocket, useWebSocketEvent } from '@/contexts/WebSocketContext';
import { audioApi } from '@/api/audio';
import type { AudioStatus, AudioStatusMessage } from '@/types/api';

const TICK_MS = 1000;

export const useAudioStatus = (): AudioStatus | null => {
  const { lastAudioStatus } = useWebSocket();

  // fix #56 T4/T5: initialize SYNCHRONOUSLY from WS cache so the very first
  // render already has correct metadata. useEffect-based init was too late
  // (fires after render) causing null→cached transition = progress bar jump.
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(
    () => lastAudioStatus ?? null
  );

  const interpolatedRef = useRef<AudioStatus | null>(audioStatus);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const positionPatchedRef = useRef(false);

  useEffect(() => {
    if (positionPatchedRef.current) return;
    positionPatchedRef.current = true;

    if (lastAudioStatus) {
      // Cache hit: metadata already rendered correctly.
      // Patch only position_ms + duration_ms + state via REST to fix stale position.
      audioApi.getStatus().then((fresh) => {
        setAudioStatus((prev) => {
          if (!prev) return fresh;
          const patched: AudioStatus = {
            ...prev,
            position_ms: fresh.position_ms,
            duration_ms: fresh.duration_ms,
            state: fresh.state,
          };
          interpolatedRef.current = patched;
          return patched;
        });
      }).catch(() => null);
    } else {
      // No cache (first load / hard reload): full REST fetch
      audioApi.getStatus().then((data) => {
        interpolatedRef.current = data;
        setAudioStatus(data);
      }).catch(() => null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // only on mount

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
