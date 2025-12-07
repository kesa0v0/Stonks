import { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import api from '../api/client';
import DashboardLayout from '../components/DashboardLayout';
import Skeleton from '../components/Skeleton';
import Avatar from '../components/Avatar';
import { CandleChart } from '../components/CandleChart';
import { toFixedString, REPORT_ROUNDING, formatWithThousands } from '../utils/numfmt';
import Decimal from 'decimal.js';
import ConfirmationModal from '../components/ConfirmationModal'; // Added import

const DEFAULT_PROPOSAL_END = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 16); // one day later

type MeProfile = { id: string; nickname: string; is_active: boolean; is_bankrupt?: boolean; is_listed?: boolean }; // Added is_listed
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
    date: string;
    source_pnl: string;
    paid_amount: string;
    ticker_id: string;
};

type IssuerDividendStats = {
    current_dividend_rate: string;
    cumulative_paid_amount: string;
};

type HumanCorporateValueResponse = {
    current_price?: string;
    market_cap?: string;
    per?: string;
};

type VoteProposalStatus = 'PENDING' | 'PASSED' | 'REJECTED' | 'CANCELLED';
type VoteProposal = {
    id: string;
    ticker_id: string;
    title: string;
    description?: string;
    vote_type: string;
    target_value?: string;
    start_at: string;
    end_at: string;
    status: VoteProposalStatus;
    tally: { yes: string; no: string };
    my_vote?: { proposal_id: string; user_id: string; choice: boolean; quantity: string } | null;
};

export default function HumanETF() {
  const [profile, setProfile] = useState<MeProfile | null>(null);
  const [isListed, setIsListed] = useState<boolean | null>(null); // null = loading

  useEffect(() => {
    const checkStatus = async () => {
      try {
        // Fetch profile first to check is_listed status
        const meData = await api.get('auth/login/me').json<MeProfile>();
        setProfile(meData);
        
        if (meData.is_listed) {
            setIsListed(true);
            // Then fetch corporate value if listed
            // api.get('human/corporate_value').json()... (handled in ListedDashboard)
        } else {
            setIsListed(false);
        }
      } catch (err) {
        console.error(err);
        setIsListed(false); 
      }
    };
    checkStatus();
  }, []);

  const handleIpoSuccess = () => {
      setIsListed(true);
      window.location.reload();
  };

  if (isListed === null) {
      return (
        <DashboardLayout>
            <div className="p-8 flex justify-center">
                <Skeleton className="w-full max-w-4xl h-96 rounded-xl" />
            </div>
        </DashboardLayout>
      );
  }

  return (
    <DashboardLayout>
        {isListed ? (
            <ListedDashboard profile={profile} setProfile={setProfile} />
        ) : (
            <NotListedView profile={profile} onSuccess={handleIpoSuccess} />
        )}
    </DashboardLayout>
  );
}

function NotListedView({ profile, onSuccess }: { profile: MeProfile | null, onSuccess: () => void }) {
    const [quantity, setQuantity] = useState<string>('1000');
    const [dividendRate, setDividendRate] = useState<number>(10); // %
    const [isLoading, setIsLoading] = useState(false);
    const [showIpoConfirmation, setShowIpoConfirmation] = useState(false); // State for modal visibility

    const handleIpoConfirmation = () => {
      setShowIpoConfirmation(true);
    };

    const confirmIpo = async () => {
        setShowIpoConfirmation(false); // Close modal
        setIsLoading(true);
        try {
            await api.post('human/ipo', {
                json: {
                    quantity: new Decimal(quantity).toNumber(), // API likely expects number
                    dividend_rate: dividendRate / 100
                }
            });
            toast.success("IPO Successful! You are now listed.");
            onSuccess();
        } catch (err: unknown) {
            console.error("IPO Failed", err);
              type ErrWithResponse = { response?: Response };
              const resp = (err as ErrWithResponse).response;
              if (resp) {
                  const errorData = await resp.json().catch(() => ({} as Record<string, string>));
                  toast.error(`IPO Failed: ${errorData.detail || 'Unknown error'}`);
              } else {
                  toast.error("IPO Failed");
              }
        } finally {
            setIsLoading(false);
        }
    };

    const cancelIpo = () => {
      setShowIpoConfirmation(false); // Close modal
    };

    return (
        <>
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center p-4">
                <div className="max-w-2xl space-y-4">
                                    <div className="w-24 h-24 mx-auto rounded-full border-4 border-gray-600 opacity-50 grayscale overflow-hidden">
                                        <Avatar seed={profile?.nickname} size={96} alt={profile?.nickname || 'avatar'} className="w-full h-full" />
                                    </div>
                    <h1 className="text-white text-4xl font-bold">You are Private</h1>
                    <p className="text-[#90a4cb] text-lg">
                        Your value is hidden from the world. Launch your IPO (Initial Public Offering) to trade yourself as an ETF.
                    </p>
                </div>

                <div className="w-full max-w-md bg-[#101623] border border-[#314368] rounded-xl p-8 flex flex-col gap-6">
                    <h2 className="text-white text-xl font-bold border-b border-[#314368] pb-4">IPO Application</h2>
                    
                    <div className="space-y-4 text-left">
                        <div>
                            <label className="text-[#90a4cb] text-sm block mb-1">Issuance Quantity</label>
                            <input 
                                type="number" 
                                value={quantity}
                                onChange={e => setQuantity(e.target.value)}
                                className="w-full bg-[#182234] text-white border border-[#314368] rounded-lg px-4 py-2 focus:ring-1 focus:ring-[#0d59f2]"
                            />
                            <p className="text-xs text-[#90a4cb] mt-1">Initial shares to be issued to your wallet.</p>
                        </div>

                        <div>
                                                    <label className="text-[#90a4cb] text-sm block mb-1">Initial Dividend Rate: <span className="text-white font-bold">{dividendRate}%</span></label>
                                                    <input 
                                                        type="range" 
                                                        min="10" max="80" step="1"
                                                        value={dividendRate}
                                                        onChange={e => setDividendRate(parseInt(e.target.value))}
                                                        className="w-full h-2 bg-[#222f49] rounded-lg appearance-none cursor-pointer accent-[#0d59f2]"
                                                    />                            <p className="text-xs text-[#90a4cb] mt-1">Percentage of your future PnL distributed to shareholders (Min 10%).</p>
                        </div>

                        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                            <div className="flex justify-between items-center text-sm">
                                <span className="text-red-400 font-bold">Listing Fee</span>
                                <span className="text-white font-mono font-bold">10,000,000 KRW</span>
                            </div>
                        </div>
                    </div>

                    <button 
                        onClick={handleIpoConfirmation}
                        disabled={isLoading}
                        className="w-full py-3 rounded-lg bg-[#0d59f2] hover:bg-[#0d59f2]/90 text-white font-bold text-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {isLoading ? 'Processing...' : 'Launch IPO'}
                    </button>
                </div>
            </div>
            <ConfirmationModal
                isOpen={showIpoConfirmation}
                onClose={cancelIpo}
                onConfirm={confirmIpo}
                title="Confirm IPO"
                message={`Are you sure you want to IPO? \n\nListing Fee: 10,000,000 KRW will be deducted.\nInitial Dividend Rate: ${dividendRate}%`}
            />
        </>
    );
}

function ListedDashboard({ profile, setProfile }: { profile: MeProfile | null, setProfile: React.Dispatch<React.SetStateAction<MeProfile | null>> }) {
  const [shareholdersData, setShareholdersData] = useState<ShareholderResponse | null>(null);
  const [dividendStats, setDividendStats] = useState<IssuerDividendStats | null>(null);
  const [dividendHistory, setDividendHistory] = useState<DividendPaymentEntry[] | null>(null);
  const [corporateValueData, setCorporateValueData] = useState<HumanCorporateValueResponse | null>(null);
  const [sliderValue, setSliderValue] = useState<number>(10); // Local state for slider
    const [proposals, setProposals] = useState<VoteProposal[] | null>(null);
    const [lockedStake, setLockedStake] = useState<Decimal>(new Decimal(0));
    const [nowTs, setNowTs] = useState<number>(() => Date.now());
    const [newProposal, setNewProposal] = useState({
        title: '',
        description: '',
        voteType: 'DIVIDEND_CHANGE',
        targetValue: '',
        endAt: DEFAULT_PROPOSAL_END,
    });
  
  // My Human ETF ticker ID, derived from user ID
  const myHumanTickerId = profile ? `HUMAN-${profile.id}` : undefined;

    const refreshProposals = useCallback(async () => {
        if (!myHumanTickerId) return;
        const listRes = await api.get('votes/proposals', { searchParams: { ticker_id: myHumanTickerId } }).json<{ items: Omit<VoteProposal, 'tally' | 'my_vote'>[] }>();
        const detailed = await Promise.all(listRes.items.map(async (p) => api.get(`votes/proposals/${p.id}`).json<VoteProposal>()));
        setProposals(detailed);
        const locked = detailed.filter(p => p.status === 'PENDING' && p.my_vote).reduce((sum, p) => sum.plus(new Decimal(p.my_vote!.quantity)), new Decimal(0));
        setLockedStake(locked);
    }, [myHumanTickerId]);

  useEffect(() => {
        const timer = setInterval(() => setNowTs(Date.now()), 30000);
        return () => clearInterval(timer);
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
            setSliderValue(new Decimal(data.current_dividend_rate).times(100).toNumber());
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
    const fetchCorporateValue = async () => {
        if (!myHumanTickerId) return; 
        try {
            const data = await api.get('human/corporate_value').json<HumanCorporateValueResponse>();
            setCorporateValueData(data);
        } catch (err) {
            console.error("Failed to fetch corporate value", err);
        }
    };

        (async () => {
                await fetchShareholders();
                await fetchDividendStats();
                await fetchDividendHistory();
                await fetchCorporateValue();
            await refreshProposals();
        })();
    }, [myHumanTickerId, refreshProposals]);

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
          setSliderValue(new Decimal(updatedDividendStats.current_dividend_rate).times(100).toNumber());
          // Re-fetch corporate value as it depends on total issued shares
          const updatedCorporateValue = await api.get('human/corporate_value').json<HumanCorporateValueResponse>();
          setCorporateValueData(updatedCorporateValue);
      }
    } catch (err) {
      console.error("Action failed", err);
      toast.error("Action Failed");
    }
  };

  const isLoading = !profile;
  const isDividendDataLoading = !dividendStats || !dividendHistory;
  const isCorporateValueLoading = !corporateValueData;

  // Calculate ownership for chart
  const myQty = shareholdersData ? new Decimal(shareholdersData.my_holdings) : new Decimal(0);
  const totalQty = shareholdersData ? new Decimal(shareholdersData.total_issued) : new Decimal(1);
  const myPct = totalQty.gt(0) ? myQty.div(totalQty).times(100) : new Decimal(0);
  const othersPct = new Decimal(100).minus(myPct);

  const r = 15.9155;
  const myDash = `${myPct.toFixed(1)} ${othersPct.toFixed(1)}`;
  const othersDash = `${othersPct.toFixed(1)} ${myPct.toFixed(1)}`;
  const othersOffset = 25 + othersPct.toNumber(); // CSS dashoffset needs number

  return (
      <div className="flex flex-col gap-8">
        
        {/* Header / Message */}
        <div className="bg-gradient-to-r from-[#101623] to-[#182234] p-6 rounded-xl border border-[#314368] flex flex-col md:flex-row justify-between items-center gap-4">
            <div>
                <h1 className="text-white text-2xl font-bold mb-1">CEO Dashboard</h1>
                <p className="text-[#90a4cb]">Strive for shareholder value. Your success is their dividend.</p>
            </div>
            <div className="flex items-center gap-3">
                <span className={`px-3 py-1 rounded-full text-xs font-bold border ${profile?.is_active ? 'bg-green-500/10 border-green-500/30 text-green-500' : 'bg-gray-500/10 border-gray-500/30 text-gray-500'}`}>
                    {profile?.is_active ? 'LISTED' : 'INACTIVE'}
                </span>
                {profile?.is_bankrupt && (
                    <span className="px-3 py-1 rounded-full text-xs font-bold bg-red-500/10 border border-red-500/30 text-red-500">
                        BANKRUPT
                    </span>
                )}
            </div>
        </div>

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
                            <div className="w-24 h-24 rounded-full border-4 border-[#0d59f2] shadow-[0_0_15px_rgba(13,89,242,0.3)] overflow-hidden">
                                <Avatar seed={profile!.nickname} size={96} alt={profile!.nickname} className="w-full h-full" />
                            </div>
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

        {/* Corporate Value */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Chart */}
            <div className="flex flex-col p-6 border border-[#314368] bg-[#101623] rounded-xl gap-4">
                <h2 className="text-white text-lg font-bold">My ETF Value</h2>
                {myHumanTickerId ? (
                    <div className="h-64 w-full bg-[#101623] rounded-lg overflow-hidden border border-[#314368]/30 relative">
                        <CandleChart 
                            tickerId={myHumanTickerId} 
                            range="1D" 
                            chartType="area" // Area chart for simpler representation
                            currencyCode="KRW" // Assuming Human ETFs are KRW denominated
                        />
                    </div>
                ) : (
                    <div className="h-64 w-full flex items-center justify-center text-[#90a4cb] border border-[#314368] rounded-lg">
                        No active Human ETF.
                    </div>
                )}
            </div>

            {/* Metrics */}
            <div className="flex flex-col p-6 border border-[#314368] bg-[#101623] rounded-xl gap-4">
                <h2 className="text-white text-lg font-bold">Key Metrics</h2>
                {isCorporateValueLoading ? (
                    <div className="space-y-4">
                        <Skeleton className="h-8 w-3/4" />
                        <Skeleton className="h-6 w-1/2" />
                        <Skeleton className="h-8 w-3/4" />
                        <Skeleton className="h-6 w-1/2" />
                    </div>
                ) : (
                    <>
                        <div className="flex flex-col gap-1">
                            <p className="text-[#90a4cb] text-sm">Current Price</p>
                            <p className="text-white text-2xl font-bold">
                                {corporateValueData?.current_price ? formatWithThousands(toFixedString(corporateValueData.current_price, 0, REPORT_ROUNDING)) : '-'} KRW
                            </p>
                        </div>
                        <div className="flex flex-col gap-1">
                            <p className="text-[#90a4cb] text-sm">Market Cap</p>
                            <p className="text-white text-2xl font-bold">
                                {corporateValueData?.market_cap ? formatWithThousands(toFixedString(corporateValueData.market_cap, 0, REPORT_ROUNDING)) : '-'} KRW
                            </p>
                        </div>
                        <div className="flex flex-col gap-1">
                            <p className="text-[#90a4cb] text-sm">P/E Ratio (Season)</p>
                            <p className="text-white text-2xl font-bold">
                                {corporateValueData?.per ? toFixedString(corporateValueData.per, 2, REPORT_ROUNDING) : '-'}x
                            </p>
                        </div>
                    </>
                )}
            </div>
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
                                            <td className="p-4 text-right text-[#90a4cb] font-mono">{formatWithThousands(toFixedString(s.quantity, 0, 'ROUND_DOWN'))}</td>
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
        
        {/* Dividend Dashboard */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Stats Card */}
            <div className="flex flex-col p-6 border border-[#314368] bg-[#101623] rounded-xl gap-4">
                <h2 className="text-white text-lg font-bold">Dividend Dashboard</h2>
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
                                {toFixedString(new Decimal(dividendStats!.current_dividend_rate).times(100), 0, REPORT_ROUNDING)}%{' '}
                                <span className="text-white text-base">of current profit goes to shareholders.</span>
                            </p>
                        </div>
                        <div className="flex flex-col gap-2">
                            <p className="text-[#90a4cb]">Cumulative Dividends Paid:</p>
                            <p className="text-white text-2xl font-bold">
                                {formatWithThousands(toFixedString(dividendStats!.cumulative_paid_amount, 0, REPORT_ROUNDING))} KRW
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
                                                -{formatWithThousands(toFixedString(entry.paid_amount, 0, 'ROUND_DOWN'))} KRW
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
                    {dividendStats ? new Decimal(dividendStats.current_dividend_rate).times(100).toFixed(0) : '-'}
                </span>
                {profile?.is_bankrupt && <span className="text-xs text-red-500 font-bold border border-red-500 px-2 py-0.5 rounded">Bankrupt Min: 50%</span>}
            </div>
          </div>
          
          <div className="flex flex-col gap-2">
             <input 
                type="range" 
                min={profile?.is_bankrupt ? "50" : "10"} 
                max="80" 
                step="1"
                value={sliderValue}
                onChange={(e) => setSliderValue(parseInt(e.target.value))}
                className="w-full h-2 bg-[#222f49] rounded-lg appearance-none cursor-pointer accent-[#0d59f2]"
             />
             <div className="flex justify-between text-xs text-[#90a4cb]">
                <span>{profile?.is_bankrupt ? "50%" : "10%"}</span>
                <span>80%</span>
             </div>
             <div className="text-center text-white font-bold text-sm">
                Target: {sliderValue}%
             </div>
          </div>

          <div className="flex justify-end">
             <button
                onClick={async () => {
                    if (!dividendStats) return;
                    try {
                        const rate = new Decimal(sliderValue).div(100).toFixed(2);
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

        {/* Shareholder Voting */}
        <div className="flex flex-col gap-4 p-6 border border-[#314368] bg-[#101623] rounded-xl">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-white text-lg font-bold">Shareholder Voting</h2>
                    <p className="text-xs text-[#90a4cb]">Stake shares to vote; staked shares are locked until proposal ends.</p>
                </div>
                <div className="text-right text-xs text-[#90a4cb]">
                    <div>My holdings: <span className="text-white font-mono">{formatWithThousands(toFixedString(myQty, 0, REPORT_ROUNDING))}</span></div>
                    <div>Locked (voting): <span className="text-white font-mono">{formatWithThousands(toFixedString(lockedStake, 0, REPORT_ROUNDING))}</span></div>
                    <div>Free to stake: <span className="text-white font-mono">{formatWithThousands(toFixedString(Decimal.max(myQty.minus(lockedStake), 0), 0, REPORT_ROUNDING))}</span></div>
                </div>
            </div>

            {/* Create Proposal */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-3 bg-[#0c1423] border border-[#1f2b44] rounded-lg p-3">
                <input
                    value={newProposal.title}
                    onChange={(e) => setNewProposal(prev => ({ ...prev, title: e.target.value }))}
                    placeholder="Title"
                    className="lg:col-span-1 bg-[#182234] border border-[#314368] rounded px-3 py-2 text-white text-sm"
                />
                <input
                    value={newProposal.description}
                    onChange={(e) => setNewProposal(prev => ({ ...prev, description: e.target.value }))}
                    placeholder="Description"
                    className="lg:col-span-1 bg-[#182234] border border-[#314368] rounded px-3 py-2 text-white text-sm"
                />
                <select
                    value={newProposal.voteType}
                    onChange={(e) => setNewProposal(prev => ({ ...prev, voteType: e.target.value }))}
                    className="bg-[#182234] border border-[#314368] rounded px-3 py-2 text-white text-sm"
                >
                    <option value="DIVIDEND_CHANGE">Dividend Change</option>
                    <option value="FORCED_DELISTING">Forced Delisting</option>
                    <option value="IMPEACHMENT">Impeachment</option>
                </select>
                <input
                    value={newProposal.targetValue}
                    onChange={(e) => setNewProposal(prev => ({ ...prev, targetValue: e.target.value }))}
                    placeholder="Target value (e.g., 0.7)"
                    className="bg-[#182234] border border-[#314368] rounded px-3 py-2 text-white text-sm"
                />
                <input
                    type="datetime-local"
                    value={newProposal.endAt}
                    onChange={(e) => setNewProposal(prev => ({ ...prev, endAt: e.target.value }))}
                    className="bg-[#182234] border border-[#314368] rounded px-3 py-2 text-white text-sm"
                />
                <div className="lg:col-span-5 flex justify-end">
                    <button
                        onClick={async () => {
                            if (!myHumanTickerId) return;
                            if (!newProposal.title.trim()) {
                                toast.error('Title is required');
                                return;
                            }
                            if (!newProposal.endAt) {
                                toast.error('End time is required');
                                return;
                            }
                            try {
                                await api.post('votes/proposals', {
                                    json: {
                                        ticker_id: myHumanTickerId,
                                        title: newProposal.title,
                                        description: newProposal.description || undefined,
                                        vote_type: newProposal.voteType,
                                        target_value: newProposal.targetValue || undefined,
                                        end_at: new Date(newProposal.endAt).toISOString(),
                                    },
                                });
                                toast.success('Proposal created');
                                await refreshProposals();
                                setNewProposal({
                                    title: '',
                                    description: '',
                                    voteType: 'DIVIDEND_CHANGE',
                                    targetValue: '',
                                    endAt: DEFAULT_PROPOSAL_END,
                                });
                            } catch (err) {
                                console.error('Create proposal failed', err);
                                toast.error('Create proposal failed');
                            }
                        }}
                        className="px-4 py-2 bg-[#0d59f2] text-white text-sm font-bold rounded hover:bg-[#0b4bcc]"
                    >
                        Create Proposal
                    </button>
                </div>
            </div>

            {!proposals ? (
                <Skeleton className="h-24 w-full" />
            ) : proposals.length === 0 ? (
                <div className="text-[#90a4cb] text-sm">No proposals yet.</div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-[#182234] text-[#90a4cb]">
                            <tr>
                                <th className="p-3">Title</th>
                                <th className="p-3">Status</th>
                                <th className="p-3">Ends</th>
                                <th className="p-3 text-right">Yes / No</th>
                                <th className="p-3 text-right">My Vote</th>
                                <th className="p-3 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-[#314368]">
                            {proposals.map((p) => {
                                const myVoteQty = p.my_vote ? new Decimal(p.my_vote.quantity) : new Decimal(0);
                                const yes = new Decimal(p.tally.yes || '0');
                                const no = new Decimal(p.tally.no || '0');
                                const isOpen = p.status === 'PENDING' && new Date(p.end_at).getTime() >= nowTs;

                                const handleVoteClick = async (choice: boolean) => {
                                    const defaultQty = Decimal.max(myQty.minus(lockedStake).plus(myVoteQty), 0);
                                    const input = prompt(`Enter shares to stake (${choice ? 'YES' : 'NO'}). Available: ${defaultQty.toFixed(0)}`, defaultQty.toFixed(0));
                                    if (!input) return;
                                    
                                    try {
                                        const qty = new Decimal(input);
                                        if (qty.lte(0)) {
                                            toast.error('Invalid quantity');
                                            return;
                                        }
                                        await api.post(`votes/proposals/${p.id}/vote`, { json: { choice, quantity: qty.toNumber() } });
                                        toast.success('Vote submitted');
                                        // refresh proposals and holdings
                                        await refreshProposals();
                                        const updatedShareholders = await api.get('human/shareholders').json<ShareholderResponse>();
                                        setShareholdersData(updatedShareholders);
                                    } catch (err) {
                                        console.error('Vote failed', err);
                                        toast.error('Vote failed (Invalid Input?)');
                                    }
                                };

                                const handleUnvote = async () => {
                                    try {
                                        await api.post(`votes/proposals/${p.id}/unvote`);
                                        toast.success('Vote removed');
                                        await refreshProposals();
                                        const updatedShareholders = await api.get('human/shareholders').json<ShareholderResponse>();
                                        setShareholdersData(updatedShareholders);
                                    } catch (err) {
                                        console.error('Unvote failed', err);
                                        toast.error('Unvote failed');
                                    }
                                };

                                const handleSettle = async () => {
                                    try {
                                        await api.post(`votes/proposals/${p.id}/settle`);
                                        toast.success('Proposal settled');
                                        await refreshProposals();
                                        // Refresh stats as settle might have changed dividend rate
                                        const updatedDividendStats = await api.get('human/dividend/stats').json<IssuerDividendStats>();
                                        setDividendStats(updatedDividendStats);
                                    } catch (err) {
                                        console.error('Settle failed', err);
                                        toast.error('Failed to settle');
                                    }
                                };

                                return (
                                    <tr key={p.id} className="hover:bg-[#182234]">
                                        <td className="p-3 text-white">
                                            <div className="font-semibold">{p.title}</div>
                                            {p.description && <div className="text-xs text-[#90a4cb]">{p.description}</div>}
                                        </td>
                                        <td className="p-3 text-xs text-[#90a4cb]">{p.status}</td>
                                        <td className="p-3 text-xs text-[#90a4cb]">{new Date(p.end_at).toLocaleString()}</td>
                                        <td className="p-3 text-right text-white font-mono">{formatWithThousands(yes.toFixed(0))} / {formatWithThousands(no.toFixed(0))}</td>
                                        <td className="p-3 text-right text-white font-mono">{myVoteQty.gt(0) ? `${myVoteQty.toFixed(0)} (${p.my_vote?.choice ? 'YES' : 'NO'})` : '-'}</td>
                                        <td className="p-3 text-right">
                                            {isOpen ? (
                                                <div className="flex gap-2 justify-end">
                                                    <button onClick={() => handleVoteClick(true)} className="px-3 py-1 text-xs rounded bg-[#0d59f2] text-white hover:bg-[#0b4bcc]">Vote Yes</button>
                                                    <button onClick={() => handleVoteClick(false)} className="px-3 py-1 text-xs rounded bg-[#ef4444] text-white hover:bg-[#dc2626]">Vote No</button>
                                                    {myVoteQty.gt(0) && <button onClick={handleUnvote} className="px-3 py-1 text-xs rounded border border-[#314368] text-[#90a4cb] hover:bg-[#182234]">Unvote</button>}
                                                </div>
                                            ) : p.status === 'PENDING' ? (
                                                <button onClick={handleSettle} className="px-3 py-1 text-xs rounded bg-yellow-600 text-white hover:bg-yellow-500">Settle</button>
                                            ) : (
                                                <span className="text-xs text-[#90a4cb]">Closed</span>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
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
  );
}
