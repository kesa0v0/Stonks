import { create } from 'zustand';
import type { OrderListItem } from '../interfaces';

interface OpenOrdersState {
  orders: Record<string, OrderListItem[]>;
  updateOpenOrders: (userId: string, openOrders: OrderListItem[]) => void;
}

export const useOpenOrdersStore = create<OpenOrdersState>((set) => ({
  orders: {},
  updateOpenOrders: (userId, openOrders) => set((state) => {
    const prev = state.orders[userId];
    // Deep compare check (simple JSON stringify for now, consistent with previous implementation)
    if (JSON.stringify(prev) !== JSON.stringify(openOrders)) {
      return {
        orders: { ...state.orders, [userId]: openOrders }
      };
    }
    return state;
  }),
}));

export const openOrdersStore = {
  updateOpenOrders: (userId: string, openOrders: OrderListItem[]) => 
    useOpenOrdersStore.getState().updateOpenOrders(userId, openOrders),
  getSnapshotKey: (userId: string) => useOpenOrdersStore.getState().orders[userId],
};

export function useOpenOrders(userId: string) {
  return useOpenOrdersStore((state) => state.orders[userId]);
}
