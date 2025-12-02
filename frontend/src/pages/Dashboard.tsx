// Extracted from previous App.tsx content into a page component
import { useEffect, useState } from 'react';
import api from '../api/client';
import type { Portfolio, OrderResponse } from '../interfaces';

const WS_URL = (import.meta.env.VITE_WS_URL as string) || 'ws://localhost:8000/ws';

interface OrderHistoryItem {
  id: string;
  created_at: string;
  ticker_id: string;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  status: string;
}

export default function Dashboard() {
  const isAxiosError = (e: unknown): e is { response?: { data?: { detail?: string } } } => {
    return typeof e === 'object' && e !== null && 'response' in (e as Record<string, unknown>);
  };
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [orderSide, setOrderSide] = useState<'BUY' | 'SELL'>('BUY');
  const [selectedTicker, setSelectedTicker] = useState('CRYPTO-COIN-DOGE');
  const [activeTab, setActiveTab] = useState<'TRADE' | 'HISTORY'>('TRADE');
  const [orderHistory, setOrderHistory] = useState<OrderHistoryItem[]>([]);

  const fetchPortfolio = async () => {
    try {
      const data = await api.get('me/portfolio').json<Portfolio>();
      setPortfolio(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    // defer to avoid lint warning about state updates directly in effect
    setTimeout(fetchPortfolio, 0);
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => console.log('🟢 Connected to Real-time Market');
    ws.onmessage = event => {
      const data = JSON.parse(event.data);
      setPortfolio(prev => {
        if (!prev) return null;
        const updatedAssets = prev.assets.map(asset => {
          if (asset.ticker_id === data.ticker_id) {
            const newTotalValue = asset.quantity * data.price;
            const newProfitRate = asset.average_price > 0 ? ((data.price - asset.average_price) / asset.average_price) * 100 : 0;
            return {
              ...asset,
              current_price: data.price,
              total_value: newTotalValue,
              profit_rate: parseFloat(newProfitRate.toFixed(2))
            };
          }
          return asset;
        });
        const newTotalStockValue = updatedAssets.reduce((sum, a) => sum + a.total_value, 0);
        return {
          ...prev,
          total_asset_value: prev.cash_balance + newTotalStockValue,
          assets: updatedAssets
        };
      });
    };
    return () => ws.close();
  }, []);

  const fetchOrderHistory = async () => {
    try {
      const data = await api.get('me/orders').json<OrderHistoryItem[]>();
      setOrderHistory(data);
    } catch (err) {
      console.error(err);
    }
  };
  useEffect(() => {
    if (activeTab === 'HISTORY') setTimeout(fetchOrderHistory, 0);
  }, [activeTab]);

  const placeOrder = async () => {
    try {
      const sideText = orderSide === 'BUY' ? '매수' : '매도';
      const res = await api.post('orders', {
        json: {
          ticker_id: selectedTicker,
          side: orderSide,
          quantity: selectedTicker.includes('DOGE') ? 10 : 0.01
        }
      }).json<OrderResponse>();
      addLog(`✅ ${sideText} 접수: ${res.order_id.slice(0, 8)}...`);
      setTimeout(fetchPortfolio, 200);
    } catch (err) {
      const detail = isAxiosError(err) ? err.response?.data?.detail : undefined;
      const message = err instanceof Error ? err.message : 'Unknown error';
      addLog(`❌ 주문 실패: ${detail || message}`);
    }
  };

  const addLog = (msg: string) => setLog(prev => [msg, ...prev]);
  if (!portfolio) return <div style={{ padding: 20 }}>Loading...</div>;

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>🚀 STONKS Live</h1>
      <div style={{ border: '1px solid #e5e7eb', borderRadius: '12px', padding: '24px', marginBottom: '20px' }}>
        <h2>총 자산: {Math.floor(portfolio.total_asset_value).toLocaleString()} KRW</h2>
        <p>현금: {Math.floor(portfolio.cash_balance).toLocaleString()} KRW</p>
        <h4>보유 종목</h4>
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {portfolio.assets.map(asset => (
            <li key={asset.ticker_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: '#f9fafb', marginBottom: '5px', borderRadius: '5px' }}>
              <span>
                <strong>{asset.name}</strong> ({asset.quantity}개)
              </span>
              <span style={{ color: asset.profit_rate >= 0 ? '#ef4444' : '#3b82f6', fontWeight: 'bold' }}>
                {asset.current_price.toLocaleString()}원 ({asset.profit_rate}%)
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div style={{ display: 'flex', borderBottom: '1px solid #ddd', marginBottom: '20px' }}>
        <button onClick={() => setActiveTab('TRADE')} style={{ flex: 1, padding: '15px', border: 'none', background: 'none', cursor: 'pointer', fontSize: '16px', fontWeight: 'bold', borderBottom: activeTab === 'TRADE' ? '3px solid #3b82f6' : 'none', color: activeTab === 'TRADE' ? '#3b82f6' : '#666' }}>매매 (Trade)</button>
        <button onClick={() => setActiveTab('HISTORY')} style={{ flex: 1, padding: '15px', border: 'none', background: 'none', cursor: 'pointer', fontSize: '16px', fontWeight: 'bold', borderBottom: activeTab === 'HISTORY' ? '3px solid #3b82f6' : 'none', color: activeTab === 'HISTORY' ? '#3b82f6' : '#666' }}>거래 내역 (History)</button>
      </div>

      {activeTab === 'TRADE' ? (
        <div style={{ textAlign: 'center' }}>
          <div style={{ marginBottom: '15px' }}>
            <label style={{ marginRight: '15px' }}> <input type="radio" checked={selectedTicker === 'CRYPTO-COIN-DOGE'} onChange={() => setSelectedTicker('CRYPTO-COIN-DOGE')} /> 🐕 도지코인 </label>
            <label> <input type="radio" checked={selectedTicker === 'CRYPTO-COIN-BTC'} onChange={() => setSelectedTicker('CRYPTO-COIN-BTC')} /> 🪙 비트코인 </label>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', marginBottom: '10px' }}>
            <button onClick={() => setOrderSide('BUY')} style={{ padding: '10px 20px', borderRadius: '8px', border: 'none', background: orderSide === 'BUY' ? '#ef4444' : '#f3f4f6', color: orderSide === 'BUY' ? 'white' : 'black', fontWeight: 'bold', cursor: 'pointer' }}>매수</button>
            <button onClick={() => setOrderSide('SELL')} style={{ padding: '10px 20px', borderRadius: '8px', border: 'none', background: orderSide === 'SELL' ? '#3b82f6' : '#f3f4f6', color: orderSide === 'SELL' ? 'white' : 'black', fontWeight: 'bold', cursor: 'pointer' }}>매도</button>
          </div>
          <button onClick={placeOrder} style={{ padding: '15px 30px', fontSize: '18px', fontWeight: 'bold', borderRadius: '8px', border: 'none', cursor: 'pointer', color: 'white', backgroundColor: orderSide === 'BUY' ? '#ef4444' : '#3b82f6', width: '100%' }}>
            {orderSide === 'BUY' ? '매수' : '매도'} 실행
          </button>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
            <thead>
              <tr style={{ background: '#f9fafb', color: '#6b7280' }}>
                <th style={{ padding: '10px', textAlign: 'left' }}>시간</th>
                <th style={{ padding: '10px', textAlign: 'left' }}>종목</th>
                <th style={{ padding: '10px', textAlign: 'center' }}>종류</th>
                <th style={{ padding: '10px', textAlign: 'right' }}>가격</th>
                <th style={{ padding: '10px', textAlign: 'right' }}>수량</th>
                <th style={{ padding: '10px', textAlign: 'center' }}>상태</th>
              </tr>
            </thead>
            <tbody>
              {orderHistory.map((order) => (
                <tr key={order.id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: '10px', color: '#666' }}>{new Date(order.created_at).toLocaleString()}</td>
                  <td style={{ padding: '10px', fontWeight: 'bold' }}>{order.ticker_id.split('-').pop()}</td>
                  <td style={{ padding: '10px', textAlign: 'center' }}>
                    <span style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold', background: order.side === 'BUY' ? '#fee2e2' : '#dbeafe', color: order.side === 'BUY' ? '#dc2626' : '#2563eb' }}>
                      {order.side === 'BUY' ? '매수' : '매도'}
                    </span>
                  </td>
                  <td style={{ padding: '10px', textAlign: 'right' }}>{Math.floor(order.price).toLocaleString()}</td>
                  <td style={{ padding: '10px', textAlign: 'right' }}>{order.quantity}</td>
                  <td style={{ padding: '10px', textAlign: 'center' }}>{order.status === 'FILLED' ? '✅ 성공' : '❌ 실패'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {orderHistory.length === 0 && <p style={{ textAlign: 'center', color: '#999' }}>거래 내역이 없습니다.</p>}
        </div>
      )}

      <div style={{ marginTop: '30px' }}>
        <h4 style={{ color: '#6b7280' }}>System Log</h4>
        <div style={{ background: '#1f2937', color: '#10b981', padding: '15px', borderRadius: '8px', height: '100px', overflowY: 'auto', fontSize: '12px' }}>
          {log.map((l, i) => <div key={i}>&gt; {l}</div>)}
        </div>
      </div>
    </div>
  );
}
