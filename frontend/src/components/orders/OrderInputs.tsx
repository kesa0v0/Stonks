// no default React import needed

type OrderType = 'MARKET' | 'LIMIT' | 'STOP_LOSS' | 'TAKE_PROFIT' | 'STOP_LIMIT' | 'TRAILING_STOP';

export default function OrderInputs({
  orderType,
  currency,
  price,
  stopPrice,
  trailingGap,
  onPriceChange,
  onStopPriceChange,
  onTrailingGapChange,
}: {
  orderType: OrderType;
  currency: string;
  price: number | '';
  stopPrice: number | '';
  trailingGap: number | '';
  onPriceChange: (v: string) => void;
  onStopPriceChange: (v: string) => void;
  onTrailingGapChange: (v: string) => void;
}) {
  return (
    <>
      {(orderType === 'LIMIT' || orderType === 'STOP_LIMIT') && (
        <div>
          <label className="text-xs font-bold text-[#90a4cb] uppercase flex justify-between">
            <span>Limit Price ({currency})</span>
          </label>
          <input
            type="number"
            className="w-full mt-1 bg-[#182234] border border-[#314368] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all"
            value={price}
            onChange={(e) => onPriceChange(e.target.value)}
            placeholder="Price"
          />
        </div>
      )}

      {(orderType === 'STOP_LOSS' || orderType === 'TAKE_PROFIT' || orderType === 'STOP_LIMIT') && (
        <div>
          <label className="text-xs font-bold text-[#90a4cb] uppercase flex justify-between">
            <span>Stop Price ({currency})</span>
          </label>
          <input
            type="number"
            className="w-full mt-1 bg-[#182234] border border-[#314368] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all"
            value={stopPrice}
            onChange={(e) => onStopPriceChange(e.target.value)}
            placeholder="Trigger Price"
          />
        </div>
      )}

      {orderType === 'TRAILING_STOP' && (
        <div>
          <label className="text-xs font-bold text-[#90a4cb] uppercase flex justify-between">
            <span>Trailing Gap ({currency})</span>
          </label>
          <input
            type="number"
            className="w-full mt-1 bg-[#182234] border border-[#314368] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all"
            value={trailingGap}
            onChange={(e) => onTrailingGapChange(e.target.value)}
            placeholder="Gap Amount"
          />
        </div>
      )}
    </>
  );
}
