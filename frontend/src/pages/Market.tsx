import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import api from '../api/client';
import DashboardLayout from '../components/DashboardLayout';
import { CandleChart } from '../components/CandleChart';
import OpenOrders from '../components/OpenOrders';
import type { OrderBookResponse, TickerResponse } from '../interfaces';
import { useWebSocket } from '../hooks/useWebSocket';

const toNumber = (v: string) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
};

export default function Market() {
  const { tickerId: routeTickerId } = useParams<{ tickerId: string }>();
  const tickerId = routeTickerId ?? 'CRYPTO-COIN-ETH';
  
  const tickersQ = useQuery({
    queryKey: ['tickers'],
    queryFn: () => api.get('market/tickers').json<TickerResponse[]>(),
  });
  const selectedTicker = useMemo(() => (tickersQ.data || []).find(t => t.id === tickerId), [tickersQ.data, tickerId]);
  const symbol = selectedTicker?.symbol ?? (tickerId.split('-').pop() || tickerId);
  const currency = selectedTicker?.currency ?? 'KRW';

  const [orderBook, setOrderBook] = useState<OrderBookResponse | null>(null);
  const [wsPrice, setWsPrice] = useState<number | undefined>(undefined);
  const [wsTimestamp, setWsTimestamp] = useState<number | undefined>(undefined);
  
  // Form States
  const [orderType, setOrderType] = useState<'LIMIT' | 'MARKET'>('MARKET');
  const [price, setPrice] = useState<number | ''>(''); // Unit Price
  const [amount, setAmount] = useState<string>(''); // Quantity
  const [total, setTotal] = useState<string>(''); // Total Price
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [lastEdited, setLastEdited] = useState<'AMOUNT' | 'TOTAL'>('AMOUNT'); // Track last edited field for sync
  const [timeRange, setTimeRange] = useState<'1D' | '1W' | '3M' | '1Y' | '5Y'>('1D');
  const [chartType, setChartType] = useState<'candle' | 'area'>('candle');

  // WebSocket Event Handler
  const onMessage = useCallback((msg: any) => {
    if (!msg || msg.ticker_id !== tickerId) return;

    if (msg.type === 'ticker' || (!msg.type && msg.price)) {
      setWsPrice(msg.price);
      if (msg.timestamp) {
        setWsTimestamp(msg.timestamp);
      }
    } else if (msg.type === 'orderbook') {
      setOrderBook(msg);
    }
  }, [tickerId]);

  useWebSocket(onMessage);

  // Real-time Price Logic
  const realTimePrice = wsPrice !== undefined ? wsPrice : (selectedTicker?.current_price ? Number(selectedTicker.current_price) : undefined);

  let realTimeChange = selectedTicker?.change_percent ? Number(selectedTicker.change_percent) : 0;
  if (wsPrice !== undefined && selectedTicker?.current_price && selectedTicker.change_percent) {
    const initPrice = Number(selectedTicker.current_price);
    const initChange = Number(selectedTicker.change_percent);
    const prev = initPrice / (1 + initChange / 100);
    if (prev !== 0) {
      realTimeChange = ((wsPrice - prev) / prev) * 100;
    }
  }

  useEffect(() => {
    try {
      window.localStorage.setItem('lastMarketTickerId', tickerId);
    } catch { /* ignore persistence errors */ }
  }, [tickerId]);

  // 초기 데이터 로드 (호가창)
  useEffect(() => {
    const fetchOrderBook = async () => {
      try {
        const data = await api.get(`market/orderbook/${tickerId}`).json<OrderBookResponse>();
        setOrderBook(data);
      } catch (err) {
        console.error("Failed to fetch orderbook", err);
      }
    };
    fetchOrderBook();
  }, [tickerId]);

  // Market Mode: Sync Price & Auto-calculate
  useEffect(() => {
    if (orderType === 'MARKET' && realTimePrice) {
      setPrice(realTimePrice);
      
      if (lastEdited === 'AMOUNT') {
          // Amount is anchor -> Update Total
          if (amount) {
            const val = parseFloat(amount);
            if (!isNaN(val)) {
                setTotal((val * realTimePrice).toFixed(0));
            }
          }
      } else {
          // Total is anchor -> Update Amount
          if (total) {
            const val = parseFloat(total);
            if (!isNaN(val) && realTimePrice !== 0) {
                setAmount((val / realTimePrice).toFixed(8));
            }
          }
      }
    }
  }, [orderType, realTimePrice, lastEdited, amount, total]);

  // Initialize Price for Limit Mode
  useEffect(() => {
      if (orderType === 'LIMIT' && realTimePrice && price === '') {
          setPrice(realTimePrice);
      }
  }, [orderType, realTimePrice, price]);


  // Input Handlers
  const handlePriceChange = (val: string) => {
    const newPrice = parseFloat(val);
    setPrice(isNaN(newPrice) ? '' : newPrice);
    
    // Limit mode: update total if amount exists
    if (!isNaN(newPrice) && amount) {
        const amt = parseFloat(amount);
        if (!isNaN(amt)) {
            setTotal((newPrice * amt).toFixed(0));
        }
    }
  };

  const handleAmountChange = (val: string) => {
    setAmount(val);
    setLastEdited('AMOUNT');
    const amt = parseFloat(val);
    const p = typeof price === 'number' ? price : parseFloat(price);
    
    if (!isNaN(amt) && !isNaN(p)) {
        setTotal((p * amt).toFixed(0));
    } else if (val === '') {
        setTotal('');
    }
  };

  const handleTotalChange = (val: string) => {
    setTotal(val);
    setLastEdited('TOTAL');
    const tot = parseFloat(val);
    const p = typeof price === 'number' ? price : parseFloat(price);
    
    if (!isNaN(tot) && !isNaN(p) && p !== 0) {
        // Calculate amount
        const newAmount = tot / p;
        setAmount(newAmount.toFixed(8)); 
    } else if (val === '') {
        setAmount('');
    }
  };

  // 주문 제출 핸들러
  const handleOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post('orders', {
        json: {
          ticker_id: tickerId,
          side: side,
          type: orderType, 
          quantity: toNumber(amount),
          target_price: typeof price === 'number' ? price : toNumber(price)
        }
      });
      toast.success("Order Placed Successfully!");
      setAmount('');
      setTotal('');
    } catch (err) {
      console.error("Order execution failed", err);
    }
  };

  return (
    <DashboardLayout>
      <>
        {/* Header Bar */}
        <header className="flex items-center justify-between border-b border-[#314368] pb-4 mb-6">
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
            <div className="text-right hidden sm:block">
              <p className="text-[#90a4cb] text-xs uppercase font-bold">24h Change</p>
              <p className={`font-mono font-bold ${(realTimeChange >= 0) ? 'text-profit' : 'text-loss'}`}>
                {realTimeChange >= 0 ? '+' : ''}{realTimeChange.toFixed(2)}%
              </p>
            </div>
            <div className="text-right hidden sm:block">
              <p className="text-[#90a4cb] text-xs uppercase font-bold">24h Volume</p>
              <p className="text-white font-mono font-bold">
                {selectedTicker?.volume ? Number(selectedTicker.volume).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '-'}
              </p>
            </div>
          </div>
        </header>

        {/* Main Grid */}
        <div className="grid grid-cols-12 gap-6 h-[calc(100vh-180px)] min-h-[600px]">
          
          {/* Left Column: Chart */}
          <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
            <div className="flex-1 rounded-xl border border-[#314368] bg-[#101623] p-4 flex flex-col">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-white font-bold">Price Chart</h3>
                <div className="flex gap-4">
                  {/* Range Toggle */}
                  <div className="flex gap-2 bg-[#182234] p-1 rounded-lg">
                    {['1D', '1W', '3M', '1Y', '5Y'].map((r) => (
                      <button 
                        key={r}
                        onClick={() => setTimeRange(r as any)}
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
                   lastPrice={realTimePrice}
                   lastPriceTimestamp={wsTimestamp}
                 />
              </div>
            </div>
          </div>

          {/* Right Column: OrderBook & Trade Form */}
          <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
            
            {/* Order Book */}
            <div className="flex-[2] rounded-xl border border-[#314368] bg-[#101623] p-4 flex flex-col overflow-hidden">
              <h3 className="text-white font-bold mb-3 border-b border-[#314368] pb-2">Order Book</h3>
              <div className="flex-1 overflow-y-auto font-mono text-sm custom-scrollbar">
                <table className="w-full">
                  <thead>
                    <tr className="text-[#90a4cb] text-xs">
                      <th className="text-left font-normal pb-2">Price</th>
                      <th className="text-right font-normal pb-2">Amount</th>
                      <th className="text-right font-normal pb-2">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* Asks (Sell Orders) - Blue (Loss) */}
                    {orderBook?.asks.slice(0, 8).reverse().map((ask, i) => (
                      <tr key={`ask-${i}`} className="hover:bg-[#182234] transition-colors relative">
                        <td className="text-loss py-1">{ask.price.toLocaleString()}</td>
                        <td className="text-right text-white/70">{Number(ask.quantity).toFixed(4)}</td>
                        <td className="text-right text-white/40">{(ask.price * Number(ask.quantity)).toLocaleString()}</td>
                      </tr>
                    ))}
                    
                    {/* Current Price Divider */}
                    <tr className="border-y border-[#314368] bg-[#222f49]/50">
                      <td colSpan={3} className="py-2 text-center text-lg font-bold text-white">
                        {realTimePrice ? realTimePrice.toLocaleString() : '-'} <span className="text-xs text-[#90a4cb] font-normal">KRW</span>
                      </td>
                    </tr>

                    {/* Bids (Buy Orders) - Red (Profit) */}
                    {orderBook?.bids.slice(0, 8).map((bid, i) => (
                      <tr key={`bid-${i}`} className="hover:bg-[#2a1818] transition-colors relative">
                        <td className="text-profit py-1">{bid.price.toLocaleString()}</td>
                        <td className="text-right text-white/70">{Number(bid.quantity).toFixed(4)}</td>
                        <td className="text-right text-white/40">{(bid.price * Number(bid.quantity)).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Trade Form */}
            <div className="flex-[3] rounded-xl border border-[#314368] bg-[#101623] p-4 flex flex-col justify-center">
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

              {/* Order Type Tabs */}
              <div className="flex gap-4 mb-4 border-b border-[#314368] px-1">
                <button 
                    onClick={() => setOrderType('LIMIT')}
                    className={`pb-2 text-sm font-bold transition-colors ${orderType === 'LIMIT' ? 'text-white border-b-2 border-[#0d59f2]' : 'text-[#90a4cb] hover:text-white'}`}
                >
                    Limit
                </button>
                <button 
                    onClick={() => setOrderType('MARKET')}
                    className={`pb-2 text-sm font-bold transition-colors ${orderType === 'MARKET' ? 'text-white border-b-2 border-[#0d59f2]' : 'text-[#90a4cb] hover:text-white'}`}
                >
                    Market
                </button>
              </div>

              <form onSubmit={handleOrder} className="flex flex-col gap-3">
                {/* Price Input */}
                <div>
                  <label className="text-xs font-bold text-[#90a4cb] uppercase flex justify-between">
                      <span>Price ({currency})</span>
                      {orderType === 'MARKET' && <span className="text-[#0d59f2] text-[10px]">Market Price</span>}
                  </label>
                  <input 
                    type="number" 
                    className={`w-full mt-1 bg-[#182234] border border-[#314368] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all ${orderType === 'MARKET' ? 'market-price-readonly' : ''}`}
                    value={price}
                    onChange={(e) => handlePriceChange(e.target.value)}
                    readOnly={orderType === 'MARKET'}
                    placeholder="Price"
                  />
                </div>

                {/* Amount Input */}
                <div>
                  <label className="text-xs font-bold text-[#90a4cb] uppercase">Amount ({symbol})</label>
                  <input 
                    type="number" 
                    step="0.0001"
                    className="w-full mt-1 bg-[#182234] border border-[#314368] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all"
                    placeholder="0.00"
                    value={amount}
                    onChange={(e) => handleAmountChange(e.target.value)}
                  />
                </div>

                {/* Total Input */}
                <div>
                  <label className="text-xs font-bold text-[#90a4cb] uppercase">Total ({currency})</label>
                  <input 
                    type="number" 
                    className="w-full mt-1 bg-[#182234] border border-[#314368] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all"
                    placeholder="0"
                    value={total}
                    onChange={(e) => handleTotalChange(e.target.value)}
                  />
                </div>
                
                <button 
                  type="submit" 
                  className={`w-full py-3 rounded-lg font-bold text-white mt-2 transition-all hover:brightness-110 active:scale-95
                    ${side === 'BUY' ? 'bg-profit' : 'bg-loss'}`}
                >
                  {orderType === 'MARKET' ? 'Market ' : ''}{side}
                </button>
              </form>
            </div>

          </div>
        </div>

        {/* Open Orders Section */}
        <div className="mt-6">
           <OpenOrders tickerId={tickerId} />
        </div>
      </>
    </DashboardLayout>
  );
}
