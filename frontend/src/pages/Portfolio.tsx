import { useState, useEffect, useMemo } from 'react';
import api from '../api/client';
import DashboardLayout from '../components/DashboardLayout';
import type { Portfolio as IPortfolio, OrderListItem } from '../interfaces';
import { usePrices } from '../hooks/usePrices';

export default function Portfolio() {
  const [fetchedPortfolio, setFetchedPortfolio] = useState<IPortfolio | null>(null);
  const [orders, setOrders] = useState<OrderListItem[]>([]);
  const prices = usePrices();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [pf, ord] = await Promise.all([
          api.get('me/portfolio').json<IPortfolio>(),
          api.get('me/orders').json<OrderListItem[]>()
        ]);
        setFetchedPortfolio(pf);
        setOrders(ord);
      } catch (err) {
        console.error("Failed to load portfolio data", err);
      }
    };
    fetchData();
  }, []);

  const portfolio = useMemo(() => {
    if (!fetchedPortfolio) return null;

    const updatedAssets = fetchedPortfolio.assets.map(a => {
      const p = prices.get(a.ticker_id);
      if (p !== undefined) {
        return { ...a, current_price: p, total_value: p * a.quantity };
      }
      return a;
    });

    const newTotalValue = updatedAssets.reduce((acc, cur) => acc + cur.total_value, 0) + fetchedPortfolio.cash_balance;

    // Calculate real-time change percent
    let newChange = fetchedPortfolio.total_asset_change_percent;
    if (fetchedPortfolio.total_asset_change_percent && fetchedPortfolio.total_asset_value > 0) {
        const oldTotal = fetchedPortfolio.total_asset_value;
        const oldChange = Number(fetchedPortfolio.total_asset_change_percent);
        // Calculate previous total value (e.g., yesterday's close)
        const prevTotal = oldTotal / (1 + oldChange / 100);
        
        if (prevTotal !== 0) {
             const changeVal = ((newTotalValue - prevTotal) / prevTotal) * 100;
             newChange = changeVal.toFixed(2);
        }
    }

    return {
        ...fetchedPortfolio,
        assets: updatedAssets,
        total_asset_value: newTotalValue,
        total_asset_change_percent: newChange
    };
  }, [fetchedPortfolio, prices]);

  const isLoading = !portfolio;

  // 도넛 차트용 데이터 계산 (간단 예시)
  const stockVal = portfolio ? portfolio.assets.filter(a => !a.ticker_id.includes('COIN')).reduce((acc, cur) => acc + cur.total_value, 0) : 0;
  const cryptoVal = portfolio ? portfolio.assets.filter(a => a.ticker_id.includes('COIN')).reduce((acc, cur) => acc + cur.total_value, 0) : 0;
  const totalVal = portfolio ? Math.max(portfolio.total_asset_value, 1) : 1; // 0 나누기 방지
  
  const stockPct = (stockVal / totalVal) * 100;
  const cryptoPct = (cryptoVal / totalVal) * 100;
  const cashPct = portfolio ? (portfolio.cash_balance / totalVal) * 100 : 0;

  // SVG Dash Arrays for Donut Chart
  const r = 15.9155;
  const stockDash = `${stockPct} ${100 - stockPct}`;
  const cryptoDash = `${cryptoPct} ${100 - cryptoPct}`;
  const cashDash = `${cashPct} ${100 - cashPct}`;
  
  const stockOffset = 25; 
  const cryptoOffset = 25 + 100 - stockPct; 
  const cashOffset = 25 + 100 - stockPct - cryptoPct;

  return (
    <DashboardLayout>
      <h1 className="text-white text-3xl font-bold mb-6">Personal Financial Overview</h1>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {isLoading ? (
          <SkeletonCard />
        ) : (
              <StatCard 
                title="Total Asset Value" 
                value={`$${Math.floor(portfolio.total_asset_value).toLocaleString()}`} 
                trend={portfolio.total_asset_change_percent ? `${Number(portfolio.total_asset_change_percent) >= 0 ? '+' : ''}${portfolio.total_asset_change_percent}%` : undefined}
                trendPositive={Number(portfolio.total_asset_change_percent || 0) >= 0}
              />
        )}
        {isLoading ? (
          <SkeletonCard />
        ) : (
          <StatCard title="Available Cash" value={`$${Math.floor(portfolio.cash_balance).toLocaleString()}`} />
        )}
        {isLoading ? (
          <SkeletonCard />
        ) : (
          <StatCard title="Total Positions" value={portfolio.assets.length.toString()} />
        )}
      </div>

      {/* Chart Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 flex flex-col gap-4 p-6 rounded-xl border border-[#314368] bg-[#101623]">
          <h2 className="text-white text-xl font-bold">Portfolio Allocation</h2>
          <div className="flex items-center justify-center grow relative min-h-[300px]">
            {isLoading ? (
              <div className="w-full h-full max-w-xs max-h-xs animate-pulse">
                <div className="w-full h-full rounded-full bg-[#182234]" />
              </div>
            ) : (
              <>
                <svg className="w-full h-full max-w-xs max-h-xs" viewBox="0 0 36 36">
                  <path className="stroke-[#222f49]" d={`M18 2.0845 a ${r} ${r} 0 0 1 0 31.831 a ${r} ${r} 0 0 1 0 -31.831`} fill="none" strokeWidth="3" />
                  <path className="stroke-[#0d59f2]" strokeDasharray={stockDash} strokeDashoffset={stockOffset} d={`M18 2.0845 a ${r} ${r} 0 0 1 0 31.831 a ${r} ${r} 0 0 1 0 -31.831`} fill="none" strokeWidth="3" />
                  <path className="stroke-[#8b5cf6]" strokeDasharray={cryptoDash} strokeDashoffset={cryptoOffset} d={`M18 2.0845 a ${r} ${r} 0 0 1 0 31.831 a ${r} ${r} 0 0 1 0 -31.831`} fill="none" strokeWidth="3" />
                  <path className="stroke-[#10b981]" strokeDasharray={cashDash} strokeDashoffset={cashOffset} d={`M18 2.0845 a ${r} ${r} 0 0 1 0 31.831 a ${r} ${r} 0 0 1 0 -31.831`} fill="none" strokeWidth="3" />
                </svg>
                <div className="absolute flex flex-col items-center justify-center">
                  <p className="text-[#90a4cb] text-sm">Total Value</p>
                  <p className="text-white text-xl font-bold">${Math.floor(portfolio.total_asset_value).toLocaleString()}</p>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-col gap-4 p-6 rounded-xl border border-[#314368] bg-[#101623] justify-center">
          {isLoading ? (
            <>
              <SkeletonLine />
              <SkeletonLine />
              <SkeletonLine />
            </>
          ) : (
            <>
              <LegendItem color="bg-[#0d59f2]" label="Stocks" pct={stockPct} />
              <LegendItem color="bg-[#8b5cf6]" label="Crypto" pct={cryptoPct} />
              <LegendItem color="bg-[#10b981]" label="Cash" pct={cashPct} />
            </>
          )}
        </div>
      </div>

      {/* Recent Trade History */}
      <div className="flex flex-col gap-4">
        <h2 className="text-white text-xl font-bold">Recent Trade History</h2>
        <div className="rounded-lg border border-[#314368] bg-[#101623] overflow-hidden">
          {isLoading ? (
            <div className="p-6 space-y-3">
              <SkeletonLine wide />
              <SkeletonLine wide />
              <SkeletonLine wide />
            </div>
          ) : (
            <table className="w-full text-left">
              <thead className="bg-[#182234]">
                <tr>
                  <th className="px-6 py-4 text-[#90a4cb] text-sm font-medium">Date</th>
                  <th className="px-6 py-4 text-[#90a4cb] text-sm font-medium">Ticker</th>
                  <th className="px-6 py-4 text-[#90a4cb] text-sm font-medium text-center">Side</th>
                  <th className="px-6 py-4 text-[#90a4cb] text-sm font-medium text-right">Price</th>
                  <th className="px-6 py-4 text-[#90a4cb] text-sm font-medium text-right">Quantity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#314368]">
                {orders.map((order) => (
                  <tr key={order.id} className="hover:bg-[#182234] transition-colors">
                    <td className="px-6 py-4 text-white/70 text-sm">{new Date(order.created_at).toLocaleDateString()}</td>
                    <td className="px-6 py-4 text-white font-bold">{order.ticker_id.split('-').pop()}</td>
                    <td className="px-6 py-4 text-center">
                          <span className={`inline-flex items-center justify-center rounded-full h-7 px-3 text-xs font-bold ${order.side === 'BUY' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'}`}>
                        {order.side}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right text-white/70">{order.price ? Number(order.price).toLocaleString() : '-'}</td>
                    <td className="px-6 py-4 text-right text-white/70">{Number(order.quantity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}

const StatCard = ({ title, value, trend, trendPositive }: { title: string, value: string, trend?: string, trendPositive?: boolean }) => (
  <div className="flex flex-col gap-2 rounded-xl p-6 border border-[#314368] bg-[#101623]">
    <p className="text-[#90a4cb] text-sm font-medium">{title}</p>
    <p className="text-white text-3xl font-bold">{value}</p>
    {trend && (
            <div className={`flex items-center gap-1 text-sm font-medium ${trendPositive ? 'text-profit' : 'text-loss'}`}>
        <span className="material-symbols-outlined text-base">{trendPositive ? 'arrow_upward' : 'arrow_downward'}</span>
        <span>{trend}</span>
      </div>
    )}
  </div>
);

const LegendItem = ({ color, label, pct }: { color: string, label: string, pct: number }) => (
  <div className="flex items-center gap-3">
    <div className={`size-3 rounded-full ${color}`}></div>
    <div className="flex justify-between items-baseline w-full">
      <span className="text-white">{label}</span>
      <span className="text-[#90a4cb] font-mono">{pct.toFixed(1)}%</span>
    </div>
  </div>
);

const SkeletonCard = () => (
  <div className="flex flex-col gap-2 rounded-xl p-6 border border-[#314368] bg-[#101623] animate-pulse">
    <div className="h-4 w-24 bg-[#182234] rounded" />
    <div className="h-7 w-32 bg-[#182234] rounded" />
    <div className="h-3 w-16 bg-[#182234] rounded" />
  </div>
);

const SkeletonLine = ({ wide }: { wide?: boolean }) => (
  <div className={`h-4 ${wide ? 'w-full' : 'w-48'} bg-[#182234] rounded animate-pulse`} />
);