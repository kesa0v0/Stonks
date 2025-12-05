import { useState, useEffect, useMemo, useCallback } from 'react';
import Decimal from 'decimal.js';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import api from '../api/client';
import { toFixedString, REPORT_ROUNDING, formatCurrencyDisplay, getAssetQuantityDigits } from '../utils/numfmt';
import { useUsdKrwRate } from '../hooks/useFx';
import DashboardLayout from '../components/DashboardLayout';
import { SkeletonRow } from '../components/Skeleton';
import { CandleChart } from '../components/CandleChart';
import OpenOrders from '../components/OpenOrders';
import OrderInputs from '../components/orders/OrderInputs';
import ValidatedOrderForm from '../components/orders/ValidatedOrderForm';
import type { OrderBookResponse, TickerResponse, Portfolio } from '../interfaces';
import { usePrice } from '../store/prices';
import { useOrderBook } from '../store/orderBook'; // Import useOrderBook

// Isolated header stats to avoid rerendering the whole page on price updates
function RealTimeHeaderStats({ tickerId, selectedTicker }: { tickerId: string; selectedTicker?: TickerResponse }) {
  const livePrice = usePrice(tickerId);
  const basePrice = selectedTicker?.current_price ? Number(selectedTicker.current_price) : undefined;
  const baseChange = selectedTicker?.change_percent ? Number(selectedTicker.change_percent) : undefined;
  const price = typeof livePrice === 'number' ? livePrice : basePrice;

  let change = baseChange ?? 0;
  if (typeof price === 'number' && typeof basePrice === 'number' && typeof baseChange === 'number') {
    const prev = d(basePrice).div(d(1).add(d(baseChange).div(100))).toNumber();
    if (prev !== 0) change = d(price).sub(prev).div(prev).mul(100).toNumber();
  }

  return (
    <>
      <div className="text-right hidden sm:block">
        <p className="text-[#90a4cb] text-xs uppercase font-bold">24h Change</p>
        <p className={`font-mono font-bold ${change >= 0 ? 'text-profit' : 'text-loss'}`}>
          {change >= 0 ? '+' : ''}{toFixedString(change, 2, REPORT_ROUNDING)}%
        </p>
      </div>
      <div className="text-right hidden sm:block">
        <p className="text-[#90a4cb] text-xs uppercase font-bold">24h Volume</p>
        <p className="text-white font-mono font-bold">
          {selectedTicker?.volume ? Number(selectedTicker.volume).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '-'}
        </p>
      </div>
    </>
  );
}
// Helpers using Decimal for precise money/quantity calculations
const d = (v: Decimal.Value | undefined | null) => {
  try {
    if (v === undefined || v === null || v === '') return new Decimal(0);
    return new Decimal(v as Decimal.Value);
  } catch {
    return new Decimal(0);
  }
};

// mulToString/divToString are handled inside ValidatedOrderForm now

export default function Market() {
    const usdKrw = useUsdKrwRate();
  const { tickerId: routeTickerId } = useParams<{ tickerId: string }>();
  const tickerId = routeTickerId ?? 'CRYPTO-COIN-ETH';
  
  const tickersQ = useQuery({
    queryKey: ['tickers'],
    queryFn: () => api.get('market/tickers').json<TickerResponse[]>(),
  });
  const selectedTicker = useMemo(() => (tickersQ.data || []).find(t => t.id === tickerId), [tickersQ.data, tickerId]);
  const symbol = selectedTicker?.symbol ?? (tickerId.split('-').pop() || tickerId);
  const currency = selectedTicker?.currency ?? 'KRW';

  // Get order book from global store
  const orderBook = useOrderBook(tickerId);
  
  // Form States
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT' | 'STOP_LOSS' | 'TAKE_PROFIT' | 'STOP_LIMIT' | 'TRAILING_STOP'>('MARKET');
  const [price, setPrice] = useState<number | ''>(''); // Unit Price / Target Price
  const [stopPrice, setStopPrice] = useState<number | ''>(''); // Trigger Price
  const [trailingGap, setTrailingGap] = useState<number | ''>(''); // Trailing Gap
  // amount/total are handled by ValidatedOrderForm
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  // lastEdited no longer needed after moving amount/total handling
  const [timeRange, setTimeRange] = useState<'1D' | '1W' | '3M' | '1Y' | '5Y'>('1D');
  const [chartType, setChartType] = useState<'candle' | 'area'>('candle');

  // Fetch trading fee config (fallback to 0.1%)
  const feeQ = useQuery({
    queryKey: ['trading-fees'],
    queryFn: async () => {
      try {
        const r = await api.get('config/trading').json<{ maker_fee?: string | number; taker_fee?: string | number }>();
        return r;
      } catch {
        return { maker_fee: 0.001, taker_fee: 0.001 };
      }
    }
  });
  const makerFee = Number(feeQ.data?.maker_fee ?? 0.001);
  const takerFee = Number(feeQ.data?.taker_fee ?? 0.001);
  const effectiveFeeRate = (orderType === 'LIMIT' || orderType === 'STOP_LIMIT') ? makerFee : takerFee;

  // fee-adjusted total is handled in ValidatedOrderForm

  const portfolioQ = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => api.get('me/portfolio').json<Portfolio>(),
    refetchInterval: 5000, // Refresh every 5 seconds
  });

  // Real-time Price Logic
  const livePrice = usePrice(tickerId); // kept for order form auto-calc below
  const realTimePrice = (typeof livePrice === 'number') ? livePrice : (selectedTicker?.current_price ? Number(selectedTicker.current_price) : undefined);

  const currentHolding = useMemo(() => {
    return portfolioQ.data?.assets.find(a => a.ticker_id === tickerId);
  }, [portfolioQ.data, tickerId]);

  const holdingPnL = useMemo(() => {
      if (!currentHolding || !realTimePrice) return null;
        const avg = Number(currentHolding.average_price);
        const qty = Number(currentHolding.quantity);
        if (avg === 0 || qty === 0) return 0;
        const totalVal = d(realTimePrice).mul(qty);
        const costBasis = d(avg).mul(qty);
        return totalVal.sub(costBasis).div(costBasis.abs()).mul(100).toNumber();
  }, [currentHolding, realTimePrice]);

  useEffect(() => {
    try {
      window.localStorage.setItem('lastMarketTickerId', tickerId);
    } catch { /* ignore persistence errors */ }
  }, [tickerId]);

  // Market Mode: Sync Price & Auto-calculate
  // For MARKET-like orders, we display realTimePrice separately; no need to sync price state

  // Initialize Price for Limit Mode
  // For LIMIT-like orders, keep price user-controlled; optionally show placeholder with realTimePrice


  // Input Handlers
  const handlePriceChange = (val: string) => {
    const newPrice = parseFloat(val);
    setPrice(isNaN(newPrice) ? '' : newPrice);
    // Total is derived inside ValidatedOrderForm; nothing else to do here
  };

  // amount/total handling moved to ValidatedOrderForm

  // amount/total handling moved to ValidatedOrderForm

  // 주문 제출은 ValidatedOrderForm 내부에서 처리

  // Tabs Configuration
  const tabs = [
      { id: 'MARKET', label: 'Market' },
      { id: 'LIMIT', label: 'Limit' },
      { id: 'STOP_LOSS', label: 'Stop Loss' },
      { id: 'TAKE_PROFIT', label: 'Take Profit' },
      { id: 'STOP_LIMIT', label: 'Stop Limit' },
      { id: 'TRAILING_STOP', label: 'Trailing' },
  ];

  return (
    <DashboardLayout>
      <div className="flex flex-col min-h-screen">
        {/* Header Bar */}
        <header className="flex-none flex items-center justify-between border-b border-[#314368] pb-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-[#222f49] flex items-center justify-center text-[#0d59f2]">
              <span className="material-symbols-outlined text-2xl">currency_bitcoin</span>
            </div>
            <div>
              <h1 className="text-white text-xl font-bold leading-tight">
                {(symbol.endsWith(`/${currency}`) || symbol.endsWith(`-${currency}`)) ? symbol : `${symbol} / ${currency}`}
              </h1>
              <p className="text-[#90a4cb] text-sm">{selectedTicker?.name ?? tickerId}</p>
            </div>
          </div>
          <div className="flex gap-4">
            <RealTimeHeaderStats tickerId={tickerId} selectedTicker={selectedTicker} />
          </div>
        </header>

        {/* Main Grid: fixed viewport height; prioritize larger panels */}
        <div className="flex-1 grid grid-cols-12 gap-6 min-h-0">
          
          {/* Left Column: Chart */}
          <div className="col-span-12 lg:col-span-8 flex flex-col h-full">
            <div className="flex-1 rounded-xl border border-[#314368] bg-[#101623] p-4 flex flex-col min-h-0">
              <div className="flex justify-between items-center mb-4 flex-none">
                <h3 className="text-white font-bold">Price Chart</h3>
                <div className="flex gap-4">
                  {/* Range Toggle */}
                  <div className="flex gap-2 bg-[#182234] p-1 rounded-lg">
                    {(['1D', '1W', '3M', '1Y', '5Y'] as const).map((r) => (
                      <button 
                        key={r}
                        onClick={() => setTimeRange(r)}
                        className={`px-3 py-1 rounded text-xs font-bold transition-colors ${timeRange === r ? 'bg-[#222f49] text-white shadow' : 'text-[#90a4cb] hover:text-white'}`}
                      >
                        {r}
                      </button>
                    ))}
                  </div>

                  {/* Type Toggle */}
                  <div className="flex gap-2 bg-[#182234] p-1 rounded-lg">
                    <button 
                      onClick={() => setChartType('candle')}
                      className={`p-1 rounded transition-colors ${chartType === 'candle' ? 'bg-[#222f49] text-white shadow' : 'text-[#90a4cb] hover:text-white'}`}
                      title="Candlestick"
                    >
                      <span className="material-symbols-outlined text-sm">candlestick_chart</span>
                    </button>
                    <button 
                      onClick={() => setChartType('area')}
                      className={`p-1 rounded transition-colors ${chartType === 'area' ? 'bg-[#222f49] text-white shadow' : 'text-[#90a4cb] hover:text-white'}`}
                      title="Area Line"
                    >
                       <span className="material-symbols-outlined text-sm">show_chart</span>
                    </button>
                  </div>
                </div>
              </div>
              {/* Chart Area */}
              <div className="flex-1 w-full bg-[#101623] rounded-lg overflow-hidden border border-[#314368]/30 relative">
                 <CandleChart 
                   tickerId={tickerId} 
                   range={timeRange} 
                   chartType={chartType}
                   currencyCode={currency}
                 />
              </div>
            </div>
          </div>

          {/* Right Column: OrderBook & Trade Form */}
          <div className="col-span-12 lg:col-span-4 flex flex-col gap-6 h-full">
            
            {/* Order Book */}
            <div className="flex-1 rounded-xl border border-[#314368] bg-[#101623] p-4 flex flex-col min-h-0 overflow-hidden">
              <h3 className="text-white font-bold mb-3 border-b border-[#314368] pb-2 flex-none">Order Book</h3>
              <div className="flex-1 overflow-y-auto font-mono text-sm no-scrollbar">
                <table className="w-full">
                  <thead>
                    <tr className="text-[#90a4cb] text-xs">
                      <th className="text-left font-normal pb-2">Price</th>
                      <th className="text-right font-normal pb-2">Amount</th>
                      <th className="text-right font-normal pb-2">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {!orderBook ? (
                        Array.from({ length: 16 }).map((_, i) => <SkeletonRow key={i} cols={3} />)
                    ) : (
                        <>
                        {/* Asks (Sell Orders) - Blue (Loss) */}
                        {orderBook?.asks.slice(0, 8).reverse().map((ask, i) => (
                        <tr key={`ask-${i}`} className="hover:bg-[#182234] transition-colors relative">
                            <td className="text-loss py-1">{formatCurrencyDisplay(ask.price, currency, 'ROUND_DOWN')}</td>
                            <td className="text-right text-white/70">{toFixedString(ask.quantity, 4, 'ROUND_DOWN')}</td>
                            <td className="text-right text-white/40">{formatCurrencyDisplay(Number(ask.price) * Number(ask.quantity), currency, 'ROUND_DOWN')}</td>
                        </tr>
                        ))}
                        
                        {/* Current Price Divider */}
                        <tr className="border-y border-[#314368] bg-[#222f49]/50">
                        <td colSpan={3} className="py-2 text-center text-lg font-bold text-white">
                            {realTimePrice ? formatCurrencyDisplay(realTimePrice, currency, 'ROUND_DOWN') : '-'} <span className="text-xs text-[#90a4cb] font-normal">{currency}</span>
                        </td>
                        </tr>

                        {/* Bids (Buy Orders) - Red (Profit) */}
                        {orderBook?.bids.slice(0, 8).map((bid, i) => (
                        <tr key={`bid-${i}`} className="hover:bg-[#2a1818] transition-colors relative">
                            <td className="text-profit py-1">{formatCurrencyDisplay(bid.price, currency, 'ROUND_DOWN')}</td>
                            <td className="text-right text-white/70">{toFixedString(bid.quantity, 4, 'ROUND_DOWN')}</td>
                            <td className="text-right text-white/40">{formatCurrencyDisplay(Number(bid.price) * Number(bid.quantity), currency, 'ROUND_DOWN')}</td>
                        </tr>
                        ))}
                        </>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Trade Form */}
            <div className="flex-none h-auto rounded-xl border border-[#314368] bg-[#101623] p-4 flex flex-col">
              {/* Side Toggle */}
              <div className="flex bg-[#182234] rounded-lg p-1 mb-4">
                <button 
                  onClick={() => setSide('BUY')}
                  className={`flex-1 py-2 rounded-md text-sm font-bold transition-all ${side === 'BUY' ? 'bg-profit text-white shadow-lg' : 'text-[#90a4cb] hover:text-white'}`}
                >
                  Buy
                </button>
                <button 
                  onClick={() => setSide('SELL')}
                  className={`flex-1 py-2 rounded-md text-sm font-bold transition-all ${side === 'SELL' ? 'bg-loss text-white shadow-lg' : 'text-[#90a4cb] hover:text-white'}`}
                >
                  Sell
                </button>
              </div>

              {/* Order Type Grid */}
              <div className="grid grid-cols-3 gap-2 mb-4">
                {tabs.map((tab) => (
                    <button 
                        key={tab.id}
                        onClick={() => setOrderType(tab.id as 'MARKET' | 'LIMIT' | 'STOP_LOSS' | 'TAKE_PROFIT' | 'STOP_LIMIT' | 'TRAILING_STOP')}
                        className={`py-2 rounded-md text-xs font-bold transition-all 
                          ${orderType === tab.id 
                            ? 'bg-[#222f49] text-[#0d59f2] border border-[#0d59f2]' 
                            : 'bg-[#182234] text-[#90a4cb] hover:bg-[#222f49] hover:text-white border border-transparent'
                          }`}
                    >
                        {tab.label}
                    </button>
                ))}
              </div>

              <div className="flex flex-col gap-3">
                
                {/* Order-specific Inputs */}
                <OrderInputs
                  orderType={orderType}
                  currency={currency}
                  price={price}
                  stopPrice={stopPrice}
                  trailingGap={trailingGap}
                  onPriceChange={handlePriceChange}
                  onStopPriceChange={(v: string) => setStopPrice(v === '' ? '' : parseFloat(v))}
                  onTrailingGapChange={(v: string) => setTrailingGap(v === '' ? '' : parseFloat(v))}
                />

                {/* Market Price Display (for Market-like orders) */}
                {(orderType === 'MARKET' || orderType === 'STOP_LOSS' || orderType === 'TAKE_PROFIT' || orderType === 'TRAILING_STOP') && (
                  <div>
                    <label className="text-xs font-bold text-[#90a4cb] uppercase flex justify-between">
                      <span>Unit Price</span>
                      <span className="text-[#0d59f2] text-[10px]">Market Price</span>
                    </label>
                    <div className="w-full mt-1 bg-[#182234]/50 border border-[#314368] rounded-lg px-3 py-2 text-white/80 font-mono cursor-default flex justify-between">
                      <span>{realTimePrice ? formatCurrencyDisplay(realTimePrice, currency, 'ROUND_DOWN') : '-' } {currency}</span>
                      {currency === 'USD' && realTimePrice ? (
                        <span className="text-white/60 text-xs">≈ {formatCurrencyDisplay(realTimePrice * usdKrw, 'KRW', 'ROUND_DOWN')} KRW</span>
                      ) : null}
                    </div>
                  </div>
                )}

                {/* Validated amount/total form */}
                {currentHolding && (
                  <div className="flex justify-between text-xs mb-1">
                      <span className="text-[#90a4cb]">
                          Holding: <span className="font-mono text-white">{Number(currentHolding.quantity).toLocaleString(undefined, { maximumFractionDigits: 4 })}</span>
                      </span>
                        {holdingPnL !== null && (
                          <span className={`font-mono font-bold ${holdingPnL >= 0 ? 'text-profit' : 'text-loss'}`}>
                            {holdingPnL >= 0 ? '+' : ''}{toFixedString(holdingPnL, 2, REPORT_ROUNDING)}%
                          </span>
                        )}
                  </div>
                )}

                <ValidatedOrderForm
                  currency={currency}
                  side={side}
                  effectivePrice={(orderType === 'MARKET' || orderType === 'STOP_LOSS' || orderType === 'TAKE_PROFIT' || orderType === 'TRAILING_STOP') ? realTimePrice : (typeof price === 'number' ? price : undefined)}
                  effectiveFeeRate={effectiveFeeRate}
                  amountUnitLabel={symbol}
                  submitLabel={`${orderType.replace('_', ' ')} ${side}`}
                  onSubmit={async (quantity) => {
                    const payload: Record<string, unknown> = {
                      ticker_id: tickerId,
                      side,
                      type: orderType,
                      quantity,
                    };
                    if (orderType === 'LIMIT' || orderType === 'STOP_LIMIT') {
                      payload.target_price = typeof price === 'number' ? price : 0;
                    }
                    if (orderType === 'STOP_LOSS' || orderType === 'TAKE_PROFIT' || orderType === 'STOP_LIMIT') {
                      payload.stop_price = typeof stopPrice === 'number' ? stopPrice : 0;
                    }
                    if (orderType === 'TRAILING_STOP') {
                      payload.trailing_gap = typeof trailingGap === 'number' ? trailingGap : 0;
                    }
                    try {
                      await api.post('orders', { json: payload });
                      // Build informative success toast with amounts
                      const qtyStr = toFixedString(quantity,  getAssetQuantityDigits(symbol), 'ROUND_DOWN');
                      const unit = (orderType === 'LIMIT' || orderType === 'STOP_LIMIT') 
                        ? (typeof price === 'number' ? price : undefined) 
                        : realTimePrice;
                      if (unit) {
                        const notional = new Decimal(unit).mul(quantity);
                        const fee = notional.mul(effectiveFeeRate);
                        const total = notional.add(fee);
                        const unitStr = formatCurrencyDisplay(unit, currency, 'ROUND_DOWN');
                        if (currency === 'USD') {
                          const krwTotal = total.mul(usdKrw);
                          const totalStrKRW = formatCurrencyDisplay(krwTotal.toNumber(), 'KRW', 'ROUND_DOWN');
                          toast.success(`${side} ${qtyStr} ${symbol} @ ${unitStr} • 예상 결제 ${totalStrKRW} KRW`);
                        } else {
                          const totalStr = formatCurrencyDisplay(total.toNumber(), currency, 'ROUND_DOWN');
                          toast.success(`${side} ${qtyStr} ${symbol} @ ${unitStr} • Est. total ${totalStr} ${currency}`);
                        }
                      } else {
                        toast.success(`${side} ${qtyStr} ${symbol} • Order placed`);
                      }
                      try { window.dispatchEvent(new Event('orders:updated')); } catch { /* ignore */ }
                    } catch (err) {
                      console.error('Order execution failed', err);
                      toast.error('Order Failed');
                    }
                  }}
                />
              </div>
            </div>

          </div>
        </div>

        {/* Open Orders Section: fixed card height with internal scroll */}
        <div className="flex-none mt-6 pb-6">
           <OpenOrders tickerId={tickerId} />
        </div>
      </div>
    </DashboardLayout>
  );
}
