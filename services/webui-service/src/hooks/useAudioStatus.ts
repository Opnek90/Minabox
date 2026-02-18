import { useEffect, useRef, useState } from 'react';
import { useWebSocket } from '@/contexts/WebSocketContext';
import type { AudioStatus } from '@/types/api';

const TICK_MS = 1000;

export const useAudioStatus = (): AudioStatus | null => {
  const { lastMessage } = useWebSocket();
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(null);
  const interpolatedRef = useRef<AudioStatus | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Update from WebSocket
  useEffect(() => {
    if (lastMessage?.type === 'audio_status') {
      const data = lastMessage.data as AudioStatus;
      interpolatedRef.current = { ...data };
      setAudioStatus({ ...data });
    }
  }, [lastMessage]);

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
