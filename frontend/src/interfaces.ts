import type { components } from './api/types';

// 1. Asset (자산) 타입
export type Asset = components['schemas']['AssetResponse'];

// 2. Portfolio (포트폴리오) 타입
export type Portfolio = components['schemas']['PortfolioResponse'];

// 3. OrderResponse (주문 응답) 타입
export type OrderResponse = components['schemas']['OrderResponse'];

// 4. OrderBook (호가창) 타입
// Generated OrderBookEntry has price: string, quantity: string (Decimal)
export type OrderBookEntry = components['schemas']['OrderBookEntry'];

export interface OrderBookResponse extends components['schemas']['OrderBookResponse'] {
  timestamp?: number; // Added manually for race condition handling
}

// 5. Ranking 타입들
export type RankingEntry = components['schemas']['RankingEntry'];
export type HallOfFameResponse = components['schemas']['HallOfFameResponse'];

// 6. Order list item (for /me/orders)
// OpenOrders relies on fields (type, target_price, etc.) that might be missing in the strict generated schema.
// We extend it to include them, assuming the backend sends them.
export interface OrderListItem extends components['schemas']['OrderListResponse'] {
  type: components['schemas']['OrderType'];
  side: components['schemas']['OrderSide'] | string;
  target_price?: string | null;
  stop_price?: string | null;
  trailing_gap?: string | null;
}

export type TickerResponse = components['schemas']['TickerResponse'];

export type MeProfile = components['schemas']['UserResponse'] & {
  avatar_url?: string;
  discord_user_id?: string;
  discord_avatar?: string;
  discriminator?: string;
};

export type MoverResponse = components['schemas']['MoverResponse'];
