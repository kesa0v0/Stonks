import { useMemo } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import Decimal from 'decimal.js';
import { getCurrencyDigits, toFixedString, formatCurrencyDisplay } from '../../utils/numfmt';

type Side = 'BUY' | 'SELL';

const d = (v: Decimal.Value | undefined | null) => {
  try {
    if (v === undefined || v === null || v === '') return new Decimal(0);
    return new Decimal(v as Decimal.Value);
  } catch {
    return new Decimal(0);
  }
};

const Schema = z.object({
  quantity: z
    .string()
    .transform((v) => (v ?? '').trim())
    .refine((v) => {
      try {
        const q = new Decimal(v || '0');
        return q.gt(0);
      } catch {
        return false;
      }
    }, { message: 'Amount must be greater than 0' }),
});

type Form = z.infer<typeof Schema>;

export default function ValidatedOrderForm({
  currency,
  side,
  effectivePrice,
  effectiveFeeRate,
  onSubmit,
  amountUnitLabel,
  submitLabel,
}: {
  currency: string;
  side: Side;
  effectivePrice: number | undefined;
  effectiveFeeRate: number;
  onSubmit: (quantity: number) => void;
  amountUnitLabel?: string;
  submitLabel?: string;
}) {
  const { register, handleSubmit, setValue, control, formState: { errors, isSubmitting } } = useForm<Form>({
    resolver: zodResolver(Schema),
    defaultValues: { quantity: '' },
  });

  const qtyStr = useWatch({ control, name: 'quantity' }) || '';
  const priceDec = (typeof effectivePrice === 'number' && isFinite(effectivePrice) && effectivePrice > 0)
    ? new Decimal(effectivePrice)
    : new Decimal(0);

  const qtyDec = useMemo(() => {
    try { return new Decimal((qtyStr as string) || '0'); } catch { return new Decimal(0); }
  }, [qtyStr]);

  const currencyDigits = getCurrencyDigits(currency);
  const total = qtyDec.gt(0) && priceDec.gt(0) ? toFixedString(priceDec.mul(qtyDec), currencyDigits, 'ROUND_DOWN') : '';

  const feeAdjustedTotal = useMemo(() => {
    const base = d(total);
    if (base.isZero()) return '';
    const fee = base.mul(effectiveFeeRate);
    const adjusted = side === 'BUY' ? base.add(fee) : base.sub(fee);
    return toFixedString(adjusted, currencyDigits, 'ROUND_DOWN');
  }, [total, effectiveFeeRate, side]);

  // display formatting is centralized in numfmt util

  const onSubmitInternal = async (data: Form) => {
    let q = new Decimal('0');
    try { q = new Decimal(data.quantity); } catch {}
    onSubmit(q.toNumber());
    setValue('quantity', '');
  };

  return (
    <form onSubmit={handleSubmit(onSubmitInternal)} className="flex flex-col gap-3">
      {/* Amount */}
      <div>
        <label className="text-xs font-bold text-[#90a4cb] uppercase">Amount{amountUnitLabel ? ` (${amountUnitLabel})` : ''}</label>
        <input
          type="number"
          step="0.0001"
          className={`w-full mt-1 bg-[#182234] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all border ${errors.quantity ? 'border-red-500' : 'border-[#314368]'}`}
          placeholder="0.00"
          {...register('quantity')}
        />
        {errors.quantity && (
          <p className="mt-1 text-xs text-red-400">{String(errors.quantity.message)}</p>
        )}
      </div>

      {/* Total */}
      <div>
        <label className="text-xs font-bold text-[#90a4cb] uppercase">Total ({currency})</label>
        <input
          type="number"
          className={`w-full mt-1 bg-[#182234] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all border ${errors.quantity ? 'border-red-500' : 'border-[#314368]'}`}
          placeholder="0"
          value={total}
          onChange={(e) => {
            const raw = e.target.value;
            try {
              const t = new Decimal(raw);
              if (priceDec.lte(0)) {
                setValue('quantity', '');
              } else {
                const q = t.div(priceDec).toFixed(8);
                setValue('quantity', q);
              }
            } catch {
              setValue('quantity', '');
            }
          }}
        />
        {total && (
          <div className="mt-2 bg-[#182234]/60 border border-[#314368] rounded-lg px-3 py-2">
            <div className="flex justify-between text-[11px] text-[#90a4cb]">
              <span>
                {side === 'BUY' ? 'Estimated cost incl. fee' : 'Estimated proceeds after fee'} ({(effectiveFeeRate*100).toFixed(2)}%)
              </span>
              <span>{currency}</span>
            </div>
            <div className="mt-1 text-right font-mono text-xl font-bold text-white">
              {feeAdjustedTotal ? formatCurrencyDisplay(feeAdjustedTotal, currency, 'ROUND_DOWN') : ''}
            </div>
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting || priceDec.lte(0)}
        className={`w-full py-3 rounded-lg font-bold text-white mt-2 transition-all hover:brightness-110 active:scale-95 ${side === 'BUY' ? 'bg-profit' : 'bg-loss'} ${priceDec.lte(0) ? 'opacity-60 cursor-not-allowed' : ''}`}
      >
        {submitLabel ?? 'Submit'}
      </button>
    </form>
  );
}
