import type { LobbyState, Metric } from './types';
import { ContinueStatus } from './MissionPresence';

const names: Record<Metric, string> = {
  infrastructure: 'Infrastructure', public_trust: 'Public Trust', economy: 'Economy', safety: 'Safety',
};
const signed = (value: number) => value > 0 ? `+${value}` : `${value}`;

export function ConsequenceOutcome({ mission, connected, continuing, onContinue }: {
  mission: LobbyState; connected: boolean; continuing: boolean; onContinue: () => void;
}) {
  const result = mission.result;
  if (!result) return null;
  return <div className="consequence-outcome">
    <p className="eyebrow">Crisis {result.crisis_number.toString().padStart(2, '0')} outcome</p>
    <p>{result.outcome}</p>
    <table className="civilization-impact">
      <caption>Civilization impact</caption>
      <thead><tr><th scope="col">Metric</th><th scope="col">Before → After</th><th scope="col">Change</th></tr></thead>
      <tbody>{(Object.keys(names) as Metric[]).map(key => <tr key={key}>
        <th scope="row">{names[key]}</th>
        <td>{result.before[key]} → <strong>{result.after[key]}</strong></td>
        <td>{signed(result.applied_deltas[key])}
          {result.applied_deltas[key] !== result.authored_deltas[key] && <small>Authored {signed(result.authored_deltas[key])}; bounded to 0–100</small>}
        </td>
      </tr>)}</tbody>
    </table>
    {mission.phase === 'failed' && <p role="status">Collapsed metrics: {mission.collapsed_metrics.map(key => names[key]).join(', ')}. The mission cannot continue.</p>}
    {mission.phase === 'decision_locked' && <>
      <p>{mission.crisis_number === mission.crisis_count ? 'All configured crises survived. Finish the mission after reviewing the outcome.' : 'Review the outcome with your team before the next crisis.'}</p>
      {mission.you === mission.host_id
        ? <button aria-describedby="continue-status" disabled={!connected || continuing || mission.players.some(player => !player.connected)} onClick={onContinue}>{mission.crisis_number === mission.crisis_count ? 'Finish mission' : 'Next crisis'}</button>
        : null}
      <ContinueStatus mission={mission} connected={connected} continuing={continuing} />
    </>}
  </div>;
}

export function FinalConsensusScore({ score }: { score: number | null }) {
  if (score === null) return null;
  return <p className="consensus-score">Final Consensus Score: <strong>{score.toLocaleString(undefined, { maximumFractionDigits: 2 })} / 100</strong></p>;
}
