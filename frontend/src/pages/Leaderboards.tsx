import { useState, useEffect } from 'react';
import api from '../api/client';
import Decimal from 'decimal.js';
import { toFixedString, REPORT_ROUNDING, formatWithThousands } from '../utils/numfmt';
import DashboardLayout from '../components/DashboardLayout';
import { SkeletonRow } from '../components/Skeleton';
import Avatar from '../components/Avatar';
import type { RankingEntry, HallOfFameResponse } from '../interfaces';

// API client prefix is configured via VITE_API_BASE_URL

// 탭 정의 (UI 표시 이름 -> API 파라미터 매핑)
const TABS = [
  { label: 'Top PnL', type: 'pnl' },
  { label: 'Top Loss', type: 'loss' },
  { label: 'Top Volume', type: 'volume' },
  { label: 'Profit Factor', type: 'profit_factor' },
  { label: 'Dividends', type: 'dividend' },
];

export default function Leaderboard() {
  // 상태 관리
  const [activeTab, setActiveTab] = useState<string>('pnl');
  const [rankings, setRankings] = useState<RankingEntry[]>([]);
  const [hallOfFame, setHallOfFame] = useState<HallOfFameResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // 1. 명예의 전당 데이터 로드 (최초 1회)
  useEffect(() => {
    const fetchHallOfFame = async () => {
      try {
        const data = await api.get('rankings/hall-of-fame').json<HallOfFameResponse>();
        setHallOfFame(data);
      } catch (err) {
        console.error("Failed to fetch Hall of Fame", err);
      }
    };
    fetchHallOfFame();
  }, []);

  // 2. 랭킹 데이터 로드 (탭 변경 시)
  useEffect(() => {
    const fetchRankings = async () => {
      setLoading(true);
      try {
        const data = await api.get(`rankings/${activeTab}`, { searchParams: { limit: 10 } }).json<RankingEntry[]>();
        setRankings(data);
      } catch (err) {
        console.error(`Failed to fetch rankings for ${activeTab}`, err);
      } finally {
        setLoading(false);
      }
    };
    fetchRankings();
  }, [activeTab]);

  return (
    <DashboardLayout>
      <div className="flex flex-col lg:flex-row gap-8 h-full">
          
          {/* Left: Leaderboard Table Section */}
          <div className="flex-[3] flex flex-col min-w-0">
            {/* Heading */}
            <div className="flex flex-wrap justify-between gap-3 p-4">
              <p className="text-white text-4xl font-black leading-tight tracking-[-0.033em]">
                Competitive Leaderboard
              </p>
            </div>

            {/* Tabs */}
            <div className="pb-3 px-4">
              <div className="flex border-b border-[#314368] gap-8 overflow-x-auto">
                {TABS.map((tab) => (
                  <button
                    key={tab.type}
                    onClick={() => setActiveTab(tab.type)}
                    className={`flex flex-col items-center justify-center border-b-[3px] pb-[13px] pt-4 text-sm font-bold tracking-[0.015em] transition-colors whitespace-nowrap
                      ${activeTab === tab.type 
                        ? 'border-b-[#0d59f2] text-white' 
                        : 'border-b-transparent text-[#90a4cb] hover:text-white hover:border-b-[#0d59f2]/50'
                      }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Ranking Table */}
            <div className="px-4 py-3">
              <div className="flex flex-col overflow-hidden rounded-lg border border-[#314368] bg-[#101623]">
                <table className="w-full">
                  <thead>
                    <tr className="bg-[#182234]">
                      <th className="px-6 py-3 text-left text-white w-24 text-sm font-medium">Rank</th>
                      <th className="px-6 py-3 text-left text-white text-sm font-medium">User Profile</th>
                      <th className="px-6 py-3 text-right text-white text-sm font-medium">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      Array.from({ length: 10 }).map((_, i) => <SkeletonRow key={i} cols={3} />)
                    ) : rankings.length === 0 ? (
                      <tr><td colSpan={3} className="text-center py-8 text-[#90a4cb]">No Data Available</td></tr>
                    ) : (
                      rankings.map((user) => (
                        <tr key={user.rank} className="border-t border-t-[#314368] hover:bg-[#182234] transition-colors">
                          <td className="h-[72px] px-6 py-2 text-[#90a4cb] text-sm font-normal">
                            <div className="flex items-center gap-2">
                              {getRankIcon(user.rank)}
                              <span className={user.rank <= 3 ? "font-bold text-white" : ""}>{user.rank}</span>
                            </div>
                          </td>
                          <td className="h-[72px] px-6 py-2">
                            <div className="flex items-center gap-3">
                              <Avatar
                                seed={user.nickname}
                                size={40}
                                alt={user.nickname}
                                className="border border-[#314368]"
                              />
                              <span className="text-white text-sm font-medium">{user.nickname}</span>
                            </div>
                          </td>
                          <td className={`h-[72px] px-6 py-2 text-right text-sm font-bold ${getValueColor(activeTab, user.value)}`}>
                            {formatValue(activeTab, user.value)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Right: Hall of Fame Section */}
          <div className="flex-[1] flex flex-col bg-[#182234]/50 border border-[#314368] rounded-lg p-6 min-w-[320px] h-fit">
            <h2 className="text-white text-[22px] font-bold leading-tight pb-5 border-b border-[#314368] mb-5">
              Hall of Fame <span className="text-xs font-normal text-[#90a4cb] block mt-1">Current Season Leaders</span>
            </h2>
            
            <div className="grid grid-cols-2 gap-6">
              <BadgeCard 
                title="Profit King" 
                user={hallOfFame?.top_profit} 
                desc="Highest Realized PnL"
                color="text-red-500"
              />
              <BadgeCard 
                title="Rekt Master" 
                user={hallOfFame?.top_loss} 
                desc="Highest Total Loss"
                color="text-blue-500"
              />
              <BadgeCard 
                title="Volume King" 
                user={hallOfFame?.top_volume} 
                desc="Most Trades Executed"
                color="text-blue-400"
              />
              <BadgeCard 
                title="Sniper" 
                user={hallOfFame?.top_win_rate} 
                desc="Highest Win Rate"
                color="text-yellow-400"
              />
              <BadgeCard 
                title="Donor" 
                user={hallOfFame?.top_fees} 
                desc="Most Fees Paid"
                color="text-purple-400"
              />
              <BadgeCard 
                title="Dividend King" 
                user={hallOfFame?.top_dividend} 
                desc="Most Dividends Paid"
                color="text-green-400"
              />
            </div>
          </div>

      </div>
    </DashboardLayout>
  );
}

// --- Sub Components & Helpers ---

// removed local NavItem; use DashboardLayout navigation

const BadgeCard = ({ title, user, desc, color }: { title: string, user?: RankingEntry, desc: string, color: string }) => (
  <div className="relative group flex flex-col items-center text-center gap-2 p-3 rounded-lg hover:bg-[#222f49] transition-all">
    <div className={`w-16 h-16 rounded-full bg-[#101623] flex items-center justify-center border border-[#314368] ${user ? 'group-hover:border-white/50' : 'opacity-50'}`}>
      {user ? (
        <Avatar seed={user.nickname} size={64} alt={user.nickname} />
      ) : (
        <span className={`material-symbols-outlined text-3xl text-gray-600`}>lock</span>
      )}
    </div>
    
    <div>
      <p className={`text-sm font-bold ${color}`}>{title}</p>
      <p className="text-xs text-white mt-1 truncate max-w-[100px] mx-auto">
        {user ? user.nickname : '-'}
      </p>
    </div>

    {/* Tooltip */}
    <div className="absolute bottom-full mb-2 w-max max-w-xs p-2 text-xs text-white bg-black/90 rounded-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
      <p className="font-bold">{desc}</p>
      {user && <p className="text-gray-300 mt-1">Value: {formatWithThousands(toFixedString(user.value, 0, 'ROUND_DOWN'))}</p>}
    </div>
  </div>
);

// 헬퍼 함수들
function getRankIcon(rank: number) {
  if (rank === 1) return <span className="material-symbols-outlined text-[#FFD700]" style={{ textShadow: "0 0 5px #FFD700" }}>emoji_events</span>;
  if (rank === 2) return <span className="material-symbols-outlined text-[#C0C0C0]" style={{ textShadow: "0 0 5px #C0C0C0" }}>emoji_events</span>;
  if (rank === 3) return <span className="material-symbols-outlined text-[#CD7F32]" style={{ textShadow: "0 0 5px #CD7F32" }}>emoji_events</span>;
  return null;
}

function getValueColor(type: string, value: string) {
  // 사이트 전역 규칙: +는 빨강(text-profit), -는 파랑(text-loss)
  if (type === 'loss') return 'text-loss';
  if (type === 'dividend') return 'text-green-400'; // Green for dividends
  
  const num = Number(value); // Safe for basic sign check, though Decimal is better
  if (type === 'pnl') return num >= 0 ? 'text-profit' : 'text-loss';
  return 'text-white';
}

function formatValue(type: string, value: string) {
  // value is DecimalStr (string)
  const dec = new Decimal(value);
  
  if (type === 'pnl' || type === 'loss' || type === 'dividend') return `${formatWithThousands(toFixedString(dec, 0, 'ROUND_DOWN'))} KRW`;
  if (type === 'volume' || type === 'night') return `${formatWithThousands(toFixedString(dec, 0, 'ROUND_DOWN'))} 회`;
  if (type === 'win_rate' || type === 'market_ratio') return `${toFixedString(dec, 2, REPORT_ROUNDING)} %`;
  if (type === 'profit_factor') return `${toFixedString(dec, 2, REPORT_ROUNDING)}`;
  return toFixedString(dec, 2, REPORT_ROUNDING);
}