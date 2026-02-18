import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { WebSocketMessage } from '@/types/api';

interface WebSocketContextType {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  sendMessage: (message: unknown) => void;
}

const WebSocketContext = createContext<WebSocketContextType>({
  isConnected: false,
  lastMessage: null,
  sendMessage: () => undefined,
});

const WS_URL = '/ws';
const RECONNECT_DELAY_INITIAL = 1000;
const RECONNECT_DELAY_MAX = 30000;
const RECONNECT_DELAY_FACTOR = 2;

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef<number>(RECONNECT_DELAY_INITIAL);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (socketRef.current?.readyState === WebSocket.OPEN) return;

    // Build WebSocket URL relative to current host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${WS_URL}`;

    console.log('[WebUI] Connecting to WebSocket:', wsUrl);
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      console.log('[WebUI] WebSocket connected');
      setIsConnected(true);
      reconnectDelayRef.current = RECONNECT_DELAY_INITIAL;
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return;
      try {
        const message = JSON.parse(event.data as string) as WebSocketMessage;
        setLastMessage(message);
      } catch (e) {
        console.error('[WebUI] Failed to parse WebSocket message:', e);
      }
    };

    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      console.log('[WebUI] WebSocket closed:', event.code, event.reason);
      setIsConnected(false);
      socketRef.current = null;

      // Exponential backoff reconnect
      const delay = reconnectDelayRef.current;
      console.log(`[WebUI] Reconnecting in ${delay}ms...`);
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) {
          reconnectDelayRef.current = Math.min(
            delay * RECONNECT_DELAY_FACTOR,
            RECONNECT_DELAY_MAX
          );
          connect();
        }
      }, delay);
    };

    ws.onerror = (error) => {
      console.error('[WebUI] WebSocket error:', error);
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [connect]);

  const sendMessage = useCallback((message: unknown) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    } else {
      console.warn('[WebUI] WebSocket not connected, cannot send message');
    }
  }, []);

  return (
    <WebSocketContext.Provider value={{ isConnected, lastMessage, sendMessage }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = (): WebSocketContextType => useContext(WebSocketContext);
