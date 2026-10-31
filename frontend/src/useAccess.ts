import { useCallback, useEffect, useRef, useState } from 'react';
import { readAccessStatus, type AccessState } from './access';

export function useAccess() {
  const [state, setState] = useState<AccessState>('checking');
  const alive = useRef(true);
  const pending = useRef<Promise<boolean | null> | null>(null);
  const refresh = useCallback((): Promise<boolean | null> => {
    if (pending.current) return pending.current;
    const request = readAccessStatus().then(result => {
      if (alive.current) setState(previous => result === null
        ? previous === 'signedIn' ? previous : 'unavailable'
        : result ? 'signedIn' : 'signedOut');
      return result;
    }).finally(() => { if (pending.current === request) pending.current = null; });
    pending.current = request;
    return request;
  }, []);
  useEffect(() => {
    alive.current = true;
    void refresh();
    const visible = () => { if (document.visibilityState === 'visible') void refresh(); };
    const focus = () => { void refresh(); };
    window.addEventListener('focus', focus);
    window.addEventListener('pageshow', focus);
    document.addEventListener('visibilitychange', visible);
    return () => {
      alive.current = false;
      window.removeEventListener('focus', focus);
      window.removeEventListener('pageshow', focus);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [refresh]);
  return { state, refresh };
}
