import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import DashboardLayout from '../components/DashboardLayout';
import type { TickerResponse, MoverResponse } from '../interfaces';

//

export default function Dashboard() {
  const navigate = useNavigate();
  // Categories & search
  const [category, setCategory] = useState<'ALL' | 'KRX' | 'US' | 'CRYPTO' | 'HUMAN'>('ALL');
  const [search, setSearch] = useState('');
  

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

  //

  const onTrade = (t: TickerResponse) => {
    navigate(`/market/${t.id}`);
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
                  <div className="text-[#90a4cb] flex bg-[#182234] items-center justify-center pl-4 rounded-l-lg border border-[#314368] border-r-0">
                    <span className="material-symbols-outlined">search</span>
                  </div>
                  <input className="form-input flex w-full min-w-0 flex-1 rounded-r-lg text-white bg-[#182234] h-full placeholder:text-[#90a4cb] px-4 pl-2 text-base font-normal border border-[#314368] border-l-0 focus:ring-1 focus:ring-primary focus:border-primary" placeholder="Search assets..." value={search} onChange={e => setSearch(e.target.value)} />
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
              <div className="overflow-x-auto rounded-lg border border-[#314368] bg-[#101623]">
                <table className="w-full text-left">
                  <thead className="bg-[#182234]">
                    <tr>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider">Symbol</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider">Name</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider text-right">Price</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider text-right">24h Change</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider text-right">Volume</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider text-center">Trade</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#314368]">
                    {filteredTickers.slice(0, 50).map(t => {
                      const change = Number(t.change_percent || 0);
                      const isPositive = change >= 0;
                      return (
                        <tr key={t.id} className="hover:bg-[#182234]">
                          <td className="p-4 text-white font-medium">{t.symbol}</td>
                          <td className="p-4 text-gray-300">{t.name}</td>
                          <td className="p-4 text-right text-white font-mono">
                            {t.current_price ? Number(t.current_price).toLocaleString() : '-'} {t.currency}
                          </td>
                          <td className={`p-4 text-right font-mono font-medium ${isPositive ? 'text-primary' : 'text-[#fa5538]'}`}>
                            {t.change_percent ? `${isPositive ? '+' : ''}${change.toFixed(2)}%` : '-'}
                          </td>
                          <td className="p-4 text-right text-gray-400 font-mono">
                            {t.volume ? Number(t.volume).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '-'}
                          </td>
                          <td className="p-4 text-center">
                            <button onClick={() => onTrade(t)} className="h-8 px-4 rounded-md bg-primary text-background-dark font-semibold text-sm hover:bg-primary/90">Trade</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </main>
        </div>
      </div>

      {/* Trade Modal disabled; Trade navigates to Market page */}
    </DashboardLayout>
  );
}

function Card({ title, icon, iconClass, children }: { title: string; icon: string; iconClass?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4 rounded-lg p-6 border border-[#314368] bg-[#101623]">
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
    <button onClick={onClick} className={`flex h-8 shrink-0 items-center justify-center gap-x-2 rounded-full px-4 ${primary ? 'bg-primary/20 hover:bg-primary/30 text-primary' : 'bg-[#182234] hover:bg-[#222f49] text-white'} ${active ? 'ring-2 ring-primary' : ''}`}>
      <p className={`text-sm font-medium leading-normal`}>{label}</p>
    </button>
  );
}

//