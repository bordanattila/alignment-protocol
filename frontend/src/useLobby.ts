import { useEffect, useState } from 'react';
import type { LobbyState, Session } from './types';

export function useLobby(session: Session | null) {
  const [mission, setMission] = useState<LobbyState | null>(null);
  const [status, setStatus] = useState('Connecting');
  const [rejected, setRejected] = useState(false);
  useEffect(() => {
    setMission(null);
    setRejected(false);
    if (!session) return;
    let stopped = false;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let attempt = 0;
    function connect() {
      setStatus(attempt ? 'Reconnecting' : 'Connecting');
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/missions/${encodeURIComponent(session!.token)}/ws`);
      socket.onopen = () => socket.send(JSON.stringify({ type: 'authenticate', credential: session!.credential }));
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.type === 'state') {
          setMission(message.mission);
          setStatus('Connected');
          attempt = 0;
        }
      };
      socket.onclose = event => {
        if (stopped) return;
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
    return () => { stopped = true; clearTimeout(retry); socket?.close(); };
  }, [session]);
  return { mission, status, rejected };
}
