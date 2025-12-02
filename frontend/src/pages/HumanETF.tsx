import { useState, useEffect } from 'react';
import api from '../api/client';
import DashboardLayout from '../components/DashboardLayout';

type MeProfile = { nickname: string; is_active: boolean; is_bankrupt?: boolean };
type SimpleMessage = { message?: string };

export default function HumanETF() {
  const [profile, setProfile] = useState<MeProfile | null>(null);
  
  // 사용자 정보 로드 (임시로 hardcoded ID 대신 /users/me 호출 또는 context 사용 필요)
  // 여기선 localStorage 등에서 ID를 가져온다고 가정하거나, 현재 로그인된 유저 API가 있다고 가정
  // 실제론 /auth/login/me 가 있네요.
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
      alert(res?.message || "Action Successful");
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Action Failed';
      alert(message);
    }
  };

  if (!profile) return <div className="p-8 text-white">Loading...</div>;

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-8">
        
        {/* Profile Card */}
        <div className="flex p-6 border border-[#314368] bg-[#101623] rounded-xl items-center gap-6">
          <div 
            className="w-24 h-24 rounded-full border-4 border-[#0d59f2] bg-cover bg-center shadow-[0_0_15px_rgba(13,89,242,0.3)]"
            style={{ backgroundImage: `url("https://api.dicebear.com/7.x/pixel-art/svg?seed=${profile.nickname}")` }}
          ></div>
          <div>
            <h1 className="text-white text-3xl font-bold font-mono tracking-tighter">
              {profile.nickname} <span className="text-[#0d59f2] text-xl">ETF</span>
            </h1>
            <p className="text-[#90a4cb] mt-1">Status: {profile.is_active ? 'Active Trader' : 'Inactive'}</p>
            {profile.is_bankrupt && <span className="inline-block mt-2 px-2 py-1 bg-red-500/20 text-red-500 text-xs font-bold rounded">BANKRUPT</span>}
          </div>
        </div>

        {/* Solvency Bar (Design Element) */}
        <div className="flex flex-col gap-3 p-6 border border-[#314368] bg-[#101623] rounded-xl">
          <div className="flex justify-between items-center text-white">
            <span className="font-medium">Solvency Status</span>
            <span className="font-mono font-bold text-[#00FF41]">GOOD</span>
          </div>
          <div className="h-4 bg-[#222f49] rounded-full overflow-hidden border border-[#314368]">
            <div className="h-full bg-[#00FF41] w-[85%] shadow-[0_0_10px_#00FF41]"></div>
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
              <button 
                onClick={() => handleAction('bankruptcy')}
                className="px-4 py-3 rounded-lg bg-red-500/20 text-red-500 font-bold hover:bg-red-500/30 transition-all border border-red-500/50"
              >
                Declare Bankruptcy
              </button>
            </div>
          </div>

        </div>
      </div>
    </DashboardLayout>
  );
}