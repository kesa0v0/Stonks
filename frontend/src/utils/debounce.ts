// frontend/src/utils/debounce.ts

import { useRef, useEffect, useCallback } from 'react';

type Callback = (...args: any[]) => void;

export function useDebounce<T extends Callback>(callback: T, delay: number): T {
  const timeoutRef = useRef<number | null>(null);
  const callbackRef = useRef(callback);

  // Update callbackRef when callback changes
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  return useCallback((...args: Parameters<T>) => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = window.setTimeout(() => {
      callbackRef.current(...args);
    }, delay);
  }, [delay]) as T;
}
