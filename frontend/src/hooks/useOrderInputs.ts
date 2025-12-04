import { useState, useMemo } from 'react';
import Decimal from 'decimal.js';

export type OrderType = 'MARKET' | 'LIMIT' | 'STOP_LOSS' | 'TAKE_PROFIT' | 'STOP_LIMIT' | 'TRAILING_STOP';

const d = (v: Decimal.Value | undefined | null) => {
  try { if (v === undefined || v === null || v === '') return new Decimal(0); return new Decimal(v as Decimal.Value); } catch { return new Decimal(0); }
};

export function useOrderInputs(initial: {
  orderType: OrderType;
  price?: number | '';
  amount?: string;
  total?: string;
  realTimePrice?: number;
}) {
  const [orderType, setOrderType] = useState<OrderType>(initial.orderType);
  const [price, setPrice] = useState<number | ''>(initial.price ?? '');
  const [amount, setAmount] = useState<string>(initial.amount ?? '');
  const [total, setTotal] = useState<string>(initial.total ?? '');
  const [lastEdited, setLastEdited] = useState<'AMOUNT' | 'TOTAL'>('AMOUNT');

  const effectivePrice = useMemo(() => {
    const isMarketLike = (orderType === 'MARKET' || orderType === 'STOP_LOSS' || orderType === 'TAKE_PROFIT' || orderType === 'TRAILING_STOP');
    return isMarketLike ? initial.realTimePrice ?? 0 : (typeof price === 'number' ? price : parseFloat(String(price)) || 0);
  }, [orderType, price, initial.realTimePrice]);

  const setAmountAndTotalByPrice = (amtStr: string) => {
    setAmount(amtStr);
    setLastEdited('AMOUNT');
    const amt = parseFloat(amtStr);
    const p = effectivePrice || 0;
    if (!isNaN(amt) && p !== 0) setTotal(d(amt).mul(p).toFixed(0)); else if (amtStr === '') setTotal('');
  };

  const setTotalAndAmountByPrice = (totStr: string) => {
    setTotal(totStr);
    setLastEdited('TOTAL');
    const tot = parseFloat(totStr);
    const p = effectivePrice || 0;
    if (!isNaN(tot) && p !== 0) setAmount(d(tot).div(p).toFixed(8)); else if (totStr === '') setAmount('');
  };

  return {
    orderType,
    setOrderType,
    price,
    setPrice,
    amount,
    total,
    lastEdited,
    setAmountAndTotalByPrice,
    setTotalAndAmountByPrice,
  };
}
