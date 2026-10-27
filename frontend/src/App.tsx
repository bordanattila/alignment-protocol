import { useRef, useState, type FormEvent } from 'react';
import { clearSession, restoreSession, saveSession } from './session';
import { CrisisBriefing } from './CrisisBriefing';
import { RoleBadge } from './RoleBadge';
import { ActiveGameplay, ChatPanel, ResponseOptions, phaseLabel } from './Gameplay';
import { MissionReview } from './MissionReview';
import { ConnectionNotice, PlayerPresence } from './MissionPresence';
import { useLobby } from './useLobby';
import { MissionEntryRequest } from './missionEntry';
import { MissionEntryForm } from './MissionEntryForm';
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
  const entryRequest = useRef(new MissionEntryRequest());
  const { mission, status, rejected, sendIntent, actionError, clockSample, connected = status === 'Connected' } = useLobby(session);
  const activeMission = mission != null && mission.phase !== 'lobby';

  async function enter(event: FormEvent) {
    event.preventDefault();
    if (entryRequest.current.pending) return;
    setBusy(true);
    setError('');
    try {
      // Verify storage is usable before allocating a seat.
      localStorage.setItem('consensus.storage-check', 'ok');
      localStorage.removeItem('consensus.storage-check');
      const result = await entryRequest.current.submit(inviteToken, callsign);
      if (!result) return;
      saveSession(result);
      history.replaceState(null, '', `?mission=${encodeURIComponent(result.token)}`);
      setSession(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to connect. Please try again.');
    } finally { setBusy(false); }
  }

  async function missionAction(action: 'start' | 'discussion' | 'continue') {
    if (!session || !connected) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/missions/${encodeURIComponent(session.token)}/${action}`, {
        method: 'POST', headers: { 'X-Mission-Session': session.credential, 'Content-Type': 'application/json' },
        body: action === 'continue' ? JSON.stringify({ result_id: mission?.result?.id }) : undefined,
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

  if (mission?.summary && (mission.phase === 'completed' || mission.phase === 'failed')) return <main className="active-mission">
    <header><a className="brand" href="/">CE <span>Consensus Engine</span></a></header>
    <ConnectionNotice status={status} connected={connected} />
    <PlayerPresence mission={mission} connected={connected} />
    <MissionReview mission={mission} />
    <footer><a href="/">Return to mission creation</a><span>Collective judgment. Shared consequences.</span></footer>
  </main>;

  return <main className={activeMission ? 'active-mission' : undefined}>
    <header><a className="brand" href="/">CE <span>Consensus Engine</span></a><span className="badge">v0.1 · Collective decision</span></header>
    {session && <ConnectionNotice status={status} connected={connected} />}
    {mission && <PlayerPresence mission={mission} connected={connected} />}
    {activeMission ? <section className="mission-header" aria-label="Current mission">
      <p className="eyebrow">Crisis {mission.crisis_number.toString().padStart(2, '0')} / {mission.crisis_count} <span>· {phaseLabel(mission)}</span></p>
      <h1>{mission.crisis?.title}</h1>
    </section> : <section className="intro">
      <p className="eyebrow">Civic coordination network</p>
      <h1>Intelligence proposes.<br /><em>Humanity decides.</em></h1>
      <p className="lede">A shared city. Incomplete information. Decisions you make together.</p>
    </section>}
    {actionError && <p className="error" role="alert">{actionError}</p>}
    {mission && <ActiveGameplay mission={mission} connected={connected} sendIntent={sendIntent} sample={clockSample} continuing={busy} onContinue={() => missionAction('continue')} />}
    {!session ? <section className="panel entry">
      <div><p className="eyebrow">{inviteToken ? 'Mission invitation' : 'Assemble your team'}</p>
        <h2>{inviteToken ? 'Join the mission' : 'Open a mission'}</h2>
        <p>Bring 2–4 people into a shared operations room. No account required.</p></div>
      <MissionEntryForm callsign={callsign} busy={busy} error={error} joining={Boolean(inviteToken)} onCallsign={setCallsign} onSubmit={enter} />
    </section> : <section className="lobby-grid">
      <div className="panel">
        <div className="panel-heading"><div><p className="eyebrow">Operations room</p><h2>{mission?.phase === 'lobby' || !mission ? 'Mission lobby' : phaseLabel(mission)}</h2></div></div>
        {mission ? <>
          <p>{mission.phase === 'lobby' ? `${mission.players.length} of 4 seats occupied · Invite your team to join.` : ({ reconnect_wait: 'Mission restored after server interruption. Waiting for every player to reconnect before the next mandatory phase. Saved votes and deadlines are preserved.', briefing: 'Review the public briefing and your private intelligence together.', discussion: 'Share your information in the team chat above.', voting: 'Submit your private vote in the active voting panel above.', consensus_window: 'Discuss your choices in the live chat above before final voting begins.', decision_locked: 'The decision and civilization impact are recorded above. Review the result with your team.', failed: 'The civilization has collapsed. Review the final outcome above.', completed: 'The mission is complete. Review your final score and civilization outcome.' }[mission.phase])}</p>
          {mission.phase === 'lobby' && (mission.you === mission.host_id ? <>
            <button disabled={busy || !connected || mission.players.length < 2 || mission.players.some(player => !player.connected)} onClick={() => missionAction('start')}>Start Mission</button>
            <p>Start with 2–4 players. Every occupied seat must be connected.</p>
          </> : <p>Waiting for the host to start the mission.</p>)}
          {mission.phase === 'briefing' && (mission.you === mission.host_id ? <button disabled={busy || !connected || mission.players.some(player => !player.connected)} onClick={() => missionAction('discussion')}>Begin discussion</button> : <p>Read your briefing while the host prepares discussion.</p>)}
          {mission.phase === 'discussion' && <p role="status">Compare your information with the team in mission chat before the discussion deadline.</p>}
          {mission.phase === 'lobby' && <ul className="players">{mission.players.map(player => <li key={player.id}>
            <div><strong>{player.callsign}</strong><small>{player.id === mission.you ? 'You' : 'Teammate'}{player.id === mission.host_id ? ' · Host' : ''}</small><div className="role-badges">{player.roles.map(role => <RoleBadge key={role} role={role} />)}</div></div>
            <span className={player.connected ? 'online' : 'offline'}>{player.connected ? 'Connected' : 'Offline'}</span>
          </li>)}</ul>}
          {mission.phase === 'lobby' && <><button onClick={copyInvite}>{copied ? 'Invite link copied' : 'Copy Invite Link'}</button>
          <label className="invite-label" htmlFor="invite">Mission invite</label>
          <input id="invite" value={location.href} readOnly onFocus={event => event.target.select()} /></>}
        </> : <p role="status">{rejected ? 'This session is unavailable. Check your invite or ask the host to restore access.' : 'Restoring your mission seat…'}</p>}
        {rejected && <button onClick={() => { clearSession(session.token); location.assign('/'); }}>Return to mission creation</button>}
      </div>
      <aside className="panel"><p className="eyebrow">Civilization state</p><h2>Shared stability</h2>
        <div className="metrics">{Object.entries(mission?.metrics ?? { infrastructure: 70, public_trust: 70, economy: 70, safety: 70 }).map(([key, value]) => <div key={key}>
          <div><span>{metricNames[key]}</span><strong>{value}<small>/100</small></strong></div><meter min={0} max={100} value={value}>{value}</meter>
        </div>)}</div>
      </aside>
    </section>}
    {mission?.crisis && <CrisisBriefing mission={mission} />}
    {mission?.crisis && mission.phase !== 'voting' && <div className="reference-options"><ResponseOptions mission={mission} connected={connected} sendIntent={sendIntent} /></div>}
    {mission && (mission.phase === 'reconnect_wait' || mission.phase === 'voting' || mission.phase === 'decision_locked' || mission.phase === 'failed' || mission.phase === 'completed') && <div className="chat-archive"><ChatPanel mission={mission} connected={connected} sendIntent={sendIntent} /></div>}
    {session && error && <p className="error" role="alert">{error}</p>}
    <section className="scope"><span className="eyebrow">Mission protocol</span><p>Combine your information, decide together, and carry the consequences across ten crises.</p></section>
    <footer>Consensus Engine <span>Collective judgment. Shared consequences.</span></footer>
  </main>;
}
