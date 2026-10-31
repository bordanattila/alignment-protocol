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

export function savedSeatCount(): number {
  try { return Object.keys(localStorage).filter(name => name.startsWith('consensus.session.')).length; }
  catch { return 0; }
}

export function forgetAllSeats(): void {
  // Never clear unrelated application or Sites storage. Fail rather than
  // navigating through sign-out while known seat secrets could remain behind.
  for (const name of Object.keys(localStorage)) {
    if (name.startsWith('consensus.session.')) localStorage.removeItem(name);
  }
  if (savedSeatCount()) throw new Error('Unable to forget saved seats. Clear this site’s browser storage before sharing this profile.');
}
