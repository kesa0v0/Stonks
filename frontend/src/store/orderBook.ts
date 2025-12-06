// frontend/src/store/orderBook.ts
import { useSyncExternalStore } from 'react';
import type { OrderBookResponse } from '../interfaces';

class OrderBookStore {
  private orderBooks: Map<string, OrderBookResponse | null> = new Map();
  private keyListeners: Map<string, Set<() => void>> = new Map();
  private version = 0; // Global version for re-rendering all subscribers if needed

  subscribeKey = (key: string, listener: () => void) => {
    let set = this.keyListeners.get(key);
    if (!set) {
      set = new Set();
      this.keyListeners.set(key, set);
    }
    set.add(listener);
    return () => set && set.delete(listener);
  };

  getSnapshotKey = (key: string) => this.orderBooks.get(key);
  
  /**
   * Returns list of ticker IDs that are currently being observed by components.
   * Useful for refreshing data on reconnection.
   */
  getActiveKeys = () => {
      const active: string[] = [];
      for (const [key, listeners] of this.keyListeners.entries()) {
          if (listeners.size > 0) {
              active.push(key);
          }
      }
      return active;
  };
  
  updateOrderBook = (tickerId: string, orderBook: OrderBookResponse | null) => {
    if (!orderBook) {
        this.orderBooks.delete(tickerId);
        // Notify listeners
        const set = this.keyListeners.get(tickerId);
        if (set) for (const l of set) { try { l(); } catch {} }
        return;
    }

    const prev = this.orderBooks.get(tickerId);
    
    // Race Condition Protection:
    // If we have a previous snapshot with a timestamp, and the new one also has a timestamp,
    // ensure the new one is actually newer.
    if (prev?.timestamp && orderBook.timestamp) {
        if (orderBook.timestamp < prev.timestamp) {
            console.warn(`[OrderBookStore] Ignoring stale update for ${tickerId}. Current: ${prev.timestamp}, New: ${orderBook.timestamp}`);
            return;
        }
    }

    if (prev !== orderBook) { 
      this.orderBooks.set(tickerId, orderBook);
      this.version++;
      const set = this.keyListeners.get(tickerId);
      if (set) {
        for (const l of set) {
          try { l(); } catch {}
        }
      }
    }
  };
}

export const orderBookStore = new OrderBookStore();

export function useOrderBook(tickerId: string) {
  return useSyncExternalStore(
    (listener) => orderBookStore.subscribeKey(tickerId, listener),
    () => orderBookStore.getSnapshotKey(tickerId),
    () => orderBookStore.getSnapshotKey(tickerId)
  );
}
