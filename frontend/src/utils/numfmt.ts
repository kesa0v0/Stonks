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
  const [intPart, fracPart] = s.split('.');
  const withSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return fracPart ? `${withSep}.${fracPart}` : withSep;
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
