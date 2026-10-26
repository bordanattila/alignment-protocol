export type Role = 'infrastructure' | 'community' | 'economy' | 'safety';
export interface Session { token: string; credential: string }
export interface LobbyState {
  token: string;
  phase: 'lobby' | 'briefing' | 'discussion';
  roles: Role[];
  crisis: { id: string; title: string; briefing: string; ai_recommendation_choice_id: string; choices: { id: string; title: string; description: string }[] } | null;
  private_intelligence: Partial<Record<Role, string>>;
  host_id: string;
  you: string;
  metrics: Record<'infrastructure' | 'public_trust' | 'economy' | 'safety', number>;
  players: { id: string; callsign: string; connected: boolean; roles: Role[] }[];
}
