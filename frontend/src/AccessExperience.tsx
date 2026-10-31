import { useState } from 'react';
import { signInPath, signOutPath, type AccessState } from './access';
import { forgetAllSeats, savedSeatCount } from './session';
import { DataPrivacy, PublicInformation } from './PublicInformation';

const forgetWarning = 'Forget ALL mission seats saved in this browser? This cannot be undone. Signing in again cannot recover these credentials. If you leave an active seat, your team may need a new mission.';

export function SeatControls({ signedIn, returnTo, onForget }: {
  signedIn: boolean; returnTo: string; onForget?: (signingOut: boolean) => void;
}) {
  const [, update] = useState(0);
  const count = savedSeatCount();
  const [error, setError] = useState('');
  function forget(signingOut = false): boolean {
    if (!window.confirm(forgetWarning)) return false;
    try { forgetAllSeats(); onForget?.(signingOut); update(value => value + 1); setError(''); return true; }
    catch { setError('Saved seats could not be cleared. Clear this site’s browser storage before sharing this profile.'); return false; }
  }
  return <div className="seat-controls" aria-label="Browser seat controls">
    {signedIn && <a href={signOutPath(returnTo)} target="_top" onClick={event => {
      // Even with no known seats, a storage failure must prevent unsafe sign-out.
      if (!forget(true)) event.preventDefault();
    }}>Sign out and forget saved seats</a>}
    {count > 0 && <button type="button" className="secondary" onClick={() => { forget(); }}>Forget this browser’s saved seats</button>}
    {error && <p role="alert" className="error">{error}</p>}
  </div>;
}

export function AccessPage({ state, refresh, returnTo, invalidInvite = false }: {
  state: AccessState; refresh: () => Promise<boolean | null>; returnTo: string; invalidInvite?: boolean;
}) {
  return <main>
    <header><a className="brand" href="/">CE <span>Consensus Engine</span></a><span className="badge">v0.1 · Collective decision</span></header>
    <section className="intro"><p className="eyebrow">Civic coordination network</p>
      <h1>Intelligence proposes.<br /><em>Humanity decides.</em></h1>
      <p className="lede">A shared city. Incomplete information. Decisions you make together.</p></section>
    <section className="panel access-panel" aria-labelledby="access-title">
      <h2 id="access-title">{invalidInvite ? 'This invitation is not valid' : state === 'signedOut' ? 'Sign in to play with your team' : 'Your connection to the mission site'}</h2>
      {invalidInvite ? <><p role="alert">Ask your host for the original invite link. No mission or seat has been created.</p><a href="/">Return to mission creation</a></>
        : state === 'checking' ? <p role="status">Checking sign-in…</p>
        : state === 'signedOut' ? <>
          <p>Sign in with ChatGPT to create, join or resume a mission. No separate game account or password.</p>
          <a className="primary-link" href={signInPath(returnTo)} target="_top">Sign in with ChatGPT</a>
          <p>Your invite will be preserved. If sign-in is canceled, you can return here and try again.</p>
          {savedSeatCount() > 0 && <p>This browser remembers mission seats. Sign in with the same account to resume. Using a different account or a shared browser? Forget the saved seats first; forgotten seats cannot be recovered by signing in.</p>}
          <button className="secondary" type="button" onClick={() => { void refresh(); }}>Check sign-in again</button>
        </> : <><p role="status">Sign-in could not be checked. Your saved seat has not been removed.</p>
          <button type="button" onClick={() => { void refresh(); }}>Retry sign-in check</button></>}
      <SeatControls signedIn={false} returnTo={returnTo} />
    </section>
    <PublicInformation /><DataPrivacy />
    <footer>Consensus Engine <span>Collective judgment. Shared consequences.</span></footer>
  </main>;
}
