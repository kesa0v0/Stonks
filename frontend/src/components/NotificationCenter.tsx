import { useEffect, useMemo, useRef, useState } from 'react';
import {
  useNotifications,
  useUnreadNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  clearNotifications,
  removeNotification,
} from '../store/notifications';

export default function NotificationCenter() {
  const items = useNotifications();
  const unread = useUnreadNotifications();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Close when clicking outside
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!panelRef.current) return;
      if (!panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const grouped = useMemo(() => {
    return items.reduce<{ date: string; list: typeof items }[]>((acc, n) => {
      const date = n.createdAt?.slice(0, 10) || '오늘';
      const found = acc.find(g => g.date === date);
      if (found) found.list.push(n);
      else acc.push({ date, list: [n] });
      return acc;
    }, []);
  }, [items]);

  const renderSeverity = (severity: string) => {
    switch (severity) {
      case 'success':
        return 'bg-emerald-500/15 text-emerald-200 border border-emerald-500/40';
      case 'warning':
        return 'bg-amber-500/15 text-amber-100 border border-amber-500/40';
      case 'error':
        return 'bg-rose-500/15 text-rose-100 border border-rose-500/40';
      default:
        return 'bg-slate-500/15 text-slate-100 border border-slate-500/40';
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="relative flex items-center justify-center rounded-lg border border-[#1f2a44] bg-[#0f1729] p-2 text-sm text-white hover:border-[#2c3a5c] hover:bg-[#131d32]"
        aria-label="Notifications"
      >
        <span className="material-symbols-outlined text-base" style={{ fontVariationSettings: "'FILL' 1" }}>notifications</span>
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-5 rounded-full bg-rose-500 px-1 text-[11px] font-semibold leading-5 text-white text-center">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-full ml-2 top-0 z-30 w-96 max-w-[90vw] rounded-2xl border border-[#1f2a44] bg-[#0c1324] shadow-2xl shadow-black/40">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#1f2a44]">
            <div className="flex items-center gap-2 text-sm text-white/80">
              <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>notifications</span>
              <span>Notification Center</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-white/60">
              <button onClick={markAllNotificationsRead} className="hover:text-white">모두 읽음</button>
              <button onClick={clearNotifications} className="hover:text-white">전체 삭제</button>
            </div>
          </div>

          <div className="max-h-[60vh] overflow-y-auto">
            {items.length === 0 && (
              <div className="px-4 py-8 text-center text-white/50 text-sm">알림이 없습니다.</div>
            )}
            {grouped.map(group => (
              <div key={group.date} className="px-4 py-3 space-y-2">
                <div className="text-[11px] uppercase tracking-wide text-white/40">{group.date}</div>
                {group.list.map(item => (
                  <div
                    key={item.id}
                    className={`group rounded-xl px-3 py-3 border transition ${renderSeverity(item.severity)} ${item.read ? 'opacity-80' : 'opacity-100'} flex items-start gap-3`}
                    onClick={() => markNotificationRead(item.id)}
                  >
                    <div className="mt-0.5">
                      <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                        {item.kind === 'trade' ? 'check_circle' : item.kind === 'liquidation' ? 'report' : 'info'}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-white truncate">{item.title}</p>
                        <span className="text-[11px] text-white/50 whitespace-nowrap">{new Date(item.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                      <p className="text-sm text-white/70 leading-snug mt-1 break-words">{item.message}</p>
                      {item.tickerId && (
                        <p className="text-[11px] text-white/40 mt-1">{item.tickerId}</p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); removeNotification(item.id); }}
                      className="opacity-0 group-hover:opacity-100 text-white/50 hover:text-white"
                    >
                      <span className="material-symbols-outlined text-[16px]" style={{ fontVariationSettings: "'FILL' 1" }}>close</span>
                    </button>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
