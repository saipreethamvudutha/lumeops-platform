/**
 * useWebSocket — React hook for real-time LumeOps event streaming.
 *
 * Architecture:
 *   The hook manages a single WebSocket connection per dashboard session.
 *   It automatically reconnects with exponential backoff if the connection
 *   drops, and provides both connection state and a stream of events.
 *
 * Why native WebSocket (not Socket.IO)?
 *   - Zero dependencies — the browser WebSocket API is sufficient
 *   - FastAPI has first-class WebSocket support
 *   - Socket.IO's fallback to polling adds complexity we don't need
 *     (all modern browsers support WebSocket natively)
 *   - Smaller bundle size
 *
 * Reconnection strategy:
 *   On disconnect, the hook waits an exponentially increasing interval
 *   (1s, 2s, 4s, 8s, ... up to 30s) before retrying. This prevents
 *   thundering herd when the server restarts and all clients reconnect
 *   simultaneously.
 *
 * Usage:
 *   const { connected, events, lastEvent } = useWebSocket();
 *
 *   // `connected` — boolean, true when WebSocket is open
 *   // `events` — array of recent events (last 50)
 *   // `lastEvent` — most recent event (for triggering re-renders)
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { getApiKey } from '../api/client';

/** Event received from the WebSocket server */
export interface WSEvent {
  type: string;
  data: Record<string, unknown>;
}

/** Connection states */
export type WSStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

/** Maximum number of events to keep in memory */
const MAX_EVENTS = 50;

/** Maximum reconnect delay in milliseconds */
const MAX_RECONNECT_DELAY = 30_000;

/** Initial reconnect delay in milliseconds */
const INITIAL_RECONNECT_DELAY = 1_000;

/** Ping interval to keep connection alive (25 seconds) */
const PING_INTERVAL = 25_000;

export function useWebSocket() {
  const [status, setStatus] = useState<WSStatus>('disconnected');
  const [events, setEvents] = useState<WSEvent[]>([]);
  const [lastEvent, setLastEvent] = useState<WSEvent | null>(null);

  // Refs to track reconnect state across renders
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const unmountedRef = useRef(false);

  const addEvent = useCallback((event: WSEvent) => {
    setEvents((prev) => {
      const next = [event, ...prev];
      // Keep only the most recent MAX_EVENTS
      return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next;
    });
    setLastEvent(event);
  }, []);

  const connect = useCallback(() => {
    // Don't connect if unmounted or already connecting/connected
    if (unmountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    const apiKey = getApiKey();
    if (!apiKey) {
      setStatus('error');
      return;
    }

    setStatus('connecting');

    // Build WebSocket URL from current page origin
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws?token=${encodeURIComponent(apiKey)}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) {
        ws.close();
        return;
      }
      setStatus('connected');
      reconnectAttemptRef.current = 0;

      // Start ping keepalive
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, PING_INTERVAL);
    };

    ws.onmessage = (evt) => {
      if (unmountedRef.current) return;
      try {
        const event: WSEvent = JSON.parse(evt.data);
        // Filter out pong responses (internal keepalive)
        if (event.type !== 'pong') {
          addEvent(event);
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = (evt) => {
      // Clean up ping timer
      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current);
        pingTimerRef.current = null;
      }

      if (unmountedRef.current) return;
      setStatus('disconnected');

      // Don't reconnect on auth failures (4001, 4003)
      if (evt.code === 4001 || evt.code === 4003) {
        setStatus('error');
        return;
      }

      // Exponential backoff reconnect
      const attempt = reconnectAttemptRef.current;
      const delay = Math.min(
        INITIAL_RECONNECT_DELAY * Math.pow(2, attempt),
        MAX_RECONNECT_DELAY,
      );
      reconnectAttemptRef.current = attempt + 1;

      reconnectTimerRef.current = setTimeout(() => {
        if (!unmountedRef.current) {
          connect();
        }
      }, delay);
    };

    ws.onerror = () => {
      // The onclose handler will fire after this, which handles reconnect
      if (!unmountedRef.current) {
        setStatus('error');
      }
    };
  }, [addEvent]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    unmountedRef.current = false;
    connect();

    return () => {
      unmountedRef.current = true;
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    /** Current connection status */
    status,
    /** Whether the WebSocket is connected */
    connected: status === 'connected',
    /** Recent events (newest first, max 50) */
    events,
    /** Most recent event */
    lastEvent,
    /** Manually reconnect */
    reconnect: connect,
    /** Clear event buffer */
    clearEvents: useCallback(() => {
      setEvents([]);
      setLastEvent(null);
    }, []),
  };
}
