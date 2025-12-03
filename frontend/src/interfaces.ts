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
  total_asset_change_percent?: string;
  assets: Asset[];
}

// 3. OrderResponse (주문 응답) 타입
export interface OrderResponse {
  order_id: string;
  status: string;
  message: string;
}

// 4. OrderBook (호가창) 타입
export interface OrderBookEntry {
  price: number;
  quantity: number;
}

export interface OrderBookResponse {
  bids: OrderBookEntry[];
  asks: OrderBookEntry[];
}

// 5. Ranking 타입들
export interface RankingEntry {
  rank: number;
  nickname: string;
  value: string; // 서버에서 문자열로 전달됨
}

export interface HallOfFameResponse {
  top_profit?: RankingEntry;
  top_loss?: RankingEntry;
  top_volume?: RankingEntry;
  top_win_rate?: RankingEntry;
  top_fees?: RankingEntry;
  top_night?: RankingEntry;
}

// 6. Order list item (for /me/orders)
export interface OrderListItem {
  id: string;
  ticker_id: string;
  side: 'BUY' | 'SELL' | string;
  status: string;
  quantity: string; // DecimalStr
  price?: string;   // DecimalStr
  created_at: string;
}

export interface RankingEntry {
  rank: number;
  nickname: string;
  value: string; // DecimalStr
  extra_info?: Record<string, unknown>;
}

export interface HallOfFameResponse {
  top_profit?: RankingEntry;
  top_loss?: RankingEntry;
  top_volume?: RankingEntry;
  top_win_rate?: RankingEntry;
  top_fees?: RankingEntry;
  top_night?: RankingEntry;
}

export interface TickerResponse {
  id: string;
  symbol: string;
  name: string;
  market_type: 'KRX' | 'US' | 'CRYPTO' | 'HUMAN';
  currency: 'KRW' | 'USD';
  is_active: boolean;
  source: string;
  current_price?: string;
  change_percent?: string;
  volume?: string;
}

export interface MoverResponse {
  ticker: TickerResponse;
  price: string;
  change_percent: string;
  volume: string;
  value: string;
}

export interface OrderBookResponse {
  ticker_id: string;
  bids: OrderBookEntry[];
  asks: OrderBookEntry[];
}
export interface OrderBookEntry {
  price: number;
  quantity: number;
}