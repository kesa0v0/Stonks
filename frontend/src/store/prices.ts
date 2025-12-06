import { create } from 'zustand';

interface PricesState {
  prices: Record<string, number>;
  version: number;
  updateBatch: (updates: Map<string, number>) => void;
}

export const usePricesStore = create<PricesState>((set) => ({
  prices: {},
  version: 0,
  updateBatch: (updates) => set((state) => {
    if (updates.size === 0) return state;
    
    let hasChanges = false;
    const nextPrices = { ...state.prices };
    
    for (const [key, value] of updates) {
      if (nextPrices[key] !== value) {
        nextPrices[key] = value;
        hasChanges = true;
      }
    }

    if (!hasChanges) return state;

    return {
      prices: nextPrices,
      version: state.version + 1
    };
  }),
}));

// Compatibility layer for existing code
export const pricesStore = {
  updateBatch: (updates: Map<string, number>) => usePricesStore.getState().updateBatch(updates),
};

export function usePricesAll() {
  return usePricesStore((state) => state.prices);
}

export function usePrice(tickerId: string) {
  return usePricesStore((state) => state.prices[tickerId]);
}

export function usePricesVersion() {
  return usePricesStore((state) => state.version);
}
