import type { Session } from './types';

const key = (token: string) => `consensus.session.${token}`;
export function restoreSession(token: string | null): Session | null {
  if (!token) return null;
  try {
    const credential = localStorage.getItem(key(token));
    return credential ? { token, credential } : null;
  } catch { return null; }
}
export function saveSession(session: Session) {
  // Persist before navigating: refreshing must reuse the same authorized seat.
  localStorage.setItem(key(session.token), session.credential);
}
export function clearSession(token: string) { localStorage.removeItem(key(token)); }
