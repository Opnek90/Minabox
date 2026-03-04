import { useEffect, useRef, useState } from 'react';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';
import { audioApi } from '@/api/audio';
import type { AudioStatus, AudioStatusMessage } from '@/types/api';

const TICK_MS = 1000;

export const useAudioStatus = (): AudioStatus | null => {
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(null);
  const interpolatedRef = useRef<AudioStatus | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const initialFetchDone = useRef(false);

  // Fallback: fetch current status via REST on mount so the Player page
  // renders immediately even when no MQTT event has been received yet.
  useEffect(() => {
    if (initialFetchDone.current) return;
    initialFetchDone.current = true;
    audioApi.getStatus().then((data) => {
      setAudioStatus((prev) => {
        // Don't overwrite if a WS message already arrived first
        if (prev !== null) return prev;
        interpolatedRef.current = data;
        return data;
      });
    }).catch(() => null);
  }, []);

  // Update from WebSocket using the new Pub/Sub hook
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
