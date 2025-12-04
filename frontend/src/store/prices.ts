import { useSyncExternalStore } from 'react';

// Lightweight price store with per-key subscriptions
class PricesStore {
  private prices: Map<string, number> = new Map();
  private globalListeners = new Set<() => void>();
  private keyListeners: Map<string, Set<() => void>> = new Map();
  private version = 0;
  private versionListeners = new Set<() => void>();

  subscribeAll = (listener: () => void) => {
    this.globalListeners.add(listener);
    return () => this.globalListeners.delete(listener);
  };

  subscribeKey = (key: string, listener: () => void) => {
    let set = this.keyListeners.get(key);
    if (!set) {
      set = new Set();
      this.keyListeners.set(key, set);
    }
    set.add(listener);
    return () => set && set.delete(listener);
  };

  getSnapshotAll = () => this.prices;
  getSnapshotKey = (key: string) => this.prices.get(key);
  getSnapshotVersion = () => this.version;
  subscribeVersion = (listener: () => void) => {
    this.versionListeners.add(listener);
    return () => this.versionListeners.delete(listener);
  };

  updateBatch = (updates: Map<string, number>) => {
    if (updates.size === 0) return;
    let anyKeyChanged = false;
    const changedKeys: string[] = [];
    for (const [k, v] of updates) {
      const prev = this.prices.get(k);
      if (prev !== v) {
        this.prices.set(k, v);
        anyKeyChanged = true;
        changedKeys.push(k);
      }
    }
    if (!anyKeyChanged) return;
    this.version++;
    // Notify per-key listeners first
    for (const k of changedKeys) {
      const set = this.keyListeners.get(k);
      if (set) for (const l of set) {
        try { l(); } catch {
          // swallow listener errors
        }
      }
    }
    // Then notify global listeners
    for (const l of this.globalListeners) {
      try { l(); } catch {
        // swallow listener errors
      }
    }
    // And notify version listeners
    for (const l of this.versionListeners) {
      try { l(); } catch {
        // swallow listener errors
      }
    }
  };
}

export const pricesStore = new PricesStore();

export function usePricesAll() {
  return useSyncExternalStore(
    pricesStore.subscribeAll,
    pricesStore.getSnapshotAll,
    pricesStore.getSnapshotAll
  );
}

export function usePrice(tickerId: string) {
  return useSyncExternalStore(
    (listener) => pricesStore.subscribeKey(tickerId, listener),
    () => pricesStore.getSnapshotKey(tickerId),
    () => pricesStore.getSnapshotKey(tickerId)
  );
}

export function usePricesVersion() {
  return useSyncExternalStore(
    pricesStore.subscribeVersion,
    pricesStore.getSnapshotVersion,
    pricesStore.getSnapshotVersion
  );
}
