export interface Session { token: string; credential: string }
export interface LobbyState {
  token: string;
  phase: 'lobby';
  host_id: string;
  you: string;
  metrics: Record<'infrastructure' | 'public_trust' | 'economy' | 'safety', number>;
  players: { id: string; callsign: string; connected: boolean }[];
}
