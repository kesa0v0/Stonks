import Decimal from 'decimal.js';

export type RoundingKey = 'ROUND_DOWN' | 'ROUND_HALF_UP' | 'ROUND_HALF_EVEN';

const ROUNDING_MAP: Record<RoundingKey, Decimal.Rounding> = {
  ROUND_DOWN: Decimal.ROUND_DOWN,
  ROUND_HALF_UP: Decimal.ROUND_HALF_UP,
  ROUND_HALF_EVEN: Decimal.ROUND_HALF_EVEN,
};

// Default per-currency fraction digits
const CURRENCY_DIGITS: Record<string, number> = {
  KRW: 0,
  USD: 2,
  USDT: 2,
  EUR: 2,
  JPY: 0,
  BTC: 8,
  ETH: 8,
};

export const getCurrencyDigits = (code?: string) => {
  if (!code) return 2; // sensible default
  return CURRENCY_DIGITS[code.toUpperCase()] ?? 2;
};

// FX helper: USD -> KRW rate from env, fallback 1300
export function getUsdKrwRate(): number {
  const raw = (import.meta as any)?.env?.VITE_USD_KRW;
  const n = Number(raw);
  if (isFinite(n) && n > 0) return n;
  return 1300; // sensible default
}

// Asset quantity digits (per-asset minimum increment). Default to 4 for UI readability.
const ASSET_QUANTITY_DIGITS: Record<string, number> = {
  BTC: 8,
  ETH: 8,
};

export const getAssetQuantityDigits = (symbolOrTickerId?: string) => {
  if (!symbolOrTickerId) return 4;
  // Try to extract asset symbol from common identifier patterns
  const upper = symbolOrTickerId.toUpperCase();
  // e.g., 'CRYPTO-COIN-ETH' -> 'ETH', 'ETH/KRW' -> 'ETH'
  const parts = upper.split(/[\-\/]/);
  const guess = parts[parts.length - 1];
  return ASSET_QUANTITY_DIGITS[guess] ?? 4;
};

// Global number formatting preferences
let NUMBER_LOCALE = 'en-US';
let USE_INTL = false;

export const setNumberLocale = (locale: string) => { NUMBER_LOCALE = locale; };
export const setUseIntlFormatting = (useIntl: boolean) => { USE_INTL = useIntl; };

export const toFixedString = (
  value: Decimal.Value,
  fractionDigits: number,
  rounding: RoundingKey = 'ROUND_DOWN',
) => {
  try {
    const dec = new Decimal(value);
    return dec.toDecimalPlaces(fractionDigits, ROUNDING_MAP[rounding]).toFixed(fractionDigits);
  } catch {
    return ''.padStart(Math.max(0, fractionDigits), '0');
  }
};

export const formatWithThousands = (s: string) => {
  if (!s) return s;
  if (!USE_INTL) {
    const [intPart, fracPart] = s.split('.');
    const withSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return fracPart ? `${withSep}.${fracPart}` : withSep;
  }
  // Intl path: format integer part via Intl, preserve decimal string
  const [intPart, fracPart] = s.split('.');
  // Use BigInt for safety with large integers
  const intVal = intPart ? BigInt(intPart) : 0n;
  const intFormatted = new Intl.NumberFormat(NUMBER_LOCALE, { maximumFractionDigits: 0 }).format(intVal);
  return fracPart ? `${intFormatted}.${fracPart}` : intFormatted;
};

export const formatCurrencyDisplay = (
  value: Decimal.Value,
  currencyCode?: string,
  rounding: RoundingKey = 'ROUND_DOWN',
) => {
  const digits = getCurrencyDigits(currencyCode);
  const fixed = toFixedString(value, digits, rounding);
  return formatWithThousands(fixed);
};

// Suggested global policy presets
export const INPUT_ROUNDING: RoundingKey = 'ROUND_DOWN';
export const REPORT_ROUNDING: RoundingKey = 'ROUND_HALF_UP';
