// frontend/src/store/orderBook.ts
import { useEffect } from 'react';
import { create } from 'zustand';
import type { OrderBookResponse } from '../interfaces';

interface OrderBookState {
  orderBooks: Record<string, OrderBookResponse | null>;
  listeners: Record<string, number>;
  
  updateOrderBook: (tickerId: string, data: OrderBookResponse | null) => void;
  subscribeKey: (tickerId: string) => void;
  unsubscribeKey: (tickerId: string) => void;
  getActiveKeys: () => string[];
}

export const useOrderBookStore = create<OrderBookState>((set, get) => ({
  orderBooks: {},
  listeners: {},

  updateOrderBook: (tickerId, data) => set((state) => {
    if (!data) {
      const nextBooks = { ...state.orderBooks };
      delete nextBooks[tickerId];
      return { orderBooks: nextBooks };
    }

    const prev = state.orderBooks[tickerId];
    // Race condition check
    if (prev?.timestamp && data.timestamp) {
      if (data.timestamp < prev.timestamp) {
        console.warn(`[OrderBookStore] Ignoring stale update for ${tickerId}`);
        return state;
      }
    }

    return {
      orderBooks: { ...state.orderBooks, [tickerId]: data }
    };
  }),

  subscribeKey: (tickerId) => set((state) => ({
    listeners: { 
      ...state.listeners, 
      [tickerId]: (state.listeners[tickerId] || 0) + 1 
    }
  })),

  unsubscribeKey: (tickerId) => set((state) => {
    const count = state.listeners[tickerId] || 0;
    if (count <= 1) {
      const nextListeners = { ...state.listeners };
      delete nextListeners[tickerId];
      return { listeners: nextListeners };
    }
    return {
      listeners: { ...state.listeners, [tickerId]: count - 1 }
    };
  }),

  getActiveKeys: () => Object.keys(get().listeners),
}));

// Compatibility layer
export const orderBookStore = {
  updateOrderBook: (tickerId: string, data: OrderBookResponse | null) => 
    useOrderBookStore.getState().updateOrderBook(tickerId, data),
  
  getActiveKeys: () => useOrderBookStore.getState().getActiveKeys(),
  
  getSnapshotKey: (tickerId: string) => useOrderBookStore.getState().orderBooks[tickerId] || null,
};

export function useOrderBook(tickerId: string) {
  const subscribe = useOrderBookStore((state) => state.subscribeKey);
  const unsubscribe = useOrderBookStore((state) => state.unsubscribeKey);
  
  useEffect(() => {
    subscribe(tickerId);
    return () => unsubscribe(tickerId);
  }, [tickerId, subscribe, unsubscribe]);

  return useOrderBookStore((state) => state.orderBooks[tickerId] || null);
}
