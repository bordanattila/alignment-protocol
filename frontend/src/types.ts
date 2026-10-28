export type Role = 'infrastructure' | 'community' | 'economy' | 'safety';
export type Metric = 'infrastructure' | 'public_trust' | 'economy' | 'safety';
export type Civilization = Record<Metric, number>;
export interface Session { token: string; credential: string }
export type MissionMode = 'authored' | 'generated';
export interface LobbyState {
  mode?: MissionMode;
  generation_status?: 'preparing' | 'unavailable' | null;
  revision?: number;
  recovery?: {phase: 'discussion' | 'voting' | 'consensus_window'; original_deadline: number | null} | null;
  history?: CrisisResult[];
  metrics_timeline?: MetricSnapshot[];
  summary?: MissionSummary | null;
  token: string;
  phase: 'preparing' | 'reconnect_wait' | 'lobby' | 'briefing' | 'discussion' | 'voting' | 'consensus_window' | 'decision_locked' | 'failed' | 'completed';
  crisis_number: number;
  crisis_count: number;
  result: CrisisResult | null;
  collapsed_metrics: Metric[];
  consensus_score: number | null;
  server_now: number;
  deadline: number | null;
  chat: { crisis_number?: number; id: string; sender_id: string; callsign: string; text: string; timestamp: number }[];
  voting: { round_id: string; number: number; eligible_count: number; submitted_count: number; your_vote: string | null } | null;
  closed_rounds: { round_id: string; number: number; totals: Record<string, number>; abstentions: number }[];
  decision: { choice_id: string; reason: 'initial_plurality' | 'final_plurality' | 'ai_tie_break' | 'no_vote_ai_fallback'; round_id: string; totals: Record<string, number>; abstentions: number; ai_followed: boolean } | null;
  roles: Role[];
  crisis: { id: string; title: string; briefing: string; ai_recommendation_choice_id: string; choices: { id: string; title: string; description: string }[] } | null;
  private_intelligence: Partial<Record<Role, string>>;
  host_id: string;
  you: string;
  metrics: Civilization;
  players: { id: string; callsign: string; connected: boolean; roles: Role[] }[];
}

export type MissionIntent = { type: 'chat'; text: string } | { type: 'vote'; round_id: string; choice_id: string };
export interface ClockSample { serverNow: number; receivedAt: number }

export interface CrisisResult {
  briefing?: string;
  choices?: { id: string; title: string; description: string }[];
  ai_recommendation_choice_id?: string;
  voting_rounds?: RecordedRound[];
  consensus_window_occurred?: boolean;
  final_vote_occurred?: boolean;
  status?: 'resolved' | 'collapsed';
  id: string;
  crisis_id: string;
  crisis_number: number;
  crisis_title: string;
  choice_title: string;
  choice_description: string;
  outcome: string;
  decision: NonNullable<LobbyState['decision']>;
  before: Civilization;
  after: Civilization;
  authored_deltas: Civilization;
  applied_deltas: Civilization;
}

export interface RecordedRound {
  round_id: string;
  number: number;
  totals: Record<string, number>;
  abstentions: number;
  eligible_count: number;
}
export interface MetricSnapshot { crisis_number: number; metrics: Civilization }
export interface MissionSummary {
  narrative_outcome?: string;
  notable_decisions?: {crisis_number: number; crisis_title: string; choice_title: string; outcome: string}[];
  outcome: 'victory' | 'defeat';
  crises_completed: number;
  total_crises: number;
  final_metrics: Civilization;
  consensus_score: number;
  consensus_windows: number;
  final_vote_crises: number;
  resolution_breakdown: Record<CrisisResult['decision']['reason'], number>;
}
