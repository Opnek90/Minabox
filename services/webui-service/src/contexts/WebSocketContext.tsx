import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { AudioStatus, SleepTimerStatus, WebSocketMessage } from '@/types/api';

export const wsEventTarget = new EventTarget();
export const WS_EVENT_MESSAGE = 'ws_message';

export interface CachedAudioStatus {
  status: AudioStatus;
  /** performance.now() timestamp when this status was received */
  receivedAt: number;
}

interface WebSocketContextType {
  isConnected: boolean;
  sleepTimerStatus: SleepTimerStatus | null;
  cachedAudioStatus: CachedAudioStatus | null;
  /** Last raw WebSocket message (e.g. for rfid_scanned, tag_not_found, system_alert). */
  lastMessage: WebSocketMessage | null;
  sendMessage: (message: unknown) => void;
}

const WebSocketContext = createContext<WebSocketContextType>({
  isConnected: false,
  sleepTimerStatus: null,
  cachedAudioStatus: null,
  lastMessage: null,
  sendMessage: () => undefined,
});

const WS_URL = '/ws';
const RECONNECT_DELAY_INITIAL = 1000;
const RECONNECT_DELAY_MAX = 30000;
const RECONNECT_DELAY_FACTOR = 2;

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [sleepTimerStatus, setSleepTimerStatus] = useState<SleepTimerStatus | null>(null);
  const [cachedAudioStatus, setCachedAudioStatus] = useState<CachedAudioStatus | null>(null);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef<number>(RECONNECT_DELAY_INITIAL);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (socketRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${WS_URL}`;
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setIsConnected(true);
      reconnectDelayRef.current = RECONNECT_DELAY_INITIAL;
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return;
      try {
        const message = JSON.parse(event.data as string) as WebSocketMessage;
        setLastMessage(message);
        const customEvent = new CustomEvent(WS_EVENT_MESSAGE, { detail: message });
        wsEventTarget.dispatchEvent(customEvent);

        if (message.type === 'sleep_timer_status') {
          setSleepTimerStatus(message.data as SleepTimerStatus);
        }

        if (message.type === 'audio_status') {
          setCachedAudioStatus({
            status: message.data as AudioStatus,
            receivedAt: performance.now(),
          });
        }
      } catch (e) {
        console.error('[WebUI] Failed to parse WebSocket message:', e);
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setIsConnected(false);
      socketRef.current = null;
      const delay = reconnectDelayRef.current;
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) {
          reconnectDelayRef.current = Math.min(delay * RECONNECT_DELAY_FACTOR, RECONNECT_DELAY_MAX);
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
    <WebSocketContext.Provider value={{ isConnected, sleepTimerStatus, cachedAudioStatus, lastMessage, sendMessage }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = (): WebSocketContextType => useContext(WebSocketContext);

/**
 * Listen for exactly one message type without re-rendering on every other
 * message.
 *
 * Note on the callback parameter: `Extract<WebSocketMessage, {type: T}>` is
 * always `never` here, because `WebSocketMessage` is not a discriminated union
 * but an interface with `type: WebSocketMessageType`. `never` accepts any
 * annotation without complaint - so the generic checks nothing. That is why
 * every caller annotates its own parameter and reads `data` via an `as`
 * assertion. This could only really be fixed by making `WebSocketMessage` in
 * types/api.ts a real union over the individual types.
 */
export function useWebSocketEvent<T extends WebSocketMessage['type']>(
  messageType: T,
  callback: (data: Extract<WebSocketMessage, { type: T }>) => void
) {
  // The callback lives in a ref instead of the dependencies. Almost every
  // caller passes an inline function - that is new on every render, so the
  // listener unsubscribed and re-subscribed on every render. Messages arriving
  // between unsubscribe and subscribe were lost, and every caller had to resort
  // to useCallback to avoid that.
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    const handler = (event: Event) => {
      const customEvent = event as CustomEvent<WebSocketMessage>;
      if (customEvent.detail.type === messageType) {
        callbackRef.current(customEvent.detail as Extract<WebSocketMessage, { type: T }>);
      }
    };
    wsEventTarget.addEventListener(WS_EVENT_MESSAGE, handler);
    return () => wsEventTarget.removeEventListener(WS_EVENT_MESSAGE, handler);
  }, [messageType]);
}
