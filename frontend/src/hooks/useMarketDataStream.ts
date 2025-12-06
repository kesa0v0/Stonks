import { useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWebSocket } from './useWebSocket';
import { pricesStore } from '../store/prices';
import { orderBookStore } from '../store/orderBook';
import { openOrdersStore } from '../store/openOrders'; // Import openOrdersStore
import { portfolioStore } from '../store/portfolio';   // Import portfolioStore
import { pushNotification } from '../store/notifications';
import api, { getAccessToken, getRefreshToken } from '../api/client'; // Import getAccessToken, getRefreshToken
import type { OrderBookResponse, MeProfile, Portfolio, OrderListItem } from '../interfaces'; // Import MeProfile, Portfolio, OrderListItem

const formatQty = (value: unknown) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value ?? '');
  return num.toLocaleString('en-US', { maximumFractionDigits: 4, minimumFractionDigits: 0 });
};

const formatPrice = (value: unknown) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value ?? '');
  return num.toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 0 });
};

export function useMarketDataStream() {
  const queryClient = useQueryClient();
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

    const isMine = userIdRef.current && data.user_id === userIdRef.current;

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

    if (!isMine) return;

    // Wallet balance/portfolio changes: invalidate cached queries instead of polling
    if (data.type === 'wallet_updated') {
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['openOrders'] });
      if (userIdRef.current) {
        queryClient.invalidateQueries({ queryKey: ['portfolio', userIdRef.current] });
        queryClient.invalidateQueries({ queryKey: ['openOrders', userIdRef.current] });
      }
      return;
    }

    // --- User-specific notifications ---
    if (data.type === 'order_created' || data.type === 'order_accepted') {
      pushNotification({
        kind: 'order',
        severity: 'info',
        title: '주문 접수',
        message: `${data.side || ''} ${formatQty(data.quantity)} ${data.ticker_id || ''}${data.price ? ` @ ${formatPrice(data.price)}` : ''}`.trim(),
        tickerId: data.ticker_id,
        meta: data,
      });
    } else if (data.type === 'order_cancelled') {
      pushNotification({
        kind: 'order',
        severity: 'warning',
        title: '주문 취소됨',
        message: `${data.side || ''} ${formatQty(data.quantity)} ${data.ticker_id || ''}`.trim(),
        tickerId: data.ticker_id,
        meta: data,
      });
    } else if (data.type === 'trade_executed') {
      const pnl = Number(data.realized_pnl);
      const pnlStr = Number.isFinite(pnl) ? ` (PnL ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)})` : '';
      pushNotification({
        kind: 'trade',
        severity: 'success',
        title: '체결 완료',
        message: `${data.side || ''} ${formatQty(data.quantity)} ${data.ticker_id || ''} @ ${formatPrice(data.price)}${pnlStr}`.trim(),
        tickerId: data.ticker_id,
        meta: data,
      });
    } else if (data.type === 'liquidation') {
      pushNotification({
        kind: 'liquidation',
        severity: 'error',
        title: '강제 청산',
        message: `증거금 부족으로 포지션이 청산되었습니다 (${data.ticker_id || ''})`,
        tickerId: data.ticker_id,
        meta: data,
      });
    }
  }, [queryClient]);

  // Establish the single WebSocket connection
  useWebSocket(onMessage);
}

