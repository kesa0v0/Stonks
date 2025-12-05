// frontend/src/store/portfolio.ts
import { useSyncExternalStore } from 'react';
import type { Portfolio } from '../interfaces';

class PortfolioStore {
  private portfolios: Map<string, Portfolio | null> = new Map(); // Keyed by userId
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

  getSnapshotKey = (key: string) => this.portfolios.get(key);
  
  updatePortfolio = (userId: string, portfolio: Portfolio | null) => {
    const prev = this.portfolios.get(userId);
    // Deep compare to avoid unnecessary re-renders
    if (JSON.stringify(prev) !== JSON.stringify(portfolio)) {
      this.portfolios.set(userId, portfolio);
      const set = this.keyListeners.get(userId);
      if (set) {
        for (const l of set) {
          try { l(); } catch {}
        }
      }
    }
  };
}

export const portfolioStore = new PortfolioStore();

export function usePortfolio(userId: string) {
  return useSyncExternalStore(
    (listener) => portfolioStore.subscribeKey(userId, listener),
    () => portfolioStore.getSnapshotKey(userId),
    () => portfolioStore.getSnapshotKey(userId)
  );
}
