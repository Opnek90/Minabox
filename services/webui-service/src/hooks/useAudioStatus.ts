import { useEffect, useRef, useState } from 'react';
import { useWebSocket, useWebSocketEvent } from '@/contexts/WebSocketContext';
import { audioApi } from '@/api/audio';
import type { AudioStatus, AudioStatusMessage } from '@/types/api';

const TICK_MS = 1000;

export const useAudioStatus = (): AudioStatus | null => {
  const { lastAudioStatus } = useWebSocket(); // ✅ fix #56: use cached WS status
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(null);
  const interpolatedRef = useRef<AudioStatus | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const initializedRef = useRef(false);

  // ✅ fix #56: On mount, initialize from cached WS status (no stale null, no spurious REST call).
  // Only fall back to REST if no cached status exists yet (first app load, no event received).
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (lastAudioStatus) {
      // Use cached status immediately — no jump, no flicker
      interpolatedRef.current = lastAudioStatus;
      setAudioStatus(lastAudioStatus);
    } else {
      // First load: no WS event received yet, fetch via REST
      audioApi.getStatus().then((data) => {
        interpolatedRef.current = data;
        setAudioStatus(data);
      }).catch(() => null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // only on mount — lastAudioStatus intentionally not in deps

  // Update from WebSocket using the Pub/Sub hook
  useWebSocketEvent('audio_status', (message: AudioStatusMessage) => {
    const data = message.data;
    interpolatedRef.current = { ...data };
    setAudioStatus({ ...data });
  });

  // While playing, tick every second to advance position_ms for smoother progress bar
  useEffect(() => {
    if (!audioStatus || audioStatus.state !== 'playing') {
      if (tickRef.current) {
        clearInterval(tickRef.current);
        tickRef.current = null;
      }
      return;
    }
    // ✅ fix #56: clear any stale interval before starting a new one (avoids double-tick on re-mount)
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
