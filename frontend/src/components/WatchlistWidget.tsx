import { Link } from 'react-router-dom';
import { usePricesAll } from '../store/prices';
import { useWatchlist } from '../hooks/useWatchlist';

function formatPrice(value: number | undefined) {
  if (value === undefined || Number.isNaN(value)) return '-';
  if (value >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 0 });
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

export default function WatchlistWidget() {
  const prices = usePricesAll();
  const { items: watchlistItems, isLoading, isPinned, toggle, mutatingId } = useWatchlist();
  const items = (watchlistItems || []).map(item => {
    const live = prices.get(item.ticker.id);
    const price = live ?? Number(item.current_price ?? item.ticker.current_price ?? 0);
    return { ...item, price };
  });

  return (
    <div className="mt-2 rounded-2xl border border-[#1f2a44] bg-[#0f1729] p-3 text-white/80">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>push_pin</span>
          <span>My Pins</span>
        </div>
        <Link to="/market" className="text-[11px] text-white/50 hover:text-white">전체보기</Link>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {[0,1,2].map(i => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-[#131d32] px-2 py-2 animate-pulse">
              <div className="h-3 w-16 bg-[#1d2a46] rounded" />
              <div className="h-3 w-12 bg-[#1d2a46] rounded" />
            </div>
          ))}
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="text-[13px] text-white/50 py-2">핀한 종목이 없습니다.</div>
      )}

      {!isLoading && items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map(({ ticker, price }) => (
            <Link
              key={ticker.id}
              to={`/market/${ticker.id}`}
              className="group flex flex-col rounded-lg px-2 py-2 hover:bg-[#131d32] transition"
            >
              <div className="flex justify-between gap-2">
                <div className="flex flex-col">
                  <span className="text-sm font-semibold text-white">{ticker.name}</span>
                  <span className="text-[11px] text-white/50 truncate max-w-[90px] block">{ticker.symbol}</span>
                </div>
                <button
                  type="button"
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggle(ticker.id); }}
                  className="p-1 rounded hover:bg-white/5 text-white/60 hover:text-white self-start"
                  aria-label={isPinned(ticker.id) ? 'Unpin' : 'Pin'}
                  disabled={mutatingId === ticker.id}
                >
                  <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: isPinned(ticker.id) ? "'FILL' 1" : "'FILL' 0" }}>push_pin</span>
                </button>
              </div>
              <div className="flex justify-between items-center gap-2 mt-1">
                <span className="text-sm font-mono text-white">{formatPrice(price)}</span>
                <span className="material-symbols-outlined text-[16px] text-white/30 group-hover:text-white/50" style={{ fontVariationSettings: "'FILL' 0" }}>chevron_right</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
