import { useMemo } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import Decimal from 'decimal.js';

type Side = 'BUY' | 'SELL';

const d = (v: Decimal.Value | undefined | null) => {
  try {
    if (v === undefined || v === null || v === '') return new Decimal(0);
    return new Decimal(v as Decimal.Value);
  } catch {
    return new Decimal(0);
  }
};

const mulToString = (a: Decimal.Value, b: Decimal.Value, fractionDigits = 0) => {
  return d(a).mul(d(b)).toFixed(fractionDigits);
};

const divToString = (a: Decimal.Value, b: Decimal.Value, fractionDigits = 8) => {
  const denom = d(b);
  if (denom.isZero()) return '0';
  return d(a).div(denom).toFixed(fractionDigits);
};

const Schema = z.object({
  quantity: z
    .number({ invalid_type_error: 'Amount must be a number' })
    .positive({ message: 'Amount must be greater than 0' }),
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
    defaultValues: { quantity: 0 },
  });

  const qty = useWatch({ control, name: 'quantity' }) || 0;
  const price = typeof effectivePrice === 'number' ? effectivePrice : 0;
  const total = qty > 0 && price > 0 ? mulToString(price, qty, 0) : '';

  const feeAdjustedTotal = useMemo(() => {
    const base = d(total);
    if (base.isZero()) return '';
    const fee = base.mul(effectiveFeeRate);
    const adjusted = side === 'BUY' ? base.add(fee) : base.sub(fee);
    return adjusted.toFixed(0);
  }, [total, effectiveFeeRate, side]);

  const submit = (data: Form) => {
    onSubmit(data.quantity);
    setValue('quantity', 0);
  };

  return (
    <form onSubmit={handleSubmit(submit)} className="flex flex-col gap-3">
      {/* Amount */}
      <div>
        <label className="text-xs font-bold text-[#90a4cb] uppercase">Amount{amountUnitLabel ? ` (${amountUnitLabel})` : ''}</label>
        <input
          type="number"
          step="0.0001"
          className={`w-full mt-1 bg-[#182234] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all border ${errors.quantity ? 'border-red-500' : 'border-[#314368]'}`}
          placeholder="0.00"
          {...register('quantity', { valueAsNumber: true })}
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
            const val = parseFloat(e.target.value);
            if (isNaN(val) || price <= 0) {
              setValue('quantity', 0);
            } else {
              const q = parseFloat(divToString(val, price, 8));
              setValue('quantity', q);
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
              {feeAdjustedTotal ? Number(feeAdjustedTotal).toLocaleString() : ''}
            </div>
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting || !price}
        className={`w-full py-3 rounded-lg font-bold text-white mt-2 transition-all hover:brightness-110 active:scale-95 ${side === 'BUY' ? 'bg-profit' : 'bg-loss'} ${!price ? 'opacity-60 cursor-not-allowed' : ''}`}
      >
        {submitLabel ?? 'Submit'}
      </button>
    </form>
  );
}
