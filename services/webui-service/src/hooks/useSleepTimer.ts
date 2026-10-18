import { useEffect, useState } from 'react';
import { useWebSocket } from '@/contexts/WebSocketContext';
import { audioApi } from '@/api/audio';
import type { SleepTimerStatus } from '@/types/api';

export const useSleepTimer = (): SleepTimerStatus | null => {
  const { sleepTimerStatus, isConnected } = useWebSocket();
  const [fetchedStatus, setFetchedStatus] = useState<SleepTimerStatus | null>(null);
  const [remainingMs, setRemainingMs] = useState<number | null>(null);

  useEffect(() => {
    if (!isConnected || sleepTimerStatus !== null) return;
    let active = true;
    audioApi
      .getSleepTimer()
      .then((status) => {
        if (active) setFetchedStatus(status);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [isConnected, sleepTimerStatus]);

  const source = sleepTimerStatus ?? fetchedStatus;

  useEffect(() => {
    if (!source?.active || source.remaining_ms == null || source.remaining_ms <= 0) {
      setRemainingMs(null);
      return;
    }
    const endMs = Date.now() + source.remaining_ms;
    setRemainingMs(source.remaining_ms);
    const timer = setInterval(() => {
      const next = endMs - Date.now();
      if (next <= 0) {
        clearInterval(timer);
        setRemainingMs(null);
      } else {
        setRemainingMs(next);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [source]);

  if (!source) return null;
  if (!source.active || remainingMs === null) {
    return { ...source, active: false, remaining_ms: null };
  }
  return { ...source, active: true, remaining_ms: remainingMs };
};
