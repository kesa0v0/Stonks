import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../api/client';
import type { TickerResponse } from '../interfaces';

export interface WatchlistItem {
  ticker: TickerResponse;
  current_price: number;
}

export function useWatchlist() {
  const qc = useQueryClient();
  const [mutatingId, setMutatingId] = useState<string | null>(null);

  const watchlistQ = useQuery<WatchlistItem[]>({
    queryKey: ['watchlist'],
    queryFn: async () => api.get('me/watchlist').json<WatchlistItem[]>(),
    staleTime: 60_000,
    retry: 1,
  });

  const addMutation = useMutation({
    mutationFn: async (tickerId: string) => {
      setMutatingId(tickerId);
      await api.post(`me/watchlist/${tickerId}`).json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
    onSettled: () => setMutatingId(null),
  });

  const removeMutation = useMutation({
    mutationFn: async (tickerId: string) => {
      setMutatingId(tickerId);
      await api.delete(`me/watchlist/${tickerId}`).json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
    onSettled: () => setMutatingId(null),
  });

  const isPinned = useMemo(() => {
    const ids = new Set((watchlistQ.data || []).map(w => w.ticker.id));
    return (tickerId: string) => ids.has(tickerId);
  }, [watchlistQ.data]);

  const toggle = (tickerId: string) => {
    if (isPinned(tickerId)) {
      removeMutation.mutate(tickerId);
    } else {
      addMutation.mutate(tickerId);
    }
  };

  return {
    items: watchlistQ.data || [],
    isLoading: watchlistQ.isLoading,
    isError: watchlistQ.isError,
    isPinned,
    toggle,
    mutatingId,
  };
}
