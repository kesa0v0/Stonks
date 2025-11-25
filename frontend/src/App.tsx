// frontend/src/App.tsx
import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import type { Portfolio, OrderResponse } from './interfaces'

const API_URL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000'
// http:// -> ws:// 로 변환 (웹소켓 주소)
const WS_URL = API_URL.replace('http', 'ws') + '/ws'

function App() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [log, setLog] = useState<string[]>([])
  const [orderSide, setOrderSide] = useState<'BUY' | 'SELL'>('BUY')
  
  // 선택된 코인 (기본값 도지!)
  const [selectedTicker, setSelectedTicker] = useState("CRYPTO-COIN-DOGE")

  // 탭 상태 (TRADE: 매매화면, HISTORY: 거래내역)
  const [activeTab, setActiveTab] = useState<'TRADE' | 'HISTORY'>('TRADE')
  const [orderHistory, setOrderHistory] = useState<OrderHistoryItem[]>([])

  // 초기 데이터 로딩
  const fetchPortfolio = async () => {
    try {
      const res = await axios.get<Portfolio>(`${API_URL}/portfolio`)
      setPortfolio(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  // 실시간 가격 반영 (웹소켓)
  useEffect(() => {
    fetchPortfolio() // 처음 한 번은 전체 로딩

    const ws = new WebSocket(WS_URL)

    ws.onopen = () => console.log("🟢 Connected to Real-time Market")
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      // data = { ticker_id: "...", price: 150, timestamp: ... }

      setPortfolio(prev => {
        if (!prev) return null

        // 내 포트폴리오에 있는 종목이면 가격 업데이트
        const updatedAssets = prev.assets.map(asset => {
          if (asset.ticker_id === data.ticker_id) {
            // 가격 변동에 따른 평가액 재계산
            const newTotalValue = asset.quantity * data.price
            const newProfitRate = asset.average_price > 0 
              ? ((data.price - asset.average_price) / asset.average_price) * 100 
              : 0
            
            return {
              ...asset,
              current_price: data.price,
              total_value: newTotalValue,
              profit_rate: parseFloat(newProfitRate.toFixed(2))
            }
          }
          return asset
        })

        // 총 자산 재계산 (현금 + 모든 주식 평가액)
        const newTotalStockValue = updatedAssets.reduce((sum, a) => sum + a.total_value, 0)

        return {
          ...prev,
          total_asset_value: prev.cash_balance + newTotalStockValue,
          assets: updatedAssets
        }
      })
    }

    return () => ws.close()
  }, [])

  // 거래 내역 가져오기
  const fetchOrderHistory = async () => {
    try {
      const res = await axios.get<OrderHistoryItem[]>(`${API_URL}/orders`)
      setOrderHistory(res.data)
    } catch (err) {
      console.error(err)
    }
  }
  // 탭이 바뀔 때마다 데이터 갱신
  useEffect(() => {
    if (activeTab === 'HISTORY') {
      fetchOrderHistory()
    }
  }, [activeTab])

  const placeOrder = async () => {
    try {
      const sideText = orderSide === 'BUY' ? '매수' : '매도'
      const res = await axios.post<OrderResponse>(`${API_URL}/orders`, {
        ticker_id: selectedTicker, // 선택된 코인으로 주문
        side: orderSide,
        quantity: selectedTicker.includes('DOGE') ? 10 : 0.01 // 도지는 10개씩, 비트는 0.01개씩
      })
      
      addLog(`✅ ${sideText} 접수: ${res.data.order_id.slice(0, 8)}...`)
      
      // 주문 직후에는 포트폴리오 수량이 바뀌므로 API 한 번 호출 (가격은 소켓이 해줌)
      setTimeout(fetchPortfolio, 200)
    } catch (err: any) {
      addLog(`❌ 주문 실패: ${err.response?.data?.detail || err.message}`)
    }
  }

  const addLog = (msg: string) => setLog(prev => [msg, ...prev])

  if (!portfolio) return <div style={{padding: 20}}>Loading...</div>

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>🚀 STONKS Live</h1>
      {/* 자산 카드 (기존 유지) */}
      <div style={{ border: '1px solid #e5e7eb', borderRadius: '12px', padding: '24px', marginBottom: '20px' }}>
        <h2>총 자산: {Math.floor(portfolio.total_asset_value).toLocaleString()} KRW</h2>
        <p>현금: {Math.floor(portfolio.cash_balance).toLocaleString()} KRW</p>
        <h4>보유 종목</h4>
        <ul style={{listStyle: 'none', padding: 0}}>
          {portfolio.assets.map(asset => (
            <li key={asset.ticker_id} style={{ 
              display: 'flex', justifyContent: 'space-between', padding: '10px', 
              background: '#f9fafb', marginBottom: '5px', borderRadius: '5px'
            }}>
              <span>
                <strong>{asset.name}</strong> ({asset.quantity}개)
              </span>
              <span style={{ 
                color: asset.profit_rate >= 0 ? '#ef4444' : '#3b82f6', 
                fontWeight: 'bold' 
              }}>
                {asset.current_price.toLocaleString()}원 ({asset.profit_rate}%)
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* 탭 메뉴 */}
      <div style={{ display: 'flex', borderBottom: '1px solid #ddd', marginBottom: '20px' }}>
        <button 
          onClick={() => setActiveTab('TRADE')}
          style={{
            flex: 1, padding: '15px', border: 'none', background: 'none', cursor: 'pointer',
            fontSize: '16px', fontWeight: 'bold',
            borderBottom: activeTab === 'TRADE' ? '3px solid #3b82f6' : 'none',
            color: activeTab === 'TRADE' ? '#3b82f6' : '#666'
          }}
        >
          매매 (Trade)
        </button>
        <button 
          onClick={() => setActiveTab('HISTORY')}
          style={{
            flex: 1, padding: '15px', border: 'none', background: 'none', cursor: 'pointer',
            fontSize: '16px', fontWeight: 'bold',
            borderBottom: activeTab === 'HISTORY' ? '3px solid #3b82f6' : 'none',
            color: activeTab === 'HISTORY' ? '#3b82f6' : '#666'
          }}
        >
          거래 내역 (History)
        </button>
      </div>

      {/* 탭 내용 */}
      {activeTab === 'TRADE' ? (
        /* 기존 매매 UI (주문 패널) */
        <div style={{ textAlign: 'center' }}>
           {/* ... 아까 만든 코인 선택, 매수/매도 버튼들 ... */}
           {/* (기존 코드 그대로 두세요) */}
           <div style={{ marginBottom: '15px' }}>
              <label style={{marginRight: '15px'}}>
                  <input type="radio" checked={selectedTicker === "CRYPTO-COIN-DOGE"} onChange={() => setSelectedTicker("CRYPTO-COIN-DOGE")}/> 🐕 도지코인
              </label>
              <label>
                  <input type="radio" checked={selectedTicker === "CRYPTO-COIN-BTC"} onChange={() => setSelectedTicker("CRYPTO-COIN-BTC")}/> 🪙 비트코인
              </label>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', marginBottom: '10px' }}>
               <button onClick={() => setOrderSide('BUY')} style={{padding:'10px 20px', borderRadius:'8px', border:'none', background: orderSide==='BUY'?'#ef4444':'#f3f4f6', color: orderSide==='BUY'?'white':'black', fontWeight:'bold', cursor:'pointer'}}>매수</button>
               <button onClick={() => setOrderSide('SELL')} style={{padding:'10px 20px', borderRadius:'8px', border:'none', background: orderSide==='SELL'?'#3b82f6':'#f3f4f6', color: orderSide==='SELL'?'white':'black', fontWeight:'bold', cursor:'pointer'}}>매도</button>
          </div>
          <button onClick={placeOrder} style={{ 
              padding: '15px 30px', fontSize: '18px', fontWeight: 'bold', borderRadius: '8px', border: 'none', cursor: 'pointer',
              color: 'white', backgroundColor: orderSide === 'BUY' ? '#ef4444' : '#3b82f6', width: '100%'
          }}>
              {orderSide === 'BUY' ? '매수' : '매도'} 실행
          </button>
        </div>
      ) : (
        /* [NEW] 거래 내역 테이블 UI */
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
              {orderHistory.map(order => (
                <tr key={order.id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: '10px', color: '#666' }}>
                    {new Date(order.created_at).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px', fontWeight: 'bold' }}>
                    {order.ticker_id.split('-').pop()}
                  </td>
                  <td style={{ padding: '10px', textAlign: 'center' }}>
                    <span style={{
                      padding: '4px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold',
                      background: order.side === 'BUY' ? '#fee2e2' : '#dbeafe',
                      color: order.side === 'BUY' ? '#dc2626' : '#2563eb'
                    }}>
                      {order.side === 'BUY' ? '매수' : '매도'}
                    </span>
                  </td>
                  <td style={{ padding: '10px', textAlign: 'right' }}>
                    {Math.floor(order.price).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px', textAlign: 'right' }}>
                    {order.quantity}
                  </td>
                  <td style={{ padding: '10px', textAlign: 'center' }}>
                    {order.status === 'FILLED' ? '✅ 성공' : '❌ 실패'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {orderHistory.length === 0 && <p style={{textAlign: 'center', color: '#999'}}>거래 내역이 없습니다.</p>}
        </div>
      )}
      {/* 로그창 (기존 유지) */}
      <div style={{ marginTop: '30px' }}>
        <h4 style={{ color: '#6b7280' }}>System Log</h4>
        <div style={{ background: '#1f2937', color: '#10b981', padding: '15px', borderRadius: '8px', height: '100px', overflowY: 'auto', fontSize: '12px' }}>
          {log.map((l, i) => <div key={i}>&gt; {l}</div>)}
        </div>
      </div>
    </div>
  )
}

export default App