import { useEffect, useRef, useState } from 'react';
import { MissionConnection, type ConnectionStatus } from './missionConnection';
import type { ClockSample, LobbyState, MissionIntent, Session } from './types';

export function useLobby(session: Session | null, checkAccess?: () => Promise<boolean | null>) {
  const [mission, setMission] = useState<LobbyState | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('Connecting');
  const [actionError, setActionError] = useState('');
  const [clockSample, setClockSample] = useState<ClockSample | null>(null);
  const connectionRef = useRef<MissionConnection | null>(null);
  const token = session?.token;
  const credential = session?.credential;
  useEffect(() => {
    setMission(null);
    setStatus('Connecting');
    setActionError('');
    setClockSample(null);
    if (!token || !credential) return;
    const connection = new MissionConnection({ token, credential },
      `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/missions/${encodeURIComponent(token)}/ws`, {
        status: setStatus,
        snapshot: state => {
          setActionError('');
          setMission(state);
          setClockSample({ serverNow: state.server_now, receivedAt: performance.now() });
        },
        error: setActionError,
        checkAccess,
        accessLost: () => setStatus('Sign in required'),
      });
    connectionRef.current = connection;
    connection.start();
    return () => { connection.stop(); connectionRef.current = null; };
  }, [token, credential, checkAccess]);
  function sendIntent(intent: MissionIntent): boolean {
    setActionError('');
    if (connectionRef.current?.send(intent)) return true;
    setActionError('Reconnect before sending an action.');
    return false;
  }
  return { mission, status, rejected: status === 'Session no longer recoverable',
    connected: status === 'Connected' || status === 'Reconnected', sendIntent, actionError, clockSample,
    disconnect: () => connectionRef.current?.stop() };
}
