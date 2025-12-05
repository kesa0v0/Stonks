import { useNavigate } from 'react-router-dom';
import Decimal from 'decimal.js';
import { toFixedString, formatWithThousands, REPORT_ROUNDING } from '../utils/numfmt';
import type { Asset } from '../interfaces';
import { usePrice } from '../store/prices';

interface HoldingsTableProps {
  assets: Asset[];
  isLoading?: boolean;
}

export default function HoldingsTable({ assets, isLoading }: HoldingsTableProps) {
  // navigation handled in row component

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 rounded-xl border border-[#314368] bg-[#101623] p-6">
        <div className="h-6 w-48 bg-[#182234] rounded animate-pulse mb-4" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 w-full bg-[#182234] rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!assets || assets.length === 0) {
    return (
      <div className="flex flex-col gap-4 rounded-xl border border-[#314368] bg-[#101623] p-6">
        <h2 className="text-white text-xl font-bold">Current Positions</h2>
        <div className="flex flex-col items-center justify-center py-8 text-[#90a4cb]">
          <span className="material-symbols-outlined text-4xl mb-2">savings</span>
          <p>No active positions found.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-[#314368] bg-[#101623] overflow-hidden">
      <div className="p-6 pb-2">
        <h2 className="text-white text-xl font-bold">Current Positions</h2>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="bg-[#182234]">
            <tr>
              <th className="px-4 py-3 text-[#90a4cb] text-sm font-medium">Asset</th>
              <th className="px-4 py-3 text-[#90a4cb] text-sm font-medium text-right">Quantity</th>
              <th className="px-4 py-3 text-[#90a4cb] text-sm font-medium text-right">Avg. Price</th>
              <th className="px-4 py-3 text-[#90a4cb] text-sm font-medium text-right">Current Price</th>
              <th className="px-4 py-3 text-[#90a4cb] text-sm font-medium text-right">Total Value</th>
              <th className="px-4 py-3 text-[#90a4cb] text-sm font-medium text-right">PnL</th>
              <th className="px-4 py-3 text-[#90a4cb] text-sm font-medium text-center">Trade</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#314368]">
            {assets.map((asset) => (
              <HoldingRow key={asset.ticker_id} asset={asset} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HoldingRow({ asset }: { asset: Asset }) {
  const navigate = useNavigate();
  // Hooks must be at top-level in a component
  // Subscribe to just this asset's price for fine-grained re-renders
  const rtPrice = usePrice(asset.ticker_id);

  const quantity = new Decimal(asset.quantity);
  const avgPrice = new Decimal(asset.average_price);
  const currentPrice = new Decimal(rtPrice ?? asset.current_price);
  const totalValue = currentPrice.mul(quantity);
  const pnlValue = totalValue.sub(avgPrice.mul(quantity));
  const isPositive = pnlValue.greaterThanOrEqualTo(0);
  const pnlColor = isPositive ? 'text-profit' : 'text-loss';
  const profitRate = (() => {
    const costBasis = avgPrice.mul(quantity);
    if (costBasis.isZero()) return new Decimal(0);
    return totalValue.sub(costBasis).div(costBasis.abs()).mul(100);
  })();

  return (
    <tr className="hover:bg-[#182234] transition-colors">
      <td className="px-4 py-3">
        <div className="flex flex-col">
          <span className="text-white font-bold">{asset.symbol}</span>
          <span className="text-[#90a4cb] text-xs">{asset.name}</span>
        </div>
      </td>
      <td className="px-4 py-3 text-right text-white font-mono">
        {toFixedString(quantity, 4, 'ROUND_DOWN')}
      </td>
      <td className="px-4 py-3 text-right text-[#90a4cb] font-mono">
        {formatWithThousands(toFixedString(avgPrice, 0, 'ROUND_DOWN'))}
      </td>
      <td className="px-4 py-3 text-right text-white font-mono font-medium">
        {formatWithThousands(toFixedString(currentPrice, 0, 'ROUND_DOWN'))}
      </td>
      <td className="px-4 py-3 text-right text-white font-bold font-mono">
        {formatWithThousands(toFixedString(totalValue, 0, 'ROUND_DOWN'))}
      </td>
      <td className={`px-4 py-3 text-right font-mono font-medium ${pnlColor}`}>
        <div className="flex flex-col items-end">
          <span>{isPositive ? '+' : ''}{formatWithThousands(toFixedString(pnlValue, 0, 'ROUND_DOWN'))}</span>
          <span className="text-xs">({isPositive ? '+' : ''}{toFixedString(profitRate, 2, REPORT_ROUNDING)}%)</span>
        </div>
      </td>
      <td className="px-4 py-3 text-center">
        <button onClick={() => navigate(`/market/${asset.ticker_id}`)} className="h-8 px-4 rounded-md bg-primary text-background-dark font-semibold text-sm hover:bg-primary/90">Trade</button>
      </td>
    </tr>
  );
}