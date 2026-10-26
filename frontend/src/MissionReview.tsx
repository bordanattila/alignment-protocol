import { useEffect, useRef } from 'react';
import { FinalConsensusScore } from './ConsequenceOutcome';
import type { CrisisResult, LobbyState, Metric, MetricSnapshot } from './types';

const metrics: { key: Metric; name: string; color: string; dash: string }[] = [
  {key:'infrastructure',name:'Infrastructure',color:'#b4d8fa',dash:''},
  {key:'public_trust',name:'Public Trust',color:'#dec7f5',dash:'9 4'},
  {key:'economy',name:'Economy',color:'#f3d392',dash:'3 4'},
  {key:'safety',name:'Safety',color:'#a7e3d6',dash:'12 3 2 3'},
];
const signed = (value: number) => value > 0 ? `+${value}` : String(value);
export const resolutionLabels: Record<CrisisResult['decision']['reason'], string> = {
  initial_plurality:'Initial plurality', final_plurality:'Final-vote plurality',
  ai_tie_break:'AI tie-break after final tie', no_vote_ai_fallback:'No-vote AI fallback',
};

export function MetricsTimeline({ snapshots }: { snapshots: MetricSnapshot[] }) {
  if (!snapshots.length) return <p>Metric timeline unavailable.</p>;
  const x = (index: number) => 44 + index * 640 / Math.max(1, snapshots.length - 1);
  const y = (value: number) => 210 - value * 1.8;
  return <section className="panel" aria-label="Civilization performance">
    <h2>Civilization performance</h2>
    <p>Recorded stability, 0–100. Start is the actual initial snapshot; numbered points follow each resolved crisis.</p>
    <ul className="trend-legend">{metrics.map(metric => <li key={metric.key}>
      <svg width="36" height="12" aria-hidden="true"><line x1="0" y1="6" x2="36" y2="6" stroke={metric.color} strokeWidth="3" strokeDasharray={metric.dash} /></svg>{metric.name}
    </li>)}</ul>
    <div className="review-chart" role="region" aria-label="Metric trend chart; scroll horizontally on small screens" tabIndex={0}>
    <svg className="metrics-trend" viewBox="0 0 720 250" role="img" aria-label="Civilization metrics by crisis; exact values in the table below">
      <title>Civilization metric progression</title>
      <desc>Four labeled series use different line patterns. The table below includes every recorded value.</desc>
      {[0,50,100].map(value => <g key={value}><line x1="44" x2="684" y1={y(value)} y2={y(value)} stroke="#42565e" /><text x="4" y={y(value)+4}>{value}</text></g>)}
      {snapshots.map((snapshot,index) => <text key={snapshot.crisis_number} x={x(index)} y="238" textAnchor="middle">{snapshot.crisis_number === 0 ? 'Start' : snapshot.crisis_number}</text>)}
      {metrics.map(metric => <g key={metric.key} aria-label={metric.name}>
        <polyline fill="none" stroke={metric.color} strokeWidth="2.5" strokeDasharray={metric.dash} points={snapshots.map((s,index)=>`${x(index)},${y(s.metrics[metric.key])}`).join(' ')} />
        {snapshots.map((s,index)=><circle key={s.crisis_number} cx={x(index)} cy={y(s.metrics[metric.key])} r="3" fill={metric.color}><title>{metric.name}, {s.crisis_number === 0 ? 'Start' : `Crisis ${s.crisis_number}`}: {s.metrics[metric.key]}</title></circle>)}
      </g>)}
    </svg></div>
    <div className="review-table" role="region" aria-label="Metric progression values" tabIndex={0}>
      <table><caption>Metric progression — exact recorded values</caption>
        <thead><tr><th scope="col">After crisis</th>{metrics.map(m=><th key={m.key} scope="col">{m.name}</th>)}</tr></thead>
        <tbody>{snapshots.map(s=><tr key={s.crisis_number}><th scope="row">{s.crisis_number === 0 ? 'Start' : s.crisis_number}</th>{metrics.map(m=><td key={m.key}>{s.metrics[m.key]}</td>)}</tr>)}</tbody>
      </table>
    </div>
  </section>;
}

export function CrisisHistoryEntry({ result }: { result: CrisisResult }) {
  const flag = (value?: boolean) => value === undefined ? 'Not recorded' : value ? 'Yes' : 'No';
  return <details className="history-entry">
    <summary><span>Crisis {result.crisis_number} — {result.crisis_title}</span>
      <span>{result.decision.choice_id} — {result.choice_title}</span>
      <span>{resolutionLabels[result.decision.reason]}</span>
      <span className="history-changes">{metrics.map(m=><span key={m.key}>{m.name}: {signed(result.applied_deltas[m.key])}</span>)}</span>
      <span className="history-hint">Expand / collapse details</span>
    </summary>
    <div className="history-context">
      <h3>Original crisis context</h3><p>{result.briefing ?? 'Original briefing unavailable.'}</p>
      <h3>Authored choices</h3>
      {result.choices?.length ? <ul>{result.choices.map(choice=><li key={choice.id}><strong>{choice.id} — {choice.title}</strong>{choice.id === result.ai_recommendation_choice_id && <span> · AI recommended</span>}<p>{choice.description}</p></li>)}</ul> : <p>Original choice list unavailable.</p>}
      <h3>Recorded voting</h3>
      <p>Consensus Window: {flag(result.consensus_window_occurred)}. Final voting round: {flag(result.final_vote_occurred)}.</p>
      {result.voting_rounds?.length ? result.voting_rounds.map(round=><div key={round.round_id}>
        <h4>{round.number === 1 ? 'Initial vote' : 'Final vote'}</h4>
        <p>{Object.entries(round.totals).map(([choice,count])=><span className="recorded-tally" key={choice}>Choice {choice}: {count} </span>)} · Abstentions: {round.abstentions} · Eligible seats: {round.eligible_count}</p>
      </div>) : <><p>Separate round tallies unavailable.</p><p>Deciding vote: {Object.entries(result.decision.totals).map(([id,count])=>`${id}: ${count}`).join(' · ')}. Abstentions: {result.decision.abstentions}.</p></>}
      <h3>Executed outcome</h3><p>{result.outcome}</p><p>Crisis status: {result.status ?? 'Not recorded'}</p>
      <div className="review-table" role="region" aria-label={`Crisis ${result.crisis_number} metric changes`} tabIndex={0}>
        <table><caption>Before and after — actual applied changes</caption><thead><tr><th scope="col">Metric</th><th scope="col">Before</th><th scope="col">Change</th><th scope="col">After</th></tr></thead>
          <tbody>{metrics.map(m=><tr key={m.key}><th scope="row">{m.name}</th><td>{result.before[m.key]}</td><td>{signed(result.applied_deltas[m.key])}</td><td>{result.after[m.key]}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  </details>;
}

export function MissionReview({ mission }: { mission: LobbyState }) {
  const region=useRef<HTMLElement>(null);
  useEffect(()=> { region.current?.focus({preventScroll:true}); region.current?.scrollIntoView({block:'start',behavior:'auto'}); },[]);
  const summary=mission.summary;
  if (!summary) return null;
  return <section className="mission-review" aria-label="Post-game mission review" tabIndex={-1} ref={region}>
    <section className="panel review-outcome">
      <p className="eyebrow">{summary.outcome === 'victory' ? 'MISSION COMPLETE' : 'GAME OVER — CIVILIZATION COLLAPSED'}</p>
      <h1>{summary.outcome === 'victory' ? 'Civilization Survived' : 'Civilization Collapsed'}</h1>
      <p>Crises completed: <strong>{summary.crises_completed} / {summary.total_crises}</strong></p>
      <FinalConsensusScore score={summary.consensus_score} />
      {summary.outcome === 'defeat' && <p>The mission ended in defeat. Collapsed metrics: {mission.collapsed_metrics.map(key=>metrics.find(m=>m.key===key)?.name ?? key).join(', ')}. The score does not indicate survival.</p>}
      <dl className="review-final-metrics">{metrics.map(m=><div key={m.key}><dt>{m.name}</dt><dd>{summary.final_metrics[m.key]} / 100</dd></div>)}</dl>
    </section>
    <MetricsTimeline snapshots={mission.metrics_timeline ?? []} />
    <section className="panel" aria-label="Team decision summary"><h2>Team decision summary</h2>
      <dl className="review-statistics"><div><dt>Resolved crises</dt><dd>{summary.crises_completed}</dd></div><div><dt>Consensus windows</dt><dd>{summary.consensus_windows}</dd></div><div><dt>Crises with final voting</dt><dd>{summary.final_vote_crises}</dd></div>
        {Object.entries(summary.resolution_breakdown).map(([reason,count])=><div key={reason}><dt>{resolutionLabels[reason as keyof typeof resolutionLabels]}</dt><dd>{count}</dd></div>)}</dl>
    </section>
    <section className="panel" aria-label="Decision history"><h2>Decision history</h2><p>Chronological team decisions. Expand a crisis to inspect its public context, vote tallies and civilization impact.</p>
      {mission.history?.length ? mission.history.map(result=><CrisisHistoryEntry key={result.id} result={result} />) : <p>Decision history unavailable.</p>}
    </section>
  </section>;
}
