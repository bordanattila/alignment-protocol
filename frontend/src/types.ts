export type Role = 'infrastructure' | 'community' | 'economy' | 'safety';
export interface Session { token: string; credential: string }
export interface LobbyState {
  token: string;
  phase: 'lobby' | 'briefing' | 'discussion' | 'voting' | 'consensus_window' | 'decision_locked';
  server_now: number;
  deadline: number | null;
  chat: { id: string; sender_id: string; callsign: string; text: string; timestamp: number }[];
  voting: { round_id: string; number: number; eligible_count: number; submitted_count: number; your_vote: string | null } | null;
  closed_rounds: { round_id: string; number: number; totals: Record<string, number>; abstentions: number }[];
  decision: { choice_id: string; reason: 'initial_plurality' | 'final_plurality' | 'ai_tie_break' | 'no_vote_ai_fallback'; round_id: string; totals: Record<string, number>; abstentions: number; ai_followed: boolean } | null;
  roles: Role[];
  crisis: { id: string; title: string; briefing: string; ai_recommendation_choice_id: string; choices: { id: string; title: string; description: string }[] } | null;
  private_intelligence: Partial<Record<Role, string>>;
  host_id: string;
  you: string;
  metrics: Record<'infrastructure' | 'public_trust' | 'economy' | 'safety', number>;
  players: { id: string; callsign: string; connected: boolean; roles: Role[] }[];
}

export type MissionIntent = { type: 'chat'; text: string } | { type: 'vote'; round_id: string; choice_id: string };
export interface ClockSample { serverNow: number; receivedAt: number }
