import { useState, useEffect } from 'react';
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
    // Optional: Polling or use a global event bus for order updates
    const interval = setInterval(fetchOrders, 5000);
    return () => clearInterval(interval);
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
                    <th className="px-4 py-3 text-right">Price</th>
                    <th className="px-4 py-3 text-right">Amount</th>
                    <th className="px-4 py-3 text-right">Filled</th>
                    <th className="px-4 py-3 text-center">Status</th>
                    <th className="px-4 py-3 text-center">Action</th>
                </tr>
            </thead>
            <tbody className="divide-y divide-[#314368]">
                {orders.map(order => (
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
                        <td className="px-4 py-3 text-right font-mono text-white">
                            {order.price 
                                ? Number(order.price).toLocaleString() 
                                : (order.target_price 
                                    ? Number(order.target_price).toLocaleString() 
                                    : 'Market')}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-white">
                             {Number(order.quantity).toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-white/60">
                             {/* Assuming API returns filled or calculate it? 
                                The OrderListItem interface currently has 'quantity' (total) and maybe 'unfilled_quantity'? 
                                Let's check interface. If not, assume 0 filled for now or check API response type.
                                The 'OrderListResponse' in backend has 'quantity'. 'unfilled_quantity' is in Detail but List?
                                'OrderListResponse' in backend/schemas/order.py doesn't have unfilled_quantity explicitly listed 
                                but ConfigDict(extra='ignore') might hide it if not in schema.
                                Actually `me.py` calls `get_user_open_orders`. 
                                Let's assume 0% filled for PENDING orders usually, or check schema.
                                Schema `OrderListResponse` only has `quantity`.
                                For now, let's just show Total Quantity.
                             */}
                             -
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
                ))}
            </tbody>
        </table>
      </div>
    </div>
  );
}
