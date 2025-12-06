import { useSyncExternalStore } from 'react';
import toast from 'react-hot-toast';

export type NotificationKind = 'order' | 'trade' | 'liquidation' | 'system';
export type NotificationSeverity = 'info' | 'success' | 'warning' | 'error';

export interface NotificationItem {
  id: string;
  kind: NotificationKind;
  severity: NotificationSeverity;
  title: string;
  message: string;
  tickerId?: string;
  createdAt: string; // ISO string
  read: boolean;
  meta?: Record<string, unknown>;
}

interface NotificationInput {
  id?: string;
  kind: NotificationKind;
  severity?: NotificationSeverity;
  title: string;
  message: string;
  tickerId?: string;
  createdAt?: string;
  read?: boolean;
  meta?: Record<string, unknown>;
}

interface NotificationOptions {
  toast?: boolean;
  toastMessage?: string;
}

const STORAGE_KEY = 'stonks:notifications:v1';
const MAX_ITEMS = 80;

const makeId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `n-${Math.random().toString(16).slice(2)}-${Date.now()}`;
};

class NotificationStore {
  private items: NotificationItem[] = [];
  private listeners = new Set<() => void>();
  private hydrated = false;

  constructor() {
    this.hydrate();
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = () => this.items;
  getUnreadCount = () => this.items.filter(n => !n.read).length;

  add = (input: NotificationInput) => {
    const next: NotificationItem = {
      id: input.id || makeId(),
      kind: input.kind,
      severity: input.severity || 'info',
      title: input.title,
      message: input.message,
      tickerId: input.tickerId,
      createdAt: input.createdAt || new Date().toISOString(),
      read: input.read ?? false,
      meta: input.meta,
    };
    this.items = [next, ...this.items].slice(0, MAX_ITEMS);
    this.emit();
    return next;
  };

  markRead = (id: string) => {
    let changed = false;
    this.items = this.items.map(n => {
      if (n.id === id && !n.read) {
        changed = true;
        return { ...n, read: true };
      }
      return n;
    });
    if (changed) this.emit();
  };

  markAllRead = () => {
    if (!this.items.some(n => !n.read)) return;
    this.items = this.items.map(n => ({ ...n, read: true }));
    this.emit();
  };

  remove = (id: string) => {
    const next = this.items.filter(n => n.id !== id);
    if (next.length === this.items.length) return;
    this.items = next;
    this.emit();
  };

  clear = () => {
    if (this.items.length === 0) return;
    this.items = [];
    this.emit();
  };

  private emit() {
    for (const l of this.listeners) {
      try { l(); } catch { /* noop */ }
    }
    this.persist();
  }

  private hydrate() {
    if (this.hydrated) return;
    this.hydrated = true;
    if (typeof window === 'undefined') return;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as NotificationItem[];
      if (Array.isArray(parsed)) {
        this.items = parsed
          .filter(n => n && typeof n.id === 'string')
          .map(n => ({ ...n, read: Boolean(n.read) }));
      }
    } catch {
      // ignore broken storage
    }
  }

  private persist() {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(this.items));
    } catch {
      // ignore quota errors
    }
  }
}

export const notificationStore = new NotificationStore();

export function useNotifications() {
  return useSyncExternalStore(
    notificationStore.subscribe,
    notificationStore.getSnapshot,
    notificationStore.getSnapshot
  );
}

export function useUnreadNotifications() {
  return useSyncExternalStore(
    notificationStore.subscribe,
    notificationStore.getUnreadCount,
    notificationStore.getUnreadCount
  );
}

export function pushNotification(input: NotificationInput, options: NotificationOptions = {}) {
  const item = notificationStore.add(input);
  const shouldToast = options.toast ?? true;
  const toastMessage = options.toastMessage || input.message;
  if (shouldToast && toastMessage) {
    switch (item.severity) {
      case 'success':
        toast.success(toastMessage);
        break;
      case 'warning':
        toast(toastMessage, { icon: '⚠️' });
        break;
      case 'error':
        toast.error(toastMessage);
        break;
      default:
        toast(toastMessage);
    }
  }
  return item;
}

export function markNotificationRead(id: string) {
  notificationStore.markRead(id);
}

export function markAllNotificationsRead() {
  notificationStore.markAllRead();
}

export function clearNotifications() {
  notificationStore.clear();
}

export function removeNotification(id: string) {
  notificationStore.remove(id);
}
