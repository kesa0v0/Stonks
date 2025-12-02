import { useEffect, useRef } from 'react';

export function useWebSocket(onMessage: (data: any) => void) {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let retry = 0;
    let alive = true;

    const connect = () => {
      const url = import.meta.env.VITE_WS_URL as string;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => { retry = 0; };
      ws.onmessage = ev => {
        try { onMessage(JSON.parse(ev.data)); } catch { /* ignore */ }
      };
      ws.onerror = () => ws.close();
      ws.onclose = () => {
        if (!alive) return;
        const backoff = Math.min(1000 * 2 ** retry, 15000);
        retry++;
        setTimeout(connect, backoff);
      };
    };

    connect();
    return () => { alive = false; wsRef.current?.close(); };
  }, [onMessage]);
}
