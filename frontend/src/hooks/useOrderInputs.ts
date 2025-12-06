import { useState, useMemo } from 'react';
import Decimal from 'decimal.js';

export type OrderType = 'MARKET' | 'LIMIT' | 'STOP_LOSS' | 'TAKE_PROFIT' | 'STOP_LIMIT' | 'TRAILING_STOP';

const d = (v: Decimal.Value | undefined | null) => {
  try { if (v === undefined || v === null || v === '') return new Decimal(0); return new Decimal(v); } catch { return new Decimal(0); }
};

export function useOrderInputs(initial: {
  orderType: OrderType;
  price?: string | number | '';
  amount?: string;
  total?: string;
  realTimePrice?: Decimal.Value;
}) {
  const [orderType, setOrderType] = useState<OrderType>(initial.orderType);
  const [price, setPrice] = useState<string>(initial.price ? String(initial.price) : '');
  const [amount, setAmount] = useState<string>(initial.amount ?? '');
  const [total, setTotal] = useState<string>(initial.total ?? '');
  const [lastEdited, setLastEdited] = useState<'AMOUNT' | 'TOTAL'>('AMOUNT');

  const effectivePrice = useMemo(() => {
    const isMarketLike = (orderType === 'MARKET' || orderType === 'STOP_LOSS' || orderType === 'TAKE_PROFIT' || orderType === 'TRAILING_STOP');
    if (isMarketLike) {
        return d(initial.realTimePrice);
    }
    return d(price);
  }, [orderType, price, initial.realTimePrice]);

  const setAmountAndTotalByPrice = (amtStr: string) => {
    setAmount(amtStr);
    setLastEdited('AMOUNT');
    const amt = d(amtStr);
    const p = effectivePrice;
    
    // Check if input is valid for calculation
    if (amtStr && !amt.isNaN() && !p.isZero()) {
        setTotal(amt.mul(p).toFixed(0, Decimal.ROUND_DOWN)); 
    } else if (amtStr === '') {
        setTotal('');
    }
  };

  const setTotalAndAmountByPrice = (totStr: string) => {
    setTotal(totStr);
    setLastEdited('TOTAL');
    const tot = d(totStr);
    const p = effectivePrice;
    
    if (totStr && !tot.isNaN() && !p.isZero()) {
        setAmount(tot.div(p).toFixed(8, Decimal.ROUND_DOWN));
    } else if (totStr === '') {
        setAmount('');
    }
  };

  return {
    orderType,
    setOrderType,
    price,
    setPrice, // Now expects string
    amount,
    total,
    lastEdited,
    setAmountAndTotalByPrice,
    setTotalAndAmountByPrice,
  };
}
