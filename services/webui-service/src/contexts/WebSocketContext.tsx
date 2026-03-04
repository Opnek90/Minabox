import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { SleepTimerStatus, WebSocketMessage } from '@/types/api';

// Export an EventTarget instance so components can subscribe to messages without re-rendering
export const wsEventTarget = new EventTarget();

export const WS_EVENT_MESSAGE = 'ws_message';

interface WebSocketContextType {
  isConnected: boolean;
  sleepTimerStatus: SleepTimerStatus | null;  // ✅ neu
  sendMessage: (message: unknown) => void;
}

const WebSocketContext = createContext<WebSocketContextType>({
  isConnected: false,
  sleepTimerStatus: null,
  sendMessage: () => undefined,
});

const WS_URL = '/ws';
const RECONNECT_DELAY_INITIAL = 1000;
const RECONNECT_DELAY_MAX = 30000;
const RECONNECT_DELAY_FACTOR = 2;

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [sleepTimerStatus, setSleepTimerStatus] = useState<SleepTimerStatus | null>(null); // ✅ neu
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef<number>(RECONNECT_DELAY_INITIAL);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (socketRef.current?.readyState === WebSocket.OPEN) return;

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
        
        // Dispatch custom event for Pub/Sub pattern
        const customEvent = new CustomEvent(WS_EVENT_MESSAGE, { detail: message });
        wsEventTarget.dispatchEvent(customEvent);

        // ✅ Sleep-Timer-Status persistent im Context halten
        if (message.type === 'sleep_timer_status') {
          setSleepTimerStatus(message.data as SleepTimerStatus);
        }
      } catch (e) {
        console.error('[WebUI] Failed to parse WebSocket message:', e);
      }
    };

    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      console.log('[WebUI] WebSocket closed:', event.code, event.reason);
      setIsConnected(false);
      socketRef.current = null;

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
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
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
    <WebSocketContext.Provider value={{ isConnected, sleepTimerStatus, sendMessage }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = (): WebSocketContextType => useContext(WebSocketContext);

// Custom Hook for subscribing to specific WebSocket message types
export function useWebSocketEvent<T extends WebSocketMessage['type']>(
  messageType: T,
  callback: (data: Extract<WebSocketMessage, { type: T }>) => void
) {
  useEffect(() => {
    const handler = (event: Event) => {
      const customEvent = event as CustomEvent<WebSocketMessage>;
      if (customEvent.detail.type === messageType) {
        callback(customEvent.detail as Extract<WebSocketMessage, { type: T }>);
      }
    };

    wsEventTarget.addEventListener(WS_EVENT_MESSAGE, handler);
    return () => {
      wsEventTarget.removeEventListener(WS_EVENT_MESSAGE, handler);
    };
  }, [messageType, callback]);
}
