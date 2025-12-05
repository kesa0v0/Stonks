import { useCallback, useEffect, useRef } from 'react';
import { useWebSocket } from './useWebSocket';
import { pricesStore } from '../store/prices';
import { orderBookStore } from '../store/orderBook';
import api from '../api/client';
import type { OrderBookResponse } from '../interfaces';

export function useMarketDataStream() {
  // Buffer incoming websocket updates and flush in batches.
  const priceBufferRef = useRef<Map<string, number>>(new Map());
  const orderBookRefreshQueueRef = useRef<Set<string>>(new Set()); // Tickers to refresh order book for
  const priceTimerRef = useRef<number | null>(null);
  const orderBookTimerRef = useRef<number | null>(null);

  const flushPriceBuffer = useCallback(() => {
    const buf = priceBufferRef.current;
    if (buf.size === 0) return;
    const batch = new Map(buf);
    buf.clear();
    pricesStore.updateBatch(batch);
  }, []);

  const flushOrderBookRefreshQueue = useCallback(async () => {
    const queue = orderBookRefreshQueueRef.current;
    if (queue.size === 0) return;
    
    const tickersToRefresh = new Set(queue); // Process a copy
    queue.clear();

    for (const tickerId of tickersToRefresh) {
      try {
        const data = await api.get(`market/orderbook/${tickerId}`).json<OrderBookResponse>();
        orderBookStore.updateOrderBook(tickerId, data);
      } catch (err) {
        console.error(`Failed to refresh orderbook for ${tickerId}`, err);
      }
    }
  }, []);

  useEffect(() => {
    priceTimerRef.current = window.setInterval(flushPriceBuffer, 250);
    orderBookTimerRef.current = window.setInterval(flushOrderBookRefreshQueue, 500); // Debounce order book refresh slightly more
    return () => {
      if (priceTimerRef.current) window.clearInterval(priceTimerRef.current);
      if (orderBookTimerRef.current) window.clearInterval(orderBookTimerRef.current);
      flushPriceBuffer(); // Final flush on cleanup
      flushOrderBookRefreshQueue(); // Final flush on cleanup
    };
  }, [flushPriceBuffer, flushOrderBookRefreshQueue]);

  const onMessage = useCallback((msg: any) => {
    if (!msg) return;
    
    // Handle both parsed object and string (safeguard)
    const data = typeof msg === 'string' ? JSON.parse(msg) : msg;

    // --- Price Updates ---
    if (data.type && (data.type === 'ticker' || data.type === 'price_updated') && data.ticker_id && typeof data.price === 'number') {
      priceBufferRef.current.set(String(data.ticker_id), Number(data.price));
    }
    // --- Order Book Updates & Trade Events ---
    // If it's a direct orderbook snapshot (e.g., from data_feeder for crypto)
    if (data.type === 'orderbook' && data.ticker_id && data.bids && data.asks) {
      orderBookStore.updateOrderBook(data.ticker_id, data);
      return; // Processed this message, no further action for orderbook needed
    }

    // If it's a trade event that affects the order book, queue a refresh (for Human ETFs or when snapshot not available)
    if (
      data.ticker_id && 
      ['order_created', 'trade_executed', 'order_accepted', 'order_updated', 'order_cancelled'].includes(data.type) // Trade events
    ) {
      orderBookRefreshQueueRef.current.add(data.ticker_id);
    }
  }, []);

  // Establish the single WebSocket connection
  useWebSocket(onMessage);
}

