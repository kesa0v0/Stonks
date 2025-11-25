// frontend/src/App.tsx
import { useState, useEffect } from 'react'
import axios from 'axios'
import type { Portfolio, OrderResponse } from './interfaces' // 타입 불러오기

// 환경변수 타입 단언 (Type Assertion)
const API_URL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000'

function App() {
  // state에 타입 지정: Portfolio이거나 아직 로딩 전이면 null
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [log, setLog] = useState<string[]>([])
  const [orderSide, setOrderSide] = useState<'BUY' | 'SELL'>('BUY')

  // 1. 내 포트폴리오 가져오기
  const fetchPortfolio = async () => {
    try {
      // 제네릭으로 응답 타입 지정 -> res.data가 Portfolio 타입으로 자동 인식됨
      const res = await axios.get<Portfolio>(`${API_URL}/portfolio`)
      setPortfolio(res.data)
    } catch (err) {
      console.error("포트폴리오 조회 실패:", err)
    }
  }

  // 매수/매도 통합 함수
  const placeOrder = async () => {
    try {
      const sideText = orderSide === 'BUY' ? '매수' : '매도'
      const sideColor = orderSide === 'BUY' ? '🔴' : '🔵'
      
      // [낙관적 업데이트 로직은 복잡해지니 일단 생략하거나, 매수/매도에 따라 분기 처리 필요]
      // 여기서는 간단하게 서버 요청만 먼저 보냅니다.
      
      const res = await axios.post<OrderResponse>(`${API_URL}/orders`, {
        ticker_id: "CRYPTO-COIN-BTC",
        side: orderSide, // 상태값 사용
        quantity: 0.01
      })
      
      addLog(`${sideColor} ${sideText} 접수 완료: ${res.data.order_id.slice(0, 8)}...`)
      
      // 딜레이 짧게 갱신
      setTimeout(fetchPortfolio, 200)

    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message
      addLog(`❌ 주문 실패: ${msg}`)
    }
  }

  const addLog = (msg: string) => setLog(prev => [msg, ...prev])

  useEffect(() => {
    fetchPortfolio()
    const interval = setInterval(fetchPortfolio, 3000)
    return () => clearInterval(interval)
  }, [])

  if (!portfolio) return <div style={{padding: 20}}>Loading STONKS (TS)...</div>

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '20px', fontFamily: 'sans-serif' }}>
      <h1 style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        📈 STONKS <span style={{fontSize: '0.6em', color: '#3b82f6', border: '1px solid #3b82f6', borderRadius: '4px', padding: '2px 6px'}}>TypeScript</span>
      </h1>
      
      {/* 1. 내 자산 현황 카드 */}
      <div style={{ 
        border: '1px solid #e5e7eb', 
        borderRadius: '12px', 
        padding: '24px',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
        backgroundColor: 'white'
      }}>
        <div style={{ marginBottom: '20px' }}>
          <h2 style={{ margin: 0, color: '#374151', fontSize: '1.1rem' }}>내 현금 잔고</h2>
          <p style={{ margin: 0, fontSize: '2rem', fontWeight: 'bold', color: '#111827' }}>
            {Math.floor(portfolio.cash_balance).toLocaleString()} KRW
          </p>
        </div>
        
        <div style={{ marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color: '#374151', fontSize: '1rem' }}>총 평가 자산</h3>
          <p style={{ margin: 0, fontSize: '1.5rem', fontWeight: 'bold', color: '#059669' }}>
            {Math.floor(portfolio.total_asset_value).toLocaleString()} KRW
          </p>
        </div>

        <hr style={{ border: 'none', borderTop: '1px solid #e5e7eb', margin: '20px 0' }} />
        
        <h4 style={{ margin: '0 0 10px 0' }}>보유 종목</h4>
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {portfolio.assets.map(asset => (
            <li key={asset.ticker_id} style={{ 
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px', background: '#f9fafb', borderRadius: '8px', marginBottom: '8px'
            }}>
              <div>
                  <strong style={{fontSize: '1.1em', color: '#111827'}}>{asset.name}</strong> 
                <span style={{color: '#6b7280', fontSize: '0.9em', marginLeft: '5px'}}>({asset.symbol})</span>
                <div style={{fontSize: '0.9em', color: '#4b5563'}}>
                  {asset.quantity}개 보유
                </div>
              </div>
              <div style={{textAlign: 'right'}}>
                  <div style={{fontWeight: 'bold', color: '#111827'}}>
                    {Math.floor(asset.total_value).toLocaleString()} 원
                  </div>
                  <div style={{
                    color: asset.profit_rate > 0 ? '#dc2626' : asset.profit_rate < 0 ? '#2563eb' : '#111827',
                    fontWeight: 'bold'
                  }}>
                    {asset.profit_rate > 0 ? '+' : asset.profit_rate < 0 ? '' : ''}{asset.profit_rate}%
                  </div>
              </div>
            </li>
          ))}
          {portfolio.assets.length === 0 && <li style={{color: '#9ca3af'}}>보유 중인 주식이 없습니다.</li>}
        </ul>
      </div>
      
      {/* 2. 주문(매수/매도) 패널 */}
      <div style={{ marginTop: '20px', textAlign: 'center' }}>
        
        {/* 탭 스위치 */}
        <div style={{ 
          display: 'flex', justifyContent: 'center', gap: '10px', marginBottom: '15px' 
        }}>
          <button
            onClick={() => setOrderSide('BUY')}
            style={{
              padding: '10px 20px',
              fontWeight: 'bold',
              cursor: 'pointer',
              border: 'none',
              borderRadius: '8px',
                backgroundColor: orderSide === 'BUY' ? '#ef4444' : '#f3f4f6',
                color: orderSide === 'BUY' ? 'white' : '#ef4444',
              transition: 'all 0.2s'
            }}
          >
            매수 (Buy)
          </button>
          <button
            onClick={() => setOrderSide('SELL')}
            style={{
              padding: '10px 20px',
              fontWeight: 'bold',
              cursor: 'pointer',
              border: 'none',
              borderRadius: '8px',
                backgroundColor: orderSide === 'SELL' ? '#3b82f6' : '#f3f4f6',
                color: orderSide === 'SELL' ? 'white' : '#3b82f6',
              transition: 'all 0.2s'
            }}
          >
            매도 (Sell)
          </button>
        </div>

        {/* 주문 실행 버튼 */}
        <button 
          onClick={placeOrder}
          style={{ 
            padding: '16px 32px', 
            fontSize: '18px', 
            fontWeight: 'bold',
            cursor: 'pointer',
              backgroundColor: orderSide === 'BUY' ? '#ef4444' : '#3b82f6', // 색상 변경
              color: 'white',
            border: 'none', 
            borderRadius: '8px',
            boxShadow: orderSide === 'BUY' 
              ? '0 4px 6px rgba(239, 68, 68, 0.3)' 
              : '0 4px 6px rgba(59, 130, 246, 0.3)',
            transition: 'transform 0.1s',
            width: '100%',
            maxWidth: '300px'
          }}
          onMouseDown={(e: React.MouseEvent) => (e.target as HTMLButtonElement).style.transform = 'scale(0.95)'}
          onMouseUp={(e: React.MouseEvent) => (e.target as HTMLButtonElement).style.transform = 'scale(1)'}
        >
          {orderSide === 'BUY' ? '🔴 비트코인 0.01개 매수' : '🔵 비트코인 0.01개 매도'}
        </button>
        
        <p style={{marginTop: '10px', color: '#666', fontSize: '0.9em'}}>
          * 현재가로 즉시 체결됩니다 (시장가)
        </p>
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