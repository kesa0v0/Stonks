import { useCallback, useState } from 'react';
import { useWebSocket } from './useWebSocket';

export function usePrices() {
  const [prices, setPrices] = useState<Map<string, number>>(new Map());

  const onMessage = useCallback((msg: any) => {
    if (msg?.ticker_id && typeof msg?.price === 'number') {
      setPrices(prev => {
        const next = new Map(prev);
        next.set(msg.ticker_id, msg.price);
        return next;
      });
    }
  }, []);

  useWebSocket(onMessage);
  return prices;
}
