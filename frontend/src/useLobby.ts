import { SnapshotOrder } from './snapshotOrder';
import { useEffect, useRef, useState } from 'react';
import type { ClockSample, LobbyState, MissionIntent, Session } from './types';

export function useLobby(session: Session | null) {
  const [mission, setMission] = useState<LobbyState | null>(null);
  const [status, setStatus] = useState('Connecting');
  const [rejected, setRejected] = useState(false);
  const [actionError, setActionError] = useState('');
  const [clockSample, setClockSample] = useState<ClockSample | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  useEffect(() => {
    setMission(null);
    setRejected(false);
    setActionError('');
    setClockSample(null);
    if (!session) return;
    let stopped = false;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let attempt = 0;
    const snapshots = new SnapshotOrder();
    function connect() {
      setStatus(attempt ? 'Reconnecting' : 'Connecting');
      const connection = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/missions/${encodeURIComponent(session!.token)}/ws`);
      socket = connection;
      socketRef.current = connection;
      socket.onopen = () => { if (!stopped && socketRef.current === connection) connection.send(JSON.stringify({ type: 'authenticate', credential: session!.credential })); };
      socket.onmessage = event => {
        if (stopped || socketRef.current !== connection) return;
        const message = JSON.parse(event.data);
        if (message.type === 'state') {
          if (!snapshots.accept(message.mission)) return;
          setMission(message.mission);
          setClockSample({ serverNow: message.mission.server_now, receivedAt: performance.now() });
          setStatus('Connected');
          attempt = 0;
        } else if (message.type === 'error') {
          setActionError(message.detail);
        }
      };
      socket.onclose = event => {
        if (stopped || socketRef.current !== connection) return;
        if (event.code === 1008) {
          setStatus('Session unavailable');
          setRejected(true);
          return;
        }
        setStatus('Reconnecting');
        retry = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 10000));
      };
    }
    connect();
    return () => { stopped = true; clearTimeout(retry); socket?.close(); socketRef.current = null; };
  }, [session]);
  function sendIntent(intent: MissionIntent): boolean {
    setActionError('');
    if (socketRef.current?.readyState !== WebSocket.OPEN || status !== 'Connected') {
      setActionError('Reconnect before sending an action.');
      return false;
    }
    socketRef.current.send(JSON.stringify(intent));
    return true;
  }
  return { mission, status, rejected, sendIntent, actionError, clockSample };
}
