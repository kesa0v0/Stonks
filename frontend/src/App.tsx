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
  
  // [NEW] 선택된 코인 (기본값 도지!)
  const [selectedTicker, setSelectedTicker] = useState("CRYPTO-COIN-DOGE")

  // 초기 데이터 로딩
  const fetchPortfolio = async () => {
    try {
      const res = await axios.get<Portfolio>(`${API_URL}/portfolio`)
      setPortfolio(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  // [핵심] 실시간 가격 반영 (웹소켓)
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
      
      {/* 자산 카드 */}
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

      {/* 주문 패널 */}
      <div style={{ textAlign: 'center' }}>
        {/* 코인 선택 라디오 버튼 */}
        <div style={{ marginBottom: '15px' }}>
            <label style={{marginRight: '15px'}}>
                <input 
                    type="radio" 
                    checked={selectedTicker === "CRYPTO-COIN-DOGE"} 
                    onChange={() => setSelectedTicker("CRYPTO-COIN-DOGE")}
                /> 🐕 도지코인 (10개 단위)
            </label>
            <label>
                <input 
                    type="radio" 
                    checked={selectedTicker === "CRYPTO-COIN-BTC"} 
                    onChange={() => setSelectedTicker("CRYPTO-COIN-BTC")}
                /> 🪙 비트코인 (0.01개 단위)
            </label>
        </div>

        {/* 매수/매도 버튼들 (아까 만든 코드 유지) */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', marginBottom: '10px' }}>
             <button onClick={() => setOrderSide('BUY')} style={{/*스타일생략*/ padding:'10px', background: orderSide==='BUY'?'red':'#eee'}}>매수</button>
             <button onClick={() => setOrderSide('SELL')} style={{/*스타일생략*/ padding:'10px', background: orderSide==='SELL'?'blue':'#eee'}}>매도</button>
        </div>
        
        <button onClick={placeOrder} style={{ 
            padding: '15px 30px', fontSize: '18px', fontWeight: 'bold', borderRadius: '8px', border: 'none',
            color: 'white', backgroundColor: orderSide === 'BUY' ? '#ef4444' : '#3b82f6' 
        }}>
            {orderSide === 'BUY' ? '매수' : '매도'} 실행
        </button>
      </div>

      {/* 3. 로그 */}
      <div style={{ marginTop: '30px' }}>
        <h4 style={{ color: '#6b7280' }}>거래 로그</h4>
        <div style={{ 
          background: '#1f2937', 
          color: '#10b981', 
          padding: '15px', 
          borderRadius: '8px',
          fontFamily: 'monospace',
          height: '150px',
          overflowY: 'auto'
        }}>
          {log.length === 0 && <span style={{color: '#4b5563'}}>대기 중...</span>}
          {log.map((l, i) => <div key={i}>&gt; {l}</div>)}
        </div>
      </div>
    </div>
  )
}

export default App