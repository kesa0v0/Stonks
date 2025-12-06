import { memo, useEffect } from 'react';
import { useOrderBook, orderBookStore } from '../store/orderBook';
import { SkeletonRow } from './Skeleton';
import { formatCurrencyDisplay, toFixedString } from '../utils/numfmt';
import api from '../api/client';
import Decimal from 'decimal.js';
import type { OrderBookResponse } from '../interfaces';

interface OrderBookWidgetProps {
  tickerId: string;
  currency: string;
  realTimePrice?: number;
}

const OrderBookWidget = memo(function OrderBookWidget({ tickerId, currency, realTimePrice }: OrderBookWidgetProps) {
  const orderBook = useOrderBook(tickerId);

  // Initial Fetch Strategy:
  // Fetch immediately on mount/change to ensure data is present without waiting for WebSocket.
  useEffect(() => {
    const fetchOrderBook = async () => {
      try {
        const data = await api.get(`market/orderbook/${tickerId}`).json<OrderBookResponse>();
        orderBookStore.updateOrderBook(tickerId, data);
      } catch (err) {
        // Silent fail, WS will pick it up or retry
        console.error("Failed to fetch initial orderbook", err);
      }
    };
    fetchOrderBook();
  }, [tickerId]);

  return (
    <div className="flex-1 rounded-xl border border-[#314368] bg-[#101623] p-4 flex flex-col min-h-0 max-h-[540px] overflow-hidden">
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
                {/* Asks (Sell Orders) - Blue (Loss color convention in KR usually, but here using text-loss/profit) */}
                {orderBook?.asks.slice(0, 8).reverse().map((ask, i) => (
                <tr key={`ask-${i}`} className="hover:bg-[#182234] transition-colors relative">
                    <td className="text-loss py-1">{formatCurrencyDisplay(ask.price, currency, 'ROUND_DOWN')}</td>
                    <td className="text-right text-white/70">{toFixedString(ask.quantity, 4, 'ROUND_DOWN')}</td>
                    <td className="text-right text-white/40">{formatCurrencyDisplay(new Decimal(ask.price).mul(new Decimal(ask.quantity)), currency, 'ROUND_DOWN')}</td>
                </tr>
                ))}
                
                {/* Current Price Divider */}
                <tr className="border-y border-[#314368] bg-[#222f49]/50">
                <td colSpan={3} className="py-2 text-center text-lg font-bold text-white">
                    {realTimePrice ? formatCurrencyDisplay(realTimePrice, currency, 'ROUND_DOWN') : '-'} <span className="text-xs text-[#90a4cb] font-normal">{currency}</span>
                </td>
                </tr>

                {/* Bids (Buy Orders) - Red (Profit color convention) */}
                {orderBook?.bids.slice(0, 8).map((bid, i) => (
                <tr key={`bid-${i}`} className="hover:bg-[#2a1818] transition-colors relative">
                    <td className="text-profit py-1">{formatCurrencyDisplay(bid.price, currency, 'ROUND_DOWN')}</td>
                    <td className="text-right text-white/70">{toFixedString(bid.quantity, 4, 'ROUND_DOWN')}</td>
                    <td className="text-right text-white/40">{formatCurrencyDisplay(new Decimal(bid.price).mul(new Decimal(bid.quantity)), currency, 'ROUND_DOWN')}</td>
                </tr>
                ))}
                </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
});

export default OrderBookWidget;
