import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { audioApi } from '@/api/audio';
import { useWebSocket, useWebSocketEvent } from '@/contexts/WebSocketContext';
import type { HardwareLockStatus, WebSocketMessage } from '@/types/api';

const QUERY_KEY = ['audio', 'hardware-lock'] as const;

export const useHardwareLock = () => {
  const { isConnected } = useWebSocket();
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: audioApi.getHardwareLock,
    enabled: isConnected,
    staleTime: 30_000,
  });

  useWebSocketEvent('hardware_lock', (message: WebSocketMessage) => {
    const payload = message.data as HardwareLockStatus | undefined;
    if (!payload || typeof payload.locked !== 'boolean') return;
    void queryClient.cancelQueries({ queryKey: QUERY_KEY });
    queryClient.setQueryData<HardwareLockStatus>(QUERY_KEY, payload);
  });

  const mutation = useMutation({
    mutationFn: (locked: boolean) => audioApi.setHardwareLock(locked),
    onMutate: async (locked: boolean) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous = queryClient.getQueryData<HardwareLockStatus>(QUERY_KEY);
      queryClient.setQueryData<HardwareLockStatus>(QUERY_KEY, { locked });
      return { previous };
    },
    onSuccess: (result) => {
      queryClient.setQueryData<HardwareLockStatus>(QUERY_KEY, result);
    },
    onError: (_err, _locked, context) => {
      if (context?.previous) {
        queryClient.setQueryData<HardwareLockStatus>(QUERY_KEY, context.previous);
      }
    },
  });

  const locked = Boolean(data?.locked);
  const setLocked = useCallback((next: boolean) => mutation.mutate(next), [mutation]);
  const toggleLocked = useCallback(() => mutation.mutate(!locked), [mutation, locked]);

  return {
    locked,
    setLocked,
    toggleLocked,
    isPending: mutation.isPending,
  };
};
