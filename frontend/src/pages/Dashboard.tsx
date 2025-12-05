import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import { formatCurrencyDisplay, toFixedString, REPORT_ROUNDING, formatWithThousands } from '../utils/numfmt';
import DashboardLayout from '../components/DashboardLayout';
import type { TickerResponse, MoverResponse, Portfolio } from '../interfaces';
import { usePricesAll, usePricesVersion } from '../store/prices';
import HoldingsTable from '../components/HoldingsTable';
import OpenOrders from '../components/OpenOrders';
import { SkeletonCard, SkeletonRow } from '../components/Skeleton';

//

export default function Dashboard() {
  const navigate = useNavigate();
  const prices = usePricesAll();
  const pricesVersion = usePricesVersion();

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

  const portfolioQ = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => api.get('me/portfolio').json<Portfolio>(),
  });

  const myAssets = useMemo(() => {
    if (!portfolioQ.data) return [];
    
    return portfolioQ.data.assets.map(a => {
      const p = prices.get(a.ticker_id);
      const assetQuantity = Number(a.quantity);
      const assetAveragePrice = Number(a.average_price);
      const assetCurrentPrice = p !== undefined ? p : Number(a.current_price);

      const totalValue = assetCurrentPrice * assetQuantity;
      let profitRate = 0;
      if (assetAveragePrice * assetQuantity !== 0) {
          profitRate = ((totalValue - (assetAveragePrice * assetQuantity)) / Math.abs(assetAveragePrice * assetQuantity)) * 100;
      }

      return {
          ...a,
          current_price: assetCurrentPrice.toString(),
          total_value: totalValue.toString(),
          profit_rate: profitRate.toFixed(2).toString()
      };
    });
  }, [portfolioQ.data, prices]);

  const filteredTickers = useMemo(() => {
    const list = tickersQ.data || [];
    return list.filter(t => (category === 'ALL' ? true : t.market_type === category) &&
      (search.trim() ? (t.symbol.toLowerCase().includes(search.toLowerCase()) || t.name.toLowerCase().includes(search.toLowerCase())) : true));
  }, [tickersQ.data, category, search]);

  // Merge real-time prices
  const mergePrice = (t: TickerResponse) => {
    const p = prices.get(t.id);
    if (p === undefined) return t;
    
    const current = Number(t.current_price || 0);
    const change = Number(t.change_percent || 0);
    
    // Calculate previous close from initial data
    const prev = current / (1 + change / 100);
    
    // Calculate new change percent
    // Avoid division by zero if prev is 0 (unlikely but possible)
    const newChange = prev !== 0 ? ((p - prev) / prev) * 100 : 0;
    
    return { ...t, current_price: String(p), change_percent: String(newChange) };
  };

  // Helper to merge real-time price into MoverResponse
  const mergeMover = (m: MoverResponse) => {
    const p = prices.get(m.ticker.id);
    if (p === undefined) return m;
    
    const currentPrice = p;
    // Use the pricing data from the MoverResponse itself as the baseline
    const initialPrice = Number(m.price);
    const initialChange = Number(m.change_percent);
    
    const prev = initialPrice / (1 + initialChange / 100);
    const newChange = prev !== 0 ? ((currentPrice - prev) / prev) * 100 : 0;
    
    return {
      ...m,
      price: String(currentPrice),
      change_percent: String(newChange),
      ticker: { 
        ...m.ticker, 
        current_price: String(currentPrice), 
        change_percent: String(newChange) 
      }
    };
  };

  const displayedTickers = useMemo(() => {
    return filteredTickers.map(mergePrice);
  }, [filteredTickers, pricesVersion]);

  const displayedGainers = useMemo(() => {
    return (gainersQ.data || []).map(mergeMover);
  }, [gainersQ.data, pricesVersion]);

  const displayedLosers = useMemo(() => {
    return (losersQ.data || []).map(mergeMover);
  }, [losersQ.data, pricesVersion]);

  const displayedTrending = useMemo(() => {
    return (trendingQ.data || []).map(mergeMover);
  }, [trendingQ.data, pricesVersion]);

  //

  const onTrade = (t: TickerResponse) => {
    navigate(`/market/${t.id}`);
  };

  return (
    <DashboardLayout>
      <div className="relative flex h-auto min-h-screen w-full flex-col bg-background-light dark:bg-background-dark overflow-x-hidden">
        <div className="px-4 sm:px-6 md:px-8 lg:px-10 xl:px-12 flex-1 py-5">
          {/* Header */}
          <header className="w-full px-4 pt-6 pb-3">
            <h1 className="text-white tracking-tight text-[32px] font-bold leading-tight">Market Overview</h1>
          </header>

          {/* Gainers / Losers / Trending */}
          <section className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {gainersQ.isLoading ? (
                <SkeletonCard />
              ) : (
                <Card title="Top Gainers" icon="trending_up" iconClass="text-profit">
                  <ListMovers data={displayedGainers} />
                </Card>
              )}
              {losersQ.isLoading ? (
                <SkeletonCard />
              ) : (
                <Card title="Top Losers" icon="trending_down" iconClass="text-loss">
                  <ListMovers data={displayedLosers} />
                </Card>
              )}
              {trendingQ.isLoading ? (
                <SkeletonCard />
              ) : (
                <Card title="Trending Now" icon="bolt" iconClass="text-profit">
                  <ListMovers data={displayedTrending} />
                </Card>
              )}
            </div>
          </section>

          {/* My Holdings */}
          <section className="px-4 pb-6">
             <HoldingsTable assets={myAssets} isLoading={portfolioQ.isLoading} />
          </section>

          {/* Open Orders */}
          <section className="px-4 pb-6">
             <OpenOrders />
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
                      <th className="p-4 text-sm font-semibold text-white tracking-wider text-right">Div Yield</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider text-right">Volume</th>
                      <th className="p-4 text-sm font-semibold text-white tracking-wider text-center">Trade</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#314368]">
                    {tickersQ.isLoading ? (
                        Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={7} />)
                    ) : (
                      displayedTickers.slice(0, 50).map(t => {
                      const change = Number(t.change_percent || 0);
                      const isPositive = change >= 0;
                      return (
                        <tr key={t.id} className="hover:bg-[#182234]">
                          <td className="p-4 text-white font-medium">{t.symbol}</td>
                          <td className="p-4 text-gray-300">{t.name}</td>
                          <td className="p-4 text-right text-white font-mono">
                            {t.current_price ? formatCurrencyDisplay(t.current_price, t.currency, 'ROUND_DOWN') : '-'} {t.currency}
                          </td>
                          <td className={`p-4 text-right font-mono font-medium ${isPositive ? 'text-profit' : 'text-loss'}`}>
                            {t.change_percent ? `${isPositive ? '+' : ''}${toFixedString(change, 2, REPORT_ROUNDING)}%` : '-'}
                          </td>
                          <td className="p-4 text-right font-mono">
                            {t.dividend_rate ? <span className="text-green-400 font-bold">{t.dividend_rate}%</span> : <span className="text-gray-600">-</span>}
                          </td>
                          <td className="p-4 text-right text-gray-400 font-mono">
                            {t.volume ? formatWithThousands(toFixedString(t.volume, 0, 'ROUND_DOWN')) : '-'}
                          </td>
                          <td className="p-4 text-center">
                            <button onClick={() => onTrade(t)} className="h-8 px-4 rounded-md bg-primary text-background-dark font-semibold text-sm hover:bg-primary/90">Trade</button>
                          </td>
                        </tr>
                      );
                    }))}
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

function ListMovers({ data }: { data?: MoverResponse[] }) {
  const items = (data || []).slice(0, 3);
  return (
    <>
      {items.map((m, i) => {
        const change = Number(m.change_percent);
        const isPositive = change >= 0;

        return (
          <div key={i} className="flex justify-between items-center">
            <p className="text-white tracking-light text-lg font-bold">{m.ticker.symbol}</p>
            <p className={`${isPositive ? 'text-profit' : 'text-loss'} text-base font-medium`}>
              {m.change_percent ? `${isPositive ? '+' : ''}${toFixedString(change, 1, REPORT_ROUNDING)}%` : '-'}
            </p>
          </div>
        );
      })}
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