import { useCallback, useEffect, useRef } from 'react';
import { useWebSocket } from './useWebSocket';
import { pricesStore, usePricesAll } from '../store/prices';

export function usePrices() {
  // Subscribe to the global prices Map (components still using this
  // will re-render on any change). Prefer usePrice(tickerId) for fine-grained updates.
  const prices = usePricesAll();

  // Buffer incoming websocket updates and flush in batches.
  const bufferRef = useRef<Map<string, number>>(new Map());
  const timerRef = useRef<number | null>(null);

  const flush = useCallback(() => {
    const buf = bufferRef.current;
    if (buf.size === 0) return;
    const batch = new Map(buf);
    buf.clear();
    pricesStore.updateBatch(batch);
  }, []);

  useEffect(() => {
    // Start a 500ms interval for throttled batch updates
    timerRef.current = window.setInterval(flush, 250);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      // Final flush on cleanup
      flush();
    };
  }, [flush]);

  const onMessage = useCallback((msg: any) => {
    if (msg?.ticker_id && typeof msg?.price === 'number') {
      bufferRef.current.set(String(msg.ticker_id), Number(msg.price));
    }
  }, []);

  useWebSocket(onMessage);
  return prices;
}
