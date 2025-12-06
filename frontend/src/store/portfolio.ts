import { create } from 'zustand';
import type { Portfolio } from '../interfaces';

interface PortfolioState {
  portfolios: Record<string, Portfolio | null>;
  updatePortfolio: (userId: string, portfolio: Portfolio | null) => void;
}

export const usePortfolioStore = create<PortfolioState>((set) => ({
  portfolios: {},
  updatePortfolio: (userId, portfolio) => set((state) => {
    const prev = state.portfolios[userId];
    if (JSON.stringify(prev) !== JSON.stringify(portfolio)) {
      return {
        portfolios: { ...state.portfolios, [userId]: portfolio }
      };
    }
    return state;
  }),
}));

export const portfolioStore = {
  updatePortfolio: (userId: string, portfolio: Portfolio | null) => 
    usePortfolioStore.getState().updatePortfolio(userId, portfolio),
  getSnapshotKey: (userId: string) => usePortfolioStore.getState().portfolios[userId],
};

export function usePortfolio(userId: string) {
  return usePortfolioStore((state) => state.portfolios[userId]);
}
