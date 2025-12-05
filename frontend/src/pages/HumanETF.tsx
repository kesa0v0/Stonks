import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../api/client';
import DashboardLayout from '../components/DashboardLayout';
import Skeleton from '../components/Skeleton';
import { toFixedString, REPORT_ROUNDING, formatWithThousands } from '../utils/numfmt';

type MeProfile = { nickname: string; is_active: boolean; is_bankrupt?: boolean };
type SimpleMessage = { message?: string };

type Shareholder = {
    rank: number;
    nickname: string;
    quantity: string;
    percentage: number;
};

type ShareholderResponse = {
    total_issued: string;
    my_holdings: string;
    shareholders: Shareholder[];
};

type DividendPaymentEntry = {
    date: string; // Use string for ISO format date
    source_pnl: string;
    paid_amount: string;
    ticker_id: string;
};

type IssuerDividendStats = {
    current_dividend_rate: string; // e.g., "0.50"
    cumulative_paid_amount: string;
};

export default function HumanETF() {
  const [profile, setProfile] = useState<MeProfile | null>(null);
  const [shareholdersData, setShareholdersData] = useState<ShareholderResponse | null>(null);
  const [dividendStats, setDividendStats] = useState<IssuerDividendStats | null>(null);
  const [dividendHistory, setDividendHistory] = useState<DividendPaymentEntry[] | null>(null);
  const [sliderValue, setSliderValue] = useState<number>(10); // Local state for slider
  
  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const data = await api.get('auth/login/me').json<MeProfile>();
        setProfile(data);
      } catch (err) {
        console.error(err);
      }
    };
    fetchProfile();
  }, []);

  useEffect(() => {
    const fetchShareholders = async () => {
        try {
            const data = await api.get('human/shareholders').json<ShareholderResponse>();
            setShareholdersData(data);
        } catch (err) {
            console.error("Failed to fetch shareholders", err);
        }
    };
    const fetchDividendStats = async () => {
        try {
            const data = await api.get('human/dividend/stats').json<IssuerDividendStats>();
            setDividendStats(data);
            // Initialize slider with current rate
            setSliderValue(parseFloat(data.current_dividend_rate) * 100);
        } catch (err) {
            console.error("Failed to fetch dividend stats", err);
        }
    };
    const fetchDividendHistory = async () => {
        try {
            const data = await api.get('human/dividend/history').json<DividendPaymentEntry[]>();
            setDividendHistory(data);
        } catch (err) {
            console.error("Failed to fetch dividend history", err);
        }
    };
    
    fetchShareholders();
    fetchDividendStats();
    fetchDividendHistory();
  }, []);

  const handleAction = async (action: 'burn' | 'bailout' | 'bankruptcy') => {
    try {
      let res: SimpleMessage | undefined;
      if (action === 'burn') {
        res = await api.post('human/burn', { json: { quantity: 100 } }).json<SimpleMessage>(); // 예시 수량
      } else if (action === 'bailout') {
        res = await api.post('human/bailout').json<SimpleMessage>();
      } else {
        res = await api.post('me/bankruptcy').json<SimpleMessage>();
      }
      toast.success(res?.message || "Action Successful");
      // Refresh data if burn action
      if (action === 'burn') {
          // Re-fetch shareholder data as burn affects ownership
          const updatedShareholders = await api.get('human/shareholders').json<ShareholderResponse>();
          setShareholdersData(updatedShareholders);
          // Re-fetch dividend stats as it might affect future payouts or trigger calculations
          const updatedDividendStats = await api.get('human/dividend/stats').json<IssuerDividendStats>();
          setDividendStats(updatedDividendStats);
          setSliderValue(parseFloat(updatedDividendStats.current_dividend_rate) * 100);
      }
    } catch (err) {
      console.error("Action failed", err);
      toast.error("Action Failed");
    }
  };

  const isLoading = !profile;
  const isDividendDataLoading = !dividendStats || !dividendHistory;

  // Calculate ownership for chart
  const myQty = shareholdersData ? parseFloat(shareholdersData.my_holdings) : 0;
  const totalQty = shareholdersData ? parseFloat(shareholdersData.total_issued) : 1;
  const myPct = totalQty > 0 ? (myQty / totalQty) * 100 : 0;
  const othersPct = 100 - myPct;

  const r = 15.9155;
  const myDash = `${myPct} ${100 - myPct}`;
  const othersDash = `${othersPct} ${100 - othersPct}`;
  const othersOffset = 25 + 100 - myPct;

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-8">
        
        {/* Profile Card */}
        <div className="flex p-6 border border-[#314368] bg-[#101623] rounded-xl items-center gap-6">
          {isLoading ? (
            <div className="flex items-center gap-6 w-full animate-pulse">
              <Skeleton className="w-24 h-24 rounded-full" />
              <div className="flex-1">
                <Skeleton className="h-6 w-48 mb-2" />
                <Skeleton className="h-4 w-32" />
              </div>
            </div>
          ) : (
            <>
              <div 
                className="w-24 h-24 rounded-full border-4 border-[#0d59f2] bg-cover bg-center shadow-[0_0_15px_rgba(13,89,242,0.3)]"
                style={{ backgroundImage: `url("https://api.dicebear.com/7.x/pixel-art/svg?seed=${profile!.nickname}")` }}
              ></div>
              <div>
                <h1 className="text-white text-3xl font-bold font-mono tracking-tighter">
                  {profile!.nickname} <span className="text-[#0d59f2] text-xl">ETF</span>
                </h1>
                <p className="text-[#90a4cb] mt-1">Status: {profile!.is_active ? 'Active Trader' : 'Inactive'}</p>
                {profile!.is_bankrupt && <span className="inline-block mt-2 px-2 py-1 bg-red-500/20 text-red-500 text-xs font-bold rounded">BANKRUPT</span>}
              </div>
            </>
          )}
        </div>

        {/* Cap Table Section */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Chart */}
            <div className="flex flex-col p-6 border border-[#314368] bg-[#101623] rounded-xl gap-4 items-center justify-center">
                <h2 className="text-white text-lg font-bold self-start">Ownership Structure</h2>
                {shareholdersData ? (
                     <div className="relative w-48 h-48">
                        <svg className="w-full h-full" viewBox="0 0 36 36">
                            <path className="stroke-[#222f49]" d={`M18 2.0845 a ${r} ${r} 0 0 1 0 31.831 a ${r} ${r} 0 0 1 0 -31.831`} fill="none" strokeWidth="3" />
                            <path className="stroke-[#0d59f2]" strokeDasharray={myDash} strokeDashoffset={25} d={`M18 2.0845 a ${r} ${r} 0 0 1 0 31.831 a ${r} ${r} 0 0 1 0 -31.831`} fill="none" strokeWidth="3" />
                            <path className="stroke-[#ef4444]" strokeDasharray={othersDash} strokeDashoffset={othersOffset} d={`M18 2.0845 a ${r} ${r} 0 0 1 0 31.831 a ${r} ${r} 0 0 1 0 -31.831`} fill="none" strokeWidth="3" />
                        </svg>
                        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                            <span className="text-xs text-[#90a4cb]">My Stake</span>
                            <span className="text-xl font-bold text-white">{toFixedString(myPct, 1, REPORT_ROUNDING)}%</span>
                        </div>
                     </div>
                ) : (
                    <Skeleton className="w-48 h-48 rounded-full" />
                )}
                <div className="flex gap-4 text-xs">
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 bg-[#0d59f2] rounded-full"></div>
                        <span className="text-white">Me</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 bg-[#ef4444] rounded-full"></div>
                        <span className="text-white">Shareholders</span>
                    </div>
                </div>
            </div>

            {/* Table */}
            <div className="lg:col-span-2 flex flex-col border border-[#314368] bg-[#101623] rounded-xl overflow-hidden">
                <div className="p-6 border-b border-[#314368]">
                    <h2 className="text-white text-lg font-bold">Shareholder Registry (Cap Table)</h2>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead className="bg-[#182234]">
                            <tr>
                                <th className="p-4 text-xs text-[#90a4cb] font-medium">Rank</th>
                                <th className="p-4 text-xs text-[#90a4cb] font-medium">Shareholder</th>
                                <th className="p-4 text-xs text-[#90a4cb] font-medium text-right">Shares</th>
                                <th className="p-4 text-xs text-[#90a4cb] font-medium text-right">Equity</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-[#314368]">
                            {shareholdersData ? (
                                shareholdersData.shareholders.length > 0 ? (
                                    shareholdersData.shareholders.map((s) => (
                                        <tr key={s.rank} className="hover:bg-[#182234]">
                                            <td className="p-4 text-white font-mono">{s.rank}</td>
                                            <td className="p-4 text-white font-bold">{s.nickname}</td>
                                            <td className="p-4 text-right text-[#90a4cb] font-mono">{formatWithThousands(toFixedString(parseFloat(s.quantity), 0, 'ROUND_DOWN'))}</td>
                                            <td className="p-4 text-right text-white font-mono">{s.percentage}%</td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td colSpan={4} className="p-8 text-center text-[#90a4cb]">
                                            No outside shareholders yet. You own 100%.
                                        </td>
                                    </tr>
                                )
                            ) : (
                                Array.from({length: 3}).map((_, i) => (
                                    <tr key={i}>
                                        <td colSpan={4} className="p-4"><Skeleton className="h-8 w-full" /></td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        {/* Dividend Pain Dashboard */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Stats Card */}
            <div className="flex flex-col p-6 border border-[#314368] bg-[#101623] rounded-xl gap-4">
                <h2 className="text-white text-lg font-bold">Dividend Pain Dashboard</h2>
                {isDividendDataLoading ? (
                    <div className="space-y-4">
                        <Skeleton className="h-8 w-3/4" />
                        <Skeleton className="h-6 w-1/2" />
                    </div>
                ) : (
                    <>
                        <div className="flex flex-col gap-2">
                            <p className="text-[#90a4cb]">Current Dividend Rate:</p>
                            <p className="text-red-500 text-3xl font-bold">
                                {toFixedString(parseFloat(dividendStats!.current_dividend_rate) * 100, 0, REPORT_ROUNDING)}%{' '}
                                <span className="text-white text-base">of current profit goes to shareholders.</span>
                            </p>
                        </div>
                        <div className="flex flex-col gap-2">
                            <p className="text-[#90a4cb]">Cumulative Dividends Paid:</p>
                            <p className="text-white text-2xl font-bold">
                                {formatWithThousands(toFixedString(parseFloat(dividendStats!.cumulative_paid_amount), 0, REPORT_ROUNDING))} KRW
                            </p>
                        </div>
                    </>
                )}
            </div>

            {/* Recent Dividend History */}
            <div className="flex flex-col border border-[#314368] bg-[#101623] rounded-xl overflow-hidden">
                <div className="p-6 border-b border-[#314368]">
                    <h2 className="text-white text-lg font-bold">Recent Dividend History</h2>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead className="bg-[#182234]">
                            <tr>
                                <th className="p-4 text-xs text-[#90a4cb] font-medium">Date</th>
                                <th className="p-4 text-xs text-[#90a4cb] font-medium">Ticker</th>
                                <th className="p-4 text-xs text-[#90a4cb] font-medium text-right">Paid Amount</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-[#314368]">
                            {isDividendDataLoading ? (
                                Array.from({length: 3}).map((_, i) => (
                                    <tr key={i}>
                                        <td colSpan={3} className="p-4"><Skeleton className="h-8 w-full" /></td>
                                    </tr>
                                ))
                            ) : (
                                dividendHistory && dividendHistory.length > 0 ? (
                                    dividendHistory.map((entry, i) => (
                                        <tr key={i} className="hover:bg-[#182234]">
                                            <td className="p-4 text-white font-mono text-sm">{new Date(entry.date).toLocaleDateString()}</td>
                                            <td className="p-4 text-white font-bold text-sm">{entry.ticker_id}</td>
                                            <td className="p-4 text-right text-red-500 font-mono text-sm">
                                                -{formatWithThousands(toFixedString(parseFloat(entry.paid_amount), 0, 'ROUND_DOWN'))} KRW
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td colSpan={3} className="p-8 text-center text-[#90a4cb]">
                                            No dividend payments yet.
                                        </td>
                                    </tr>
                                )
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        {/* Dividend Rate Control */}
        <div className="flex flex-col gap-4 p-6 border border-[#314368] bg-[#101623] rounded-xl">
          <div className="flex justify-between items-center text-white">
            <span className="font-medium text-lg font-bold">Dividend Rate Setting</span>
            <div className="flex items-center gap-2">
                <span className="font-mono font-bold text-[#00FF41] text-xl">
                    {profile ? sliderValue.toFixed(0) : '-'}%
                </span>
                {profile?.is_bankrupt && <span className="text-xs text-red-500 font-bold border border-red-500 px-2 py-0.5 rounded">Bankrupt Min: 50%</span>}
            </div>
          </div>
          
          <div className="flex flex-col gap-2">
             <input 
                type="range" 
                min={profile?.is_bankrupt ? "50" : "10"} 
                max="100" 
                step="1"
                value={sliderValue}
                onChange={(e) => setSliderValue(parseInt(e.target.value))}
                className="w-full h-2 bg-[#222f49] rounded-lg appearance-none cursor-pointer accent-[#0d59f2]"
             />
             <div className="flex justify-between text-xs text-[#90a4cb]">
                <span>{profile?.is_bankrupt ? "50%" : "10%"}</span>
                <span>100%</span>
             </div>
          </div>

          <div className="flex justify-end">
             <button
                onClick={async () => {
                    if (!dividendStats) return;
                    try {
                        const rate = (sliderValue / 100).toFixed(2);
                        await api.patch('human/dividend_rate', { json: { dividend_rate: parseFloat(rate) } });
                        toast.success(`Dividend rate updated to ${sliderValue}%`);
                        
                        // Update both local stats and re-fetch profile to be safe
                        setDividendStats({ ...dividendStats, current_dividend_rate: rate });
                        const data = await api.get('auth/login/me').json<MeProfile>();
                        setProfile(data);
                    } catch (err) {
                        console.error("Failed to update rate", err);
                        toast.error("Update Failed");
                    }
                }}
                className="px-4 py-2 rounded-lg bg-[#0d59f2] text-white font-bold text-sm hover:bg-[#0d59f2]/90 transition-all"
             >
                Save Rate
             </button>
          </div>
        </div>

        {/* Action Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          
          {/* IPO / Burn Section */}
          <div className="flex flex-col justify-between p-6 border border-[#314368] bg-[#101623] rounded-xl gap-4">
            <div>
              <h2 className="text-white text-xl font-bold mb-1">Share Management</h2>
              <p className="text-[#90a4cb] text-sm">Burn your ETF shares to increase value or reduce supply.</p>
            </div>
            <div className="flex justify-end">
              <button 
                onClick={() => handleAction('burn')}
                className="px-6 py-3 rounded-lg bg-[#0d59f2] text-white font-bold hover:bg-[#0d59f2]/90 transition-all"
              >
                Burn 100 Shares
              </button>
            </div>
          </div>

          {/* Bankruptcy Zone */}
          <div className="flex flex-col justify-between p-6 border-2 border-red-500/30 bg-[#101623] rounded-xl gap-4 shadow-[0_0_20px_rgba(239,68,68,0.1)]">
            <div>
              <h2 className="text-white text-xl font-bold mb-1 flex items-center gap-2">
                <span className="material-symbols-outlined text-red-500">warning</span>
                Bankruptcy Protocol
              </h2>
              <p className="text-[#90a4cb] text-sm">Emergency options for distressed accounts.</p>
            </div>
            <div className="flex gap-3 justify-end mt-2">
              <button 
                onClick={() => handleAction('bailout')}
                className="px-4 py-3 rounded-lg bg-[#222f49] text-white font-bold hover:bg-[#314368] transition-all"
              >
                Request Bailout
              </button>
            </div>
          </div>

        </div>
      </div>
    </DashboardLayout>
  );
}