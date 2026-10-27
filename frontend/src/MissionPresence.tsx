import type { LobbyState } from './types';

export function ConnectionNotice({ status, connected }: { status: string; connected: boolean }) {
  const retrying = !connected && status !== 'Connecting' && status !== 'Session no longer recoverable';
  return <section className={`connection-notice${connected ? '' : ' connection-notice--warning'}`}
    aria-label="Your connection" role="status" aria-live="polite" aria-atomic="true">
    <strong>{connected ? (status === 'Reconnected' ? 'Reconnected — mission state restored.' : 'Connected')
      : retrying ? (status.includes('unavailable') ? 'Connection unavailable — continuing to retry automatically.' : 'Connection lost — reconnecting automatically.')
      : status === 'Connecting' ? 'Connecting — restoring your mission seat.' : 'Session no longer recoverable.'}</strong>
    {!connected && <p>{retrying
      ? 'Displayed mission state may be outdated. Voting and chat are unavailable until your session is restored. Reconnection is automatic; refreshing should not normally be required.'
      : status === 'Connecting' ? 'Waiting for an authoritative mission update before enabling voting and chat.'
      : 'Voting and chat are unavailable. Check your invite or return to mission creation.'}</p>}
  </section>;
}

export function PlayerPresence({ mission, connected }: { mission: LobbyState; connected: boolean }) {
  // Counts and labels use only the server's participating seats. A disconnected
  // browser cannot infer current teammate presence from its cached snapshot.
  const count = mission.players.filter(player => player.connected).length;
  return <section className="player-presence" aria-label="Player presence">
    <div role="status" aria-live="polite" aria-atomic="true">
      <p className="presence-count">{connected ? 'Players connected' : 'Last known players connected'}: <strong>{count} of {mission.players.length}</strong></p>
      <ul className="presence-seats">{mission.players.map(player => <li key={player.id} className={player.connected ? 'presence-online' : 'presence-offline'}>
        <span>{player.callsign}{player.id === mission.you && <small> · You</small>}</span>
        <strong>{player.connected ? 'Connected' : 'Disconnected'}</strong>
      </li>)}</ul>
    </div>
    {!connected && <p className="presence-stale">Presence reflects the last server update.</p>}
  </section>;
}

export function ContinueStatus({ mission, connected, continuing }: {
  mission: LobbyState; connected: boolean; continuing: boolean;
}) {
  const missing = mission.players.filter(player => !player.connected);
  const count = mission.players.length - missing.length;
  return <div id="continue-status" className="continue-status" role="status" aria-live="polite" aria-atomic="true">
    {!connected ? <p>Reconnect and restore the current mission state before continuing. Participant presence may be outdated.</p>
      : missing.length > 0 ? <p>Waiting for {missing.map(player => player.callsign).join(', ')} to reconnect before continuing. Players connected: {count} of {mission.players.length}.</p>
      : continuing ? <p>Sending the request to continue — waiting for the server.</p>
      : mission.you !== mission.host_id ? <p>Waiting for the host to continue after reviewing the result.</p>
      : <p>All {mission.players.length} players are connected. Ready to {mission.crisis_number === mission.crisis_count ? 'finish the mission' : 'continue to the next crisis'}.</p>}
    {connected && missing.length > 0 && mission.you !== mission.host_id && <p>The host can continue once every assigned player reconnects.</p>}
  </div>;
}
