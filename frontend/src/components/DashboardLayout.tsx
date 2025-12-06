import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import api, { initializeAuth } from '../api/client';
import NotificationCenter from './NotificationCenter';

interface DashboardLayoutProps {
  children: ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const location = useLocation();
  const [me, setMe] = useState<{ nickname: string } | null>(null);
  const [loadingMe, setLoadingMe] = useState(true);
  const getAvatarUrl = (seed: string) => `https://api.dicebear.com/7.x/identicon/svg?seed=${seed}`;

  // 현재 경로와 일치하면 active 처리
  const isActive = (path: string) => {
    if (path === '/market') return location.pathname.startsWith('/market');
    return location.pathname === path;
  };
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        // Ensure auth initialization completes before fetching profile
        await initializeAuth();
        const data = await api.get('auth/login/me').json<{ nickname: string }>();
        if (mounted) setMe(data);
      } catch {
        // ignore
      } finally {
        if (mounted) setLoadingMe(false);
      }
    })();
    return () => { mounted = false; };
  }, []);
  const lastMarketTickerId = typeof window !== 'undefined' ? window.localStorage.getItem('lastMarketTickerId') : null;
  const marketPath = lastMarketTickerId ? `/market/${lastMarketTickerId}` : '/market';

  return (
    <div className="flex min-h-screen w-full flex-row bg-[#f5f6f8] dark:bg-[#101622] font-sans text-white">
      {/* Sidebar */}
      <aside className="flex h-screen flex-col justify-between border-r border-r-[#314368] bg-[#101623] p-4 w-64 sticky top-0 shrink-0">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
            {loadingMe ? (
              <>
                <div className="size-10 rounded-full bg-[#182234] animate-pulse" />
                <div className="flex flex-col gap-1">
                  <div className="h-4 w-28 bg-[#182234] rounded animate-pulse" />
                  <div className="h-3 w-24 bg-[#182234] rounded animate-pulse" />
                </div>
              </>
            ) : (
              <>
                <div className="bg-center bg-no-repeat aspect-square bg-cover rounded-full size-10" style={{ backgroundImage: `url("${getAvatarUrl(me?.nickname || 'admin')}")` }}></div>
                <div className="flex flex-col">
                  <h1 className="text-white text-base font-medium leading-normal">{me?.nickname || 'CyberTrader'}</h1>
                  <p className="text-[#90a4cb] text-sm font-normal leading-normal">Terminal v2.0</p>
                </div>
              </>
            )}
            </div>
            <NotificationCenter />
          </div>
          <nav className="flex flex-col gap-2 mt-4">
            {/* to 속성으로 경로 연결 */}
            <NavItem to="/dashboard" icon="bar_chart" label="Dashboard" active={isActive('/dashboard')} />
            <NavItem to={marketPath} icon="storefront" label="Markets" active={isActive('/market')} />
            <NavItem to="/leaderboard" icon="emoji_events" label="Leaderboard" active={isActive('/leaderboard')} />
            <NavItem to="/portfolio" icon="pie_chart" label="Portfolio" active={isActive('/portfolio')} />
            <NavItem to="/human" icon="rocket_launch" label="Human ETF" active={isActive('/human')} />
          </nav>
        </div>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <NavItem to="/settings" icon="settings" label="Settings" />
            <NavItem to="/help" icon="help" label="Help Center" />
            <NavItem to="/logout" icon="logout" label="Logout" />
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col p-8 bg-[#101622] overflow-y-auto h-screen">
        <div className="flex flex-col max-w-[1200px] mx-auto w-full gap-8">
          {children}
        </div>
      </main>
    </div>
  );
}

// Link 컴포넌트 사용
const NavItem = ({ to, icon, label, active = false }: { to: string, icon: string, label: string, active?: boolean }) => (
  <Link 
    to={to} 
    className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors
      ${active ? 'bg-[#222f49] text-white' : 'text-white/70 hover:bg-[#222f49] hover:text-white'}`}
  >
    <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: "'FILL' 1" }}>{icon}</span>
    <p className="text-sm font-medium leading-normal">{label}</p>
  </Link>
);