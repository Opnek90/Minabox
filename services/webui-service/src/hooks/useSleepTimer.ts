import { useWebSocket } from '@/contexts/WebSocketContext';
import type { SleepTimerStatus } from '@/types/api';

export const useSleepTimer = (): SleepTimerStatus | null => {
  const { sleepTimerStatus } = useWebSocket();
  return sleepTimerStatus;
};
