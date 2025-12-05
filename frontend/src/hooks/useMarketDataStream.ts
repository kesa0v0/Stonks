import { useCallback, useEffect, useRef } from 'react';
import { useWebSocket } from './useWebSocket';
import { pricesStore } from '../store/prices';
import { orderBookStore } from '../store/orderBook';
import { openOrdersStore } from '../store/openOrders'; // Import openOrdersStore
import { portfolioStore } from '../store/portfolio';   // Import portfolioStore
import api, { getAccessToken, getRefreshToken } from '../api/client'; // Import getAccessToken, getRefreshToken
import type { OrderBookResponse, MeProfile, Portfolio, OrderListItem } from '../interfaces'; // Import MeProfile, Portfolio, OrderListItem

export function useMarketDataStream() {
  // Buffer incoming websocket updates and flush in batches.
  const priceBufferRef = useRef<Map<string, number>>(new Map());
  const orderBookRefreshQueueRef = useRef<Set<string>>(new Set()); // Tickers to refresh order book for
  const userRelatedRefreshQueueRef = useRef<Set<string>>(new Set()); // Queue for user-specific data refresh
  const userIdRef = useRef<string | null>(null); // To store current user's ID

  const priceTimerRef = useRef<number | null>(null);
  const orderBookTimerRef = useRef<number | null>(null);
  const userRefreshTimerRef = useRef<number | null>(null);

  // --- Flush Functions ---
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

  const flushUserRelatedRefreshQueue = useCallback(async () => {
    const queue = userRelatedRefreshQueueRef.current;
    if (queue.size === 0) return;

    const userIdsToRefresh = new Set(queue);
    queue.clear();

    for (const uId of userIdsToRefresh) {
      // Refresh Open Orders for this user
      try {
        const openOrders = await api.get('me/orders/open').json<OrderListItem[]>();
        openOrdersStore.updateOpenOrders(uId, openOrders);
      } catch (err) {
        console.error(`Failed to refresh open orders for user ${uId}`, err);
      }
      // Refresh Portfolio for this user
      try {
        const portfolio = await api.get('me/portfolio').json<Portfolio>();
        portfolioStore.updatePortfolio(uId, portfolio);
      } catch (err) {
        console.error(`Failed to refresh portfolio for user ${uId}`, err);
      }
    }
  }, []);

  // --- Effects ---
  useEffect(() => {
    // Start timers for flushing buffers
    priceTimerRef.current = window.setInterval(flushPriceBuffer, 250);
    orderBookTimerRef.current = window.setInterval(flushOrderBookRefreshQueue, 500);
    userRefreshTimerRef.current = window.setInterval(flushUserRelatedRefreshQueue, 750); // Slightly slower debounce for user-specific data

    // Cleanup timers
    return () => {
      if (priceTimerRef.current) window.clearInterval(priceTimerRef.current);
      if (orderBookTimerRef.current) window.clearInterval(orderBookTimerRef.current);
      if (userRefreshTimerRef.current) window.clearInterval(userRefreshTimerRef.current);
      flushPriceBuffer(); 
      flushOrderBookRefreshQueue();
      flushUserRelatedRefreshQueue(); // Final flush on cleanup
    };
  }, [flushPriceBuffer, flushOrderBookRefreshQueue, flushUserRelatedRefreshQueue]);

  useEffect(() => {
    // Fetch current user ID on mount only if authenticated
    const hasToken = !!getAccessToken() || !!getRefreshToken();
    if (!hasToken) {
      userIdRef.current = null;
      return;
    }

    let isMounted = true;
    api.get('auth/login/me').json<MeProfile>()
      .then(me => {
          if (isMounted) {
              userIdRef.current = me.id;
          }
      })
      .catch(err => {
        // Suppress 401 errors for unauthenticated users, as it's expected
        if (err.response && err.response.status === 401) {
            userIdRef.current = null; // Ensure userId is cleared
        } else {
            console.error("Failed to fetch current user for WS filtering", err);
        }
      });
    return () => { isMounted = false; };
  }, []); // Run once on mount

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
      
      // Also trigger refresh for user-specific data if the event is for the current user
      if (userIdRef.current && data.user_id === userIdRef.current) {
        userRelatedRefreshQueueRef.current.add(userIdRef.current);
      }
    }
  }, []);

  // Establish the single WebSocket connection
  useWebSocket(onMessage);
}

