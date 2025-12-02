import { useMemo, useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import api from '../api/client';
import DashboardLayout from '../components/DashboardLayout';
import type { TickerResponse, MoverResponse, OrderBookResponse } from '../interfaces';

const toNumber = (v: string) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
};

export default function Dashboard() {
  // Categories & search
  const [category, setCategory] = useState<'ALL' | 'KRX' | 'US' | 'CRYPTO' | 'HUMAN'>('ALL');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<TickerResponse | null>(null);
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [amount, setAmount] = useState('');
  const [price, setPrice] = useState<number>(0);

  // Queries
  const tickersQ = useQuery({
    queryKey: ['tickers'],
    queryFn: () => api.get('market/tickers').json<TickerResponse[]>(),
  });

  const gainersQ = useQuery({
    queryKey: ['movers', 'gainers'],
    queryFn: () => api.get('market/movers', { searchParams: { type: 'gainers', limit: '5' } }).json<MoverResponse[]>(),
  });
  const losersQ = useQuery({
    queryKey: ['movers', 'losers'],
    queryFn: () => api.get('market/movers', { searchParams: { type: 'losers', limit: '5' } }).json<MoverResponse[]>(),
  });
  const trendingQ = useQuery({
    queryKey: ['trending'],
    queryFn: () => api.get('market/trending', { searchParams: { limit: '5' } }).json<MoverResponse[]>(),
  });

  const filteredTickers = useMemo(() => {
    const list = tickersQ.data || [];
    return list.filter(t => (category === 'ALL' ? true : t.market_type === category) &&
      (search.trim() ? (t.symbol.toLowerCase().includes(search.toLowerCase()) || t.name.toLowerCase().includes(search.toLowerCase())) : true));
  }, [tickersQ.data, category, search]);

  // When selecting a ticker, fetch price + orderbook
  const orderbookQ = useQuery({
    queryKey: ['orderbook', selected?.id],
    queryFn: () => api.get(`market/orderbook/${selected!.id}`).json<OrderBookResponse>(),
    enabled: !!selected,
    refetchInterval: selected ? 1500 : false,
  });
  // Optionally compute mid price for display or defaults

  const placeOrder = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error('No ticker selected');
      await api.post('orders', {
        json: {
          ticker_id: selected.id,
          side,
          type: 'LIMIT',
          quantity: toNumber(amount),
          target_price: price,
        },
      });
    },
  });

  const onTrade = (t: TickerResponse) => {
    setSelected(t);
    setAmount('');
    setSide('BUY');
  };

  return (
    <DashboardLayout>
      <div className="relative flex h-auto min-h-screen w-full flex-col bg-background-light dark:bg-background-dark overflow-x-hidden">
        <div className="px-4 sm:px-8 md:px-12 lg:px-20 xl:px-40 flex-1 py-5">
          {/* Header */}
          <header className="w-full px-4 pt-6 pb-3">
            <h1 className="text-white tracking-tight text-[32px] font-bold leading-tight">Market Overview</h1>
          </header>

          {/* Gainers / Losers / Trending */}
          <section className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card title="Top Gainers" icon="trending_up" iconClass="text-primary">
                <ListMovers data={gainersQ.data} positive />
              </Card>
              <Card title="Top Losers" icon="trending_down" iconClass="text-[#fa5538]">
                <ListMovers data={losersQ.data} />
              </Card>
              <Card title="Trending Now" icon="bolt" iconClass="text-primary">
                <ListMovers data={trendingQ.data} positive />
              </Card>
            </div>
          </section>

          {/* Asset List */}
          <main className="flex flex-col">
            <header className="px-4 pt-5 pb-3">
              <h2 className="text-white text-[22px] font-bold leading-tight tracking-[-0.015em]">Asset List</h2>
            </header>

            {/* Search */}
            <div className="px-4 py-3">
              <label className="flex flex-col min-w-40 h-12 w-full">
                <div className="flex w-full items-stretch rounded-lg h-full">
                  <div className="text-[#90cba4] flex bg-[#22492f] items-center justify-center pl-4 rounded-l-lg">
                    <span className="material-symbols-outlined">search</span>
                  </div>
                  <input className="form-input flex w-full min-w-0 flex-1 rounded-r-lg text-white focus:outline-0 focus:ring-0 border-none bg-[#22492f] h-full placeholder:text-[#90cba4] px-4 pl-2 text-base font-normal" placeholder="Search assets..." value={search} onChange={e => setSearch(e.target.value)} />
                </div>
              </label>
            </div>

            {/* Categories */}
            <div className="flex gap-3 p-4 overflow-x-auto">
              <Chip active={category==='ALL'} onClick={() => setCategory('ALL')} label="All" primary />
              <Chip active={category==='KRX'} onClick={() => setCategory('KRX')} label="KRX" />
              <Chip active={category==='US'} onClick={() => setCategory('US')} label="US" />
              <Chip active={category==='CRYPTO'} onClick={() => setCategory('CRYPTO')} label="Crypto" />
              <Chip active={category==='HUMAN'} onClick={() => setCategory('HUMAN')} label="Human ETF" />
            </div>

            {/* Table */}
            <div className="p-4">
              <div className="overflow-x-auto rounded-lg border border-[#316843]">
                <table className="w-full text-left">
                  <thead className="bg-[#22492f]">
                    <tr>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider">Symbol</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider">Name</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider">Market</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider text-center">Trade</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#316843]">
                    {filteredTickers.slice(0, 50).map(t => (
                      <tr key={t.id} className="hover:bg-[#1a3824]/50">
                        <td className="p-4 text-white font-medium">{t.symbol}</td>
                        <td className="p-4 text-gray-300">{t.name}</td>
                        <td className="p-4 text-gray-300">{t.market_type}</td>
                        <td className="p-4 text-center">
                          <button onClick={() => onTrade(t)} className="h-8 px-4 rounded-md bg-primary text-background-dark font-semibold text-sm hover:bg-primary/90">Trade</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </main>
        </div>
      </div>

      {/* Trade Modal */}
      {selected && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setSelected(null)}>
          <div className="w-full max-w-xl bg-[#101623] border border-[#316843] rounded-lg p-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[#0bda43]">trending_up</span>
                <p className="text-white text-base font-medium leading-normal">{selected.symbol} / {selected.currency}</p>
              </div>
              <button className="text-white/70 hover:text-white" onClick={() => setSelected(null)}>✕</button>
            </div>

            {/* Orderbook */}
            <div className="rounded-lg border border-[#316843] bg-[#1a3824]/30 p-3 mb-4">
              <h3 className="text-white font-bold mb-2">Order Book</h3>
              <div className="grid grid-cols-2 gap-2 text-sm font-mono">
                <div>
                  <p className="text-[#fa5538] font-semibold mb-1">Asks</p>
                  {orderbookQ.data?.asks.slice(0, 8).reverse().map((a, i) => (
                    <div key={`ask-${i}`} className="flex justify-between text-white/80">
                      <span>{a.price.toLocaleString()}</span>
                      <span>{Number(a.quantity).toFixed(4)}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <p className="text-[#0bda43] font-semibold mb-1">Bids</p>
                  {orderbookQ.data?.bids.slice(0, 8).map((b, i) => (
                    <div key={`bid-${i}`} className="flex justify-between text-white/80">
                      <span>{b.price.toLocaleString()}</span>
                      <span>{Number(b.quantity).toFixed(4)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Trade form */}
            <div className="rounded-lg border border-[#316843] bg-[#1a3824]/30 p-3">
              <div className="flex bg-[#22492f] rounded-lg p-1 mb-4">
                <button 
                  onClick={() => setSide('BUY')}
                  className={`flex-1 py-2 rounded-md text-sm font-bold transition-all ${side === 'BUY' ? 'bg-primary text-background-dark' : 'text-[#90cba4] hover:text-white'}`}
                >
                  Buy
                </button>
                <button 
                  onClick={() => setSide('SELL')}
                  className={`flex-1 py-2 rounded-md text-sm font-bold transition-all ${side === 'SELL' ? 'bg-[#fa5538] text-white' : 'text-[#90cba4] hover:text-white'}`}
                >
                  Sell
                </button>
              </div>

              <form onSubmit={e => { e.preventDefault(); placeOrder.mutate(); }} className="flex flex-col gap-3">
                <div>
                  <label className="text-xs font-bold text-[#90cba4] uppercase">Price ({selected.currency})</label>
                  <input 
                    type="number" 
                    className="w-full mt-1 bg-[#22492f] border border-[#316843] rounded-lg px-3 py-2 text-white font-mono focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                    value={price}
                    onChange={(e) => setPrice(parseFloat(e.target.value))}
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-[#90cba4] uppercase">Amount</label>
                  <input 
                    type="number" 
                    step="0.0001"
                    className="w-full mt-1 bg-[#22492f] border border-[#316843] rounded-lg px-3 py-2 text-white font-mono focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                    placeholder="0.00"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                  />
                </div>
                <div className="mt-2 pt-3 border-t border-[#316843] flex justify-between text-sm">
                  <span className="text-[#90cba4]">Total</span>
                  <span className="text-white font-bold">{(price * (parseFloat(amount) || 0)).toLocaleString()} {selected.currency}</span>
                </div>
                <button 
                  type="submit" 
                  disabled={placeOrder.isPending}
                  className={`w-full py-3 rounded-lg font-bold text-white mt-2 transition-all hover:brightness-110 active:scale-95 ${side === 'BUY' ? 'bg-primary text-background-dark' : 'bg-[#fa5538]'}`}
                >
                  {placeOrder.isPending ? 'Placing...' : `${side} ${selected.symbol}`}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}

function Card({ title, icon, iconClass, children }: { title: string; icon: string; iconClass?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4 rounded-lg p-6 border border-[#316843] bg-[#1a3824]/50 backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <span className={`material-symbols-outlined ${iconClass || ''}`}>{icon}</span>
        <p className="text-white text-base font-medium leading-normal">{title}</p>
      </div>
      <div className="flex flex-col gap-3">
        {children}
      </div>
    </div>
  );
}

function ListMovers({ data, positive }: { data?: MoverResponse[]; positive?: boolean }) {
  const items = (data || []).slice(0, 3);
  return (
    <>
      {items.map((m, i) => (
        <div key={i} className="flex justify-between items-center">
          <p className="text-white tracking-light text-lg font-bold">{m.ticker.symbol}</p>
          <p className={`${(positive ?? false) || Number(m.change_percent) > 0 ? 'text-primary' : 'text-[#fa5538]'} text-base font-medium`}>{Number(m.change_percent).toFixed(1)}%</p>
        </div>
      ))}
    </>
  );
}

function Chip({ label, active, onClick, primary }: { label: string; active?: boolean; onClick?: () => void; primary?: boolean }) {
  return (
    <button onClick={onClick} className={`flex h-8 shrink-0 items-center justify-center gap-x-2 rounded-full px-4 ${primary ? 'bg-primary/20 hover:bg-primary/30 text-primary' : 'bg-[#22492f] hover:bg-[#2a5a3a]'} ${active ? 'ring-2 ring-primary' : ''}`}>
      <p className={`${primary ? 'text-sm font-medium leading-normal' : 'text-white text-sm font-medium leading-normal'}`}>{label}</p>
    </button>
  );
}

//