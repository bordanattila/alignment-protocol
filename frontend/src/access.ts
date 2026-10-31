/** Sites owns authentication. This module never accepts identity from a URL or browser header. */
export type AccessState = 'checking' | 'signedIn' | 'signedOut' | 'unavailable';

export function missionInvite(search: string): { token: string | null; invalid: boolean } {
  const values = new URLSearchParams(search).getAll('mission');
  if (!values.length) return { token: null, invalid: false };
  if (values.length !== 1 || !/^[A-Za-z0-9_-]{1,128}$/.test(values[0])) return { token: null, invalid: true };
  return { token: values[0], invalid: false };
}

export function safeReturnPath(value: string): string {
  if (!value.startsWith('/') || value.startsWith('//') || /[\\\x00-\x20]/.test(value)) return '/';
  const base = 'https://return.invalid';
  try {
    const url = new URL(value, base);
    if (url.origin !== base || !['/', '/index.html'].includes(url.pathname)) return '/';
    const invite = missionInvite(url.search);
    // Only the invite is retained. Auth callbacks, secrets, arbitrary queries
    // and fragments are never part of the return URL.
    return invite.token && !invite.invalid ? `/?mission=${encodeURIComponent(invite.token)}` : '/';
  } catch { return '/'; }
}
export const signInPath = (value: string) => `/signin-with-chatgpt?return_to=${encodeURIComponent(safeReturnPath(value))}`;
export const signOutPath = (value: string) => `/signout-with-chatgpt?return_to=${encodeURIComponent(safeReturnPath(value))}`;

export async function readAccessStatus(fetcher: typeof fetch = fetch): Promise<boolean | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetcher('/api/access', { credentials: 'same-origin', cache: 'no-store', redirect: 'manual', signal: controller.signal });
    // Private dispatch can deny/redirect before the Worker runs. Never follow
    // an OAuth redirect with fetch; the user must navigate the normal anchor.
    if (response.type === 'opaqueredirect' || [401, 403].includes(response.status)
      || (response.status >= 300 && response.status < 400)) return false;
    if (!response.ok) return null; // A platform/network error is not a lost seat.
    const value = await response.json();
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    return Object.keys(value).length === 1 && typeof value.signedIn === 'boolean' ? value.signedIn : null;
  } catch { return null; }
  finally { clearTimeout(timer); }
}
