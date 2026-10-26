import { useState, type FormEvent } from 'react';
import { clearSession, restoreSession, saveSession } from './session';
import { CrisisBriefing } from './CrisisBriefing';
import { RoleBadge } from './RoleBadge';
import { useLobby } from './useLobby';
import type { Session } from './types';

const inviteToken = new URLSearchParams(location.search).get('mission');
const metricNames: Record<string, string> = {
  infrastructure: 'Infrastructure', public_trust: 'Public Trust', economy: 'Economy', safety: 'Safety',
};

export default function App() {
  const [session, setSession] = useState<Session | null>(() => restoreSession(inviteToken));
  const [callsign, setCallsign] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const { mission, status, rejected } = useLobby(session);
  const activeMission = mission?.phase === 'briefing' || mission?.phase === 'discussion';

  async function enter(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      // Verify storage is usable before allocating a seat.
      localStorage.setItem('consensus.storage-check', 'ok');
      localStorage.removeItem('consensus.storage-check');
      const response = await fetch(inviteToken ? `/api/missions/${encodeURIComponent(inviteToken)}/join` : '/api/missions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ callsign }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Enter a callsign of 1–24 characters.');
      saveSession(result);
      history.replaceState(null, '', `?mission=${encodeURIComponent(result.token)}`);
      setSession(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to connect. Please try again.');
    } finally { setBusy(false); }
  }

  async function missionAction(action: 'start' | 'discussion') {
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/missions/${encodeURIComponent(session.token)}/${action}`, {
        method: 'POST', headers: { 'X-Mission-Session': session.credential },
      });
      if (!response.ok) {
        const result = await response.json();
        throw new Error(typeof result.detail === 'string' ? result.detail : 'Unable to update mission.');
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to reach the mission server.');
    } finally { setBusy(false); }
  }

  async function copyInvite() {
    try {
      await navigator.clipboard.writeText(location.href);
      setCopied(true);
    } catch { setError('Copy the invite URL from the field below.'); }
  }

  return <main className={activeMission ? 'active-mission' : undefined}>
    <header><a className="brand" href="/">CE <span>Consensus Engine</span></a><span className="badge">v0.1 · Crisis briefing</span></header>
    {activeMission ? <section className="mission-header" aria-label="Current mission">
      <p className="eyebrow">Crisis 01 <span>· {mission.phase === 'briefing' ? 'Briefing' : 'Discussion'}</span></p>
      <h1>{mission.crisis?.title}</h1>
    </section> : <section className="intro">
      <p className="eyebrow">Civic coordination network</p>
      <h1>Intelligence proposes.<br /><em>Humanity decides.</em></h1>
      <p className="lede">A shared city. Incomplete information. Decisions you make together.</p>
    </section>}
    {!session ? <section className="panel entry">
      <div><p className="eyebrow">{inviteToken ? 'Mission invitation' : 'Assemble your team'}</p>
        <h2>{inviteToken ? 'Join the mission' : 'Open a mission'}</h2>
        <p>Bring 2–4 people into a shared operations room. No account required.</p></div>
      <form onSubmit={enter}>
        <label htmlFor="callsign">Your callsign</label>
        <input id="callsign" value={callsign} onChange={event => setCallsign(event.target.value)} placeholder="e.g. Rivera" required maxLength={24} autoComplete="nickname" />
        <button disabled={busy || !callsign.trim()}>{busy ? 'Connecting…' : inviteToken ? 'Join Mission' : 'Create Mission'}</button>
      </form>
    </section> : <section className="lobby-grid">
      <div className="panel">
        <div className="panel-heading"><div><p className="eyebrow">Operations room</p><h2>{mission?.phase === 'lobby' || !mission ? 'Mission lobby' : mission.phase === 'briefing' ? 'Mission briefing' : 'Discussion ready'}</h2></div><span className="badge" role="status">{status}</span></div>
        {mission ? <>
          <p>{mission.phase === 'lobby' ? `${mission.players.length} of 4 seats occupied · Invite your team to join.` : 'Review the public briefing and your private intelligence together.'}</p>
          {mission.phase === 'lobby' && (mission.you === mission.host_id ? <>
            <button disabled={busy || status !== 'Connected' || mission.players.length < 2 || mission.players.some(player => !player.connected)} onClick={() => missionAction('start')}>Start Mission</button>
            <p>Start with 2–4 players. Every occupied seat must be connected.</p>
          </> : <p>Waiting for the host to start the mission.</p>)}
          {mission.phase === 'briefing' && (mission.you === mission.host_id ? <button disabled={busy || status !== 'Connected' || mission.players.some(player => !player.connected)} onClick={() => missionAction('discussion')}>Begin discussion</button> : <p>Read your briefing while the host prepares discussion.</p>)}
          {mission.phase === 'discussion' && <p role="status">Discussion ready. Compare your information with the team. Voting is not available yet.</p>}
          <ul className="players">{mission.players.map(player => <li key={player.id}>
            <div><strong>{player.callsign}</strong><small>{player.id === mission.you ? 'You' : 'Teammate'}{player.id === mission.host_id ? ' · Host' : ''}</small><div className="role-badges">{player.roles.map(role => <RoleBadge key={role} role={role} />)}</div></div>
            <span className={player.connected ? 'online' : 'offline'}>{player.connected ? 'Connected' : 'Offline'}</span>
          </li>)}</ul>
          {mission.phase === 'lobby' && <><button onClick={copyInvite}>{copied ? 'Invite link copied' : 'Copy Invite Link'}</button>
          <label className="invite-label" htmlFor="invite">Mission invite</label>
          <input id="invite" value={location.href} readOnly onFocus={event => event.target.select()} /></>}
        </> : <p role="status">{rejected ? 'This session is unavailable. The server may have restarted.' : 'Restoring your mission seat…'}</p>}
        {rejected && <button onClick={() => { clearSession(session.token); location.assign('/'); }}>Return to mission creation</button>}
      </div>
      <aside className="panel"><p className="eyebrow">Civilization baseline</p><h2>Shared stability</h2>
        <div className="metrics">{Object.entries(mission?.metrics ?? { infrastructure: 70, public_trust: 70, economy: 70, safety: 70 }).map(([key, value]) => <div key={key}>
          <div><span>{metricNames[key]}</span><strong>{value}<small>/100</small></strong></div><meter min={0} max={100} value={value}>{value}</meter>
        </div>)}</div>
      </aside>
    </section>}
    {mission?.crisis && <CrisisBriefing mission={mission} />}
    {error && <p className="error" role="alert">{error}</p>}
    <section className="scope"><span className="eyebrow">Milestone 2</span><p>Mission start, assigned domains, and Crisis 01 intelligence are available. Discussion is untimed; chat, voting, consequences, and QR invites remain planned.</p></section>
    <footer>Consensus Engine <span>Collective judgment. Shared consequences.</span></footer>
  </main>;
}
