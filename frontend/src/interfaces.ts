// frontend/src/types.ts

// 1. Asset (자산) 타입
export interface Asset {
  ticker_id: string;
  symbol: string;
  name: string;
  quantity: number;
  average_price: number;
  current_price: number;
  total_value: number;
  profit_rate: number;
}

// 2. Portfolio (포트폴리오) 타입
export interface Portfolio {
  cash_balance: number;
  total_asset_value: number;
  assets: Asset[];
}

// 3. OrderResponse (주문 응답) 타입
export interface OrderResponse {
  order_id: string;
  status: string;
  message: string;
}