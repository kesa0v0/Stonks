// frontend/src/store/openOrders.ts
import { useSyncExternalStore } from 'react';
import type { OrderListItem } from '../interfaces';

class OpenOrdersStore {
  private orders: Map<string, OrderListItem[]> = new Map(); // Keyed by userId
  private keyListeners: Map<string, Set<() => void>> = new Map();

  subscribeKey = (key: string, listener: () => void) => {
    let set = this.keyListeners.get(key);
    if (!set) {
      set = new Set();
      this.keyListeners.set(key, set);
    }
    set.add(listener);
    return () => set && set.delete(listener);
  };

  getSnapshotKey = (key: string) => this.orders.get(key);
  
  updateOpenOrders = (userId: string, openOrders: OrderListItem[]) => {
    const prev = this.orders.get(userId);
    // Deep compare to avoid unnecessary re-renders
    if (JSON.stringify(prev) !== JSON.stringify(openOrders)) {
      this.orders.set(userId, openOrders);
      const set = this.keyListeners.get(userId);
      if (set) {
        for (const l of set) {
          try { l(); } catch {}
        }
      }
    }
  };
}

export const openOrdersStore = new OpenOrdersStore();

export function useOpenOrders(userId: string) {
  return useSyncExternalStore(
    (listener) => openOrdersStore.subscribeKey(userId, listener),
    () => openOrdersStore.getSnapshotKey(userId),
    () => openOrdersStore.getSnapshotKey(userId)
  );
}
