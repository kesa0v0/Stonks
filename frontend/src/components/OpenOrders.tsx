import { useState, useEffect } from 'react';
import Decimal from 'decimal.js';
import api from '../api/client';
import type { OrderListItem } from '../interfaces';
import toast from 'react-hot-toast';

interface OpenOrdersProps {
  tickerId?: string; // If provided, filters by this ticker
}

export default function OpenOrders({ tickerId }: OpenOrdersProps) {
  const [orders, setOrders] = useState<OrderListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchOrders = async () => {
    // Don't set loading(true) here to avoid UI flicker on background refresh
    try {
      const data = await api.get('me/orders/open').json<OrderListItem[]>();
      // Filter by tickerId if provided
      const filtered = tickerId ? data.filter(o => o.ticker_id === tickerId) : data;
      // Sort by created_at desc
      filtered.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setOrders(filtered);
    } catch (err) {
      console.error("Failed to fetch open orders", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
    // Polling for background refresh
    const interval = setInterval(fetchOrders, 5000);
    // Immediate refresh on order placement events
    const onUpdated = () => { fetchOrders(); };
    window.addEventListener('orders:updated', onUpdated as EventListener);
    return () => {
      clearInterval(interval);
      window.removeEventListener('orders:updated', onUpdated as EventListener);
    };
  }, [tickerId]);

  const handleCancel = async (orderId: string) => {
    if (!confirm('Are you sure you want to cancel this order?')) return;
    try {
      await api.post(`orders/${orderId}/cancel`);
      toast.success('Order cancelled successfully');
      fetchOrders(); // Refresh list
    } catch (err) {
      // Error handled by global error handler (toast)
      console.error(err);
    }
  };

  if (loading && orders.length === 0) {
      return <div className="text-[#90a4cb] text-sm animate-pulse p-4">Loading open orders...</div>;
  }

  if (orders.length === 0) {
      return (
        <div className="text-[#90a4cb] text-sm text-center p-8 border border-[#314368] rounded-xl bg-[#101623] border-dashed">
            No open orders {tickerId ? 'for this ticker' : ''}.
        </div>
      );
  }

  return (
    <div className="w-full overflow-hidden rounded-xl border border-[#314368] bg-[#101623]">
      <div className="p-4 border-b border-[#314368] flex justify-between items-center">
        <h3 className="text-white font-bold">Open Orders {tickerId ? `(${tickerId.split('-').pop()})` : ''}</h3>
        <button 
            onClick={fetchOrders} 
            className="text-[#0d59f2] text-xs font-bold hover:underline flex items-center gap-1"
        >
            <span className="material-symbols-outlined text-sm">refresh</span> Refresh
        </button>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
            <thead className="bg-[#182234] text-[#90a4cb] font-medium">
                <tr>
                    <th className="px-4 py-3">Time</th>
                    {!tickerId && <th className="px-4 py-3">Ticker</th>}
                    <th className="px-4 py-3 text-center">Side</th>
                    <th className="px-4 py-3 text-center">Type</th>
                    <th className="px-4 py-3 text-right">Condition</th>
                    <th className="px-4 py-3 text-right">Amount</th>
                    <th className="px-4 py-3 text-center">Status</th>
                    <th className="px-4 py-3 text-center">Action</th>
                </tr>
            </thead>
            <tbody className="divide-y divide-[#314368]">
                {orders.map(order => {
                    let conditionText = '-';
                    const targetPrice = order.target_price ? new Decimal(order.target_price).toFixed(0) : null;
                    const stopPrice = order.stop_price ? new Decimal(order.stop_price).toFixed(0) : null;
                    const gap = order.trailing_gap ? new Decimal(order.trailing_gap).toFixed(0) : null;

                    switch(order.type) {
                        case 'LIMIT':
                            conditionText = `${targetPrice} (Target)`;
                            break;
                        case 'STOP_LOSS':
                        case 'TAKE_PROFIT':
                            conditionText = `${stopPrice} (Trigger)`;
                            break;
                        case 'STOP_LIMIT':
                            conditionText = `Trig: ${stopPrice} → Lim: ${targetPrice}`;
                            break;
                        case 'TRAILING_STOP':
                            conditionText = `Trig: ${stopPrice} (Gap: ${gap})`;
                            break;
                        case 'MARKET':
                            conditionText = 'Market Price';
                            break;
                        default:
                            conditionText = targetPrice || stopPrice || '-';
                    }

                    return (
                    <tr key={order.id} className="hover:bg-[#182234] transition-colors">
                        <td className="px-4 py-3 text-white/70 whitespace-nowrap">
                            {new Date(order.created_at).toLocaleString()}
                        </td>
                        {!tickerId && (
                            <td className="px-4 py-3 text-white font-bold">
                                {order.ticker_id.split('-').pop()}
                            </td>
                        )}
                        <td className="px-4 py-3 text-center">
                            <span className={`inline-flex items-center justify-center px-2 py-1 rounded text-xs font-bold ${order.side === 'BUY' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'}`}>
                                {order.side}
                            </span>
                        </td>
                        <td className="px-4 py-3 text-center text-xs font-bold text-white/80">
                            {order.type.replace('_', ' ')}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-white text-xs">
                            {conditionText}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-white">
                             {new Decimal(order.quantity).toFixed(8)}
                        </td>
                        <td className="px-4 py-3 text-center">
                            <span className="text-xs font-bold text-yellow-500 uppercase">{order.status}</span>
                        </td>
                        <td className="px-4 py-3 text-center">
                            <button 
                                onClick={() => handleCancel(order.id)}
                                className="text-red-500 hover:text-red-400 hover:bg-red-500/10 px-3 py-1 rounded transition-colors text-xs font-bold border border-red-500/30"
                            >
                                Cancel
                            </button>
                        </td>
                    </tr>
                    );
                })}
            </tbody>
        </table>
      </div>
    </div>
  );
}
