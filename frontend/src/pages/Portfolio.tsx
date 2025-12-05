import { useState, useEffect, useMemo } from 'react';
import Decimal from 'decimal.js';
import { toFixedString, REPORT_ROUNDING, formatWithThousands, getAssetQuantityDigits, formatCurrencyDisplay } from '../utils/numfmt';
import api from '../api/client';
import DashboardLayout from '../components/DashboardLayout';
import type { Portfolio as IPortfolio, OrderListItem, TickerResponse } from '../interfaces';
import { usePricesAll, usePricesVersion } from '../store/prices';
import OpenOrders from '../components/OpenOrders';
import HoldingsTable from '../components/HoldingsTable';
import { useQuery } from '@tanstack/react-query';

export default function Portfolio() {
  const [fetchedPortfolio, setFetchedPortfolio] = useState<IPortfolio | null>(null);
  const [orders, setOrders] = useState<OrderListItem[]>([]);
  const prices = usePricesAll();
  const pricesVersion = usePricesVersion();

  // Tickers for currency mapping
  const tickersQ = useQuery({
    queryKey: ['tickers'],
    queryFn: () => api.get('market/tickers').json<TickerResponse[]>(),
  });
  const currencyByTicker = useMemo(() => {
    const map = new Map<string, string>();
    (tickersQ.data || []).forEach(t => map.set(t.id, t.currency));
    return map;
  }, [tickersQ.data]);

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

    // Convert string inputs from backend to numbers for calculations
    const initialCashBalance = Number(fetchedPortfolio.cash_balance);
    const initialTotalAssetValue = Number(fetchedPortfolio.total_asset_value);

    const d = (v: number | string | undefined | null) => {
      try {
        if (v === undefined || v === null || v === '') return new Decimal(0);
        return new Decimal(v as Decimal.Value);
      } catch { return new Decimal(0); }
    };
    
    const updatedAssets = fetchedPortfolio.assets.map(a => {
      const p = prices.get(a.ticker_id); // This is a number
      
      const assetQuantity = Number(a.quantity);
      const assetAveragePrice = Number(a.average_price);
      const assetCurrentPrice = p !== undefined ? p : Number(a.current_price); // Use real-time price if available, else initial from API

      const totalValueD = d(assetCurrentPrice).mul(assetQuantity);
      let profitRate = 0;
      const costBasisD = d(assetAveragePrice).mul(assetQuantity);
      if (!costBasisD.isZero()) {
        profitRate = totalValueD.sub(costBasisD).div(costBasisD.abs()).mul(100).toNumber();
      }

      return { 
          ...a, 
          quantity: assetQuantity.toString(), // Convert back to string for consistency with interface
          current_price: assetCurrentPrice.toString(),
              total_value: totalValueD.toString(),
          profit_rate: profitRate.toFixed(2).toString()
      };
    });

            const newTotalValueNum = updatedAssets.reduce((acc, cur) => acc + Number(cur.total_value), 0) + initialCashBalance;

    let newChange: string | undefined = undefined; 
    
    // Calculate real-time change percent
    if (fetchedPortfolio.total_asset_change_percent && initialTotalAssetValue > 0) {
        const oldChange = Number(fetchedPortfolio.total_asset_change_percent || '0');
        const divisorD = d(1).add(d(oldChange).div(100));
        let prevTotal = 0;
        if (!divisorD.isZero()) {
          prevTotal = d(initialTotalAssetValue).div(divisorD).toNumber();
        }
        if (prevTotal !== 0) {
          const changeVal = d(newTotalValueNum).sub(prevTotal).div(Math.abs(prevTotal)).mul(100).toNumber();
          newChange = new Decimal(changeVal).toFixed(2);
        } else if (newTotalValueNum > 0) {
            // If prevTotal was 0 and newTotalValue is positive, it's an "infinite" gain
            newChange = 'Infinity'; // Indicate huge gain from 0
        } else {
            newChange = '0.00'; // Both 0, no change
        }
    } else if (newTotalValueNum > 0) {
        // If there was no previous total_asset_value or change percent, but now we have value.
        // It means it's a new portfolio or initial load, no historical change to calculate.
        newChange = '0.00'; // Or set to N/A
    } else {
        newChange = '0.00';
    }


    return {
        ...fetchedPortfolio,
        assets: updatedAssets,
        cash_balance: initialCashBalance.toString(),
        total_asset_value: newTotalValueNum.toString(),
        total_asset_change_percent: newChange
    };
  }, [fetchedPortfolio, pricesVersion]);

  const isLoading = !portfolio;

  // Asset Allocation (Long Only) Calculation
  // We filter only positive values (Long positions) for the chart to represent "Asset Allocation".
  // Short positions are liabilities and are excluded from the "What do I own?" breakdown visual.
  
  const longAssets = portfolio ? portfolio.assets.filter(a => Number(a.total_value) > 0) : [];
  
  const stockVal = longAssets.filter(a => !a.ticker_id.includes('COIN')).reduce((acc, cur) => acc + Number(cur.total_value), 0);
  const cryptoVal = longAssets.filter(a => a.ticker_id.includes('COIN')).reduce((acc, cur) => acc + Number(cur.total_value), 0);
  const cashVal = portfolio ? Number(portfolio.cash_balance) : 0;

  const totalGrossAssets = stockVal + cryptoVal + cashVal;
  const totalValNum = Math.max(totalGrossAssets, 1); // Avoid division by zero
  
  const stockPct = (stockVal / totalValNum) * 100;
  const cryptoPct = (cryptoVal / totalValNum) * 100;
  const cashPct = (cashVal / totalValNum) * 100;

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
                value={`KRW ${formatCurrencyDisplay(Number(portfolio.total_asset_value), 'KRW', 'ROUND_DOWN')}`} 
                trend={portfolio.total_asset_change_percent ? `${Number(portfolio.total_asset_change_percent) >= 0 ? '+' : ''}${toFixedString(Number(portfolio.total_asset_change_percent), 2, REPORT_ROUNDING)}% (Today)` : undefined}
                trendPositive={Number(portfolio.total_asset_change_percent || 0) >= 0}
              />
        )}
        {isLoading ? (
          <SkeletonCard />
        ) : (
          <StatCard title="Available Cash" value={`KRW ${formatCurrencyDisplay(Number(portfolio.cash_balance), 'KRW', 'ROUND_DOWN')}`} />
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
                  <p className="text-[#90a4cb] text-sm">Total Assets</p>
                  <p className="text-white text-xl font-bold">KRW {formatCurrencyDisplay(totalGrossAssets, 'KRW', 'ROUND_DOWN')}</p>
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

      {/* Holdings Table */}
      <HoldingsTable assets={portfolio?.assets || []} isLoading={isLoading} />

      {/* Open Orders */}
      <div className="flex flex-col gap-4">
        <OpenOrders />
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
                  <th className="px-6 py-4 text-[#90a4cb] text-sm font-medium text-right">Total</th>
                  <th className="px-6 py-4 text-[#90a4cb] text-sm font-medium text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#314368]">
                {orders.map((order) => {
                    let statusColor = 'text-white'; // Default
                    if (order.status === 'FILLED') {
                        statusColor = 'text-profit';
                    } else if (order.status === 'CANCELLED' || order.status === 'FAILED') {
                        statusColor = 'text-loss';
                    } else if (order.status === 'PENDING') {
                        statusColor = 'text-yellow-500';
                    }
                    return (
                        <tr key={order.id} className="hover:bg-[#182234] transition-colors">
                            <td className="px-6 py-4 text-white/70 text-sm">{new Date(order.created_at).toLocaleDateString()}</td>
                            <td className="px-6 py-4 text-white font-bold">{order.ticker_id.split('-').pop()}</td>
                            <td className="px-6 py-4 text-center">
                                <span className={`inline-flex items-center justify-center rounded-full h-7 px-3 text-xs font-bold ${order.side === 'BUY' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'}`}>
                                    {order.side}
                                </span>
                            </td>
                            <td className="px-6 py-4 text-right text-white/70">{order.price ? `${formatWithThousands(toFixedString(order.price, 0, 'ROUND_DOWN'))} ${currencyByTicker.get(order.ticker_id) ?? ''}`.trim() : '-'}</td>
                            <td className="px-6 py-4 text-right text-white/70">{toFixedString(order.quantity, getAssetQuantityDigits(order.ticker_id), 'ROUND_DOWN')}</td>
                            <td className="px-6 py-4 text-right text-white/70">
                              {order.price 
                                ? `${formatWithThousands(toFixedString(Number(order.price) * Number(order.quantity), 0, 'ROUND_DOWN'))} ${currencyByTicker.get(order.ticker_id) ?? ''}`.trim()
                                : '-'}
                            </td>
                            <td className="px-6 py-4 text-center">
                                <span className={`text-xs font-bold uppercase ${statusColor}`}>{order.status}</span>
                            </td>
                        </tr>
                    );
                })}
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