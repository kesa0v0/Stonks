import { useEffect, useRef } from 'react';

export function useWebSocket(onMessage: (data: any) => void, onOpen?: () => void) {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let retry = 0;
    let alive = true;
    let heartbeat: number | null = null;

    const connect = () => {
      const url = import.meta.env.VITE_WS_URL as string;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => { 
          retry = 0;
          if (onOpen) onOpen();
      };
      ws.onmessage = ev => {
        try { onMessage(JSON.parse(ev.data)); } catch { /* ignore */ }
      };
      ws.onerror = (ev) => {
        // Log errors but don't force-close immediately; let onclose handle retry
        // Some transient network errors can fire before the connection is ready
        console.warn("WS error", ev);
      };
      ws.onclose = () => {
        if (!alive) return;
        const backoff = Math.min(1000 * 2 ** retry, 15000);
        retry++;
        setTimeout(connect, backoff);
      };

      // Optional heartbeat to keep proxies happy
      heartbeat = window.setInterval(() => {
        try {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping", t: Date.now() }));
          }
        } catch {}
      }, 30000);
    };

    connect();
    return () => {
      // React 18 StrictMode doubles effects in dev; avoid killing a connecting socket
      alive = false;
      if (heartbeat) window.clearInterval(heartbeat);
      const ws = wsRef.current;
      if (!ws) return;
      // Only close actively open sockets; let CONNECTING failover naturally
      if (ws.readyState === WebSocket.OPEN) {
        try { ws.close(); } catch {}
      }
    };
  }, [onMessage, onOpen]);
}
