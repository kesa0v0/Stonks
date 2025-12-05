import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

export function useUsdKrwRate() {
  // Query backend FX endpoint: /market/fx?base=USD&quote=KRW
  const q = useQuery({
    queryKey: ['fx', 'USD', 'KRW'],
    queryFn: async () => {
      try {
        const r = await api.get('market/fx', { searchParams: { base: 'USD', quote: 'KRW' } }).json<{ rate: number }>();
        if (typeof r.rate === 'number' && isFinite(r.rate) && r.rate > 0) return r.rate;
        throw new Error('Invalid rate');
      } catch (e) {
        // Fallback to env or default
        const raw = (import.meta as any)?.env?.VITE_USD_KRW;
        const n = Number(raw);
        return (isFinite(n) && n > 0) ? n : 1300;
      }
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
    refetchInterval: 10 * 60 * 1000,
  });

  return q.data ?? 1300;
}
