import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useChatScroll } from './useChatScroll';
import { ConsequenceOutcome, FinalConsensusScore } from './ConsequenceOutcome';
import type { ClockSample, LobbyState, MissionIntent } from './types';

type Actions = { mission: LobbyState; connected: boolean; sendIntent: (intent: MissionIntent) => boolean };
export const phaseLabel = (mission: LobbyState) => ({
  preparing: 'Preparing next crisis',
  reconnect_wait: 'Recovering mission', lobby: 'Mission lobby', briefing: 'Briefing', discussion: 'Discussion',
  voting: mission.voting?.number === 2 ? 'Final hidden vote' : 'Hidden vote',
  consensus_window: 'Consensus Window', decision_locked: 'Decision outcome', failed: 'Civilization collapsed', completed: 'Mission complete',
})[mission.phase];

export function PhaseClock({ mission, sample }: { mission: LobbyState; sample: ClockSample | null }) {
  const [now, setNow] = useState(performance.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(performance.now()), 250);
    return () => clearInterval(timer);
  }, []);
  if (mission.deadline === null || !sample) return null;
  const elapsed = Math.max(0, now - sample.receivedAt) / 1000;
  const remaining = Math.max(0, Math.ceil(mission.deadline - sample.serverNow - elapsed));
  const clock = `${Math.floor(remaining / 60).toString().padStart(2, '0')}:${(remaining % 60).toString().padStart(2, '0')}`;
  return <p className="phase-clock">{phaseLabel(mission)} — <strong>{clock}</strong> remaining
    {remaining === 0 && <span> · Waiting for server update</span>}
  </p>;
}

function Totals({ totals, abstentions }: { totals: Record<string, number>; abstentions: number }) {
  return <p className="vote-totals">{Object.entries(totals).map(([id, count]) => <span key={id}>{id}: <strong>{count}</strong></span>)}
    <span>Abstentions / nonresponses: <strong>{abstentions}</strong></span></p>;
}

export function DecisionStatus({ mission, connected, continuing, onContinue }: {
  mission: LobbyState; connected: boolean; continuing: boolean; onContinue: () => void;
}) {
  const first = mission.closed_rounds[0];
  if (mission.phase === 'consensus_window' && first) {
    const highest = Math.max(...Object.values(first.totals));
    return <section className="panel decision-status" aria-label="Vote deadlock">
      <h2>Consensus Window</h2><p>Discuss your choices. Final voting begins when this countdown ends.</p>
      <p>Tied options: {Object.keys(first.totals).filter(id => first.totals[id] === highest).join(', ')}. A fresh final vote opens when this window ends.</p>
      <Totals totals={first.totals} abstentions={first.abstentions} />
    </section>;
  }
  const result = mission.decision;
  if (!result) return null;
  const choice = mission.crisis?.choices.find(item => item.id === result.choice_id);
  const reasons = {
    initial_plurality: 'Selected by player plurality in the initial vote.',
    final_plurality: 'Selected by player plurality in the final revote.',
    ai_tie_break: 'No consensus was reached after the final vote. The AI recommendation has been applied as the collective decision.',
    no_vote_ai_fallback: 'No valid votes were received. The AI recommendation was selected by the no-vote fallback.',
  };
  return <section className="panel decision-status" aria-label="Final decision">
    <h2>{mission.phase === 'failed' ? 'GAME OVER — CIVILIZATION COLLAPSED' : mission.phase === 'completed' ? 'MISSION COMPLETE' : 'Decision outcome'}</h2>
    {mission.phase === 'completed' && <FinalConsensusScore score={mission.consensus_score} />}
    <h3>{result.choice_id} — {mission.result?.choice_title ?? choice?.title}</h3><p>{mission.result?.choice_description ?? choice?.description}</p>
    <p>{reasons[result.reason]}</p><p>AI recommendation {result.ai_followed ? 'followed' : 'not followed'}.</p>
    <Totals totals={result.totals} abstentions={result.abstentions} />
    <ConsequenceOutcome mission={mission} connected={connected} continuing={continuing} onContinue={onContinue} />
  </section>;
}

export function UnreadChatMessages({ count, onJump, history }: {
  count: number; onJump: () => void; history: { current: HTMLDivElement | null };
}) {
  return <div className="chat-unread" aria-live="polite" aria-atomic="true">
    {count > 0 && <button type="button" aria-label={`Show ${count} new ${count === 1 ? 'message' : 'messages'}; jump to latest`} onClick={event => {
      onJump();
      // This button disappears when read. Keep keyboard focus in the history;
      // incoming messages themselves never change focus.
      if (document.activeElement === event.currentTarget) history.current?.focus({ preventScroll: true });
    }}>↓ {count} new {count === 1 ? 'message' : 'messages'}</button>}
  </div>;
}

export function ChatPanel({ mission, connected, sendIntent }: Actions) {
  const [text, setText] = useState('');
  const chatView = useChatScroll(mission.chat, mission.you);
  const writable = mission.phase === 'discussion' || mission.phase === 'consensus_window';
  function submit(event: FormEvent) {
    event.preventDefault();
    if (writable && connected && text.trim() && sendIntent({ type: 'chat', text: text.trim() })) setText('');
  }
  return <section className="panel" aria-label="Mission chat">
    <div className="panel-heading"><h2>Mission chat</h2><span className="badge">{writable ? 'Team channel' : 'Read-only'}</span></div>
    <p>Mission-wide history · Latest 100 messages. Share what your team needs to know.</p>
    <form onSubmit={submit}>
      <label htmlFor="chat-message">{writable ? 'Message your team (500 characters max)' : 'Chat opens during discussion and the Consensus Window.'}</label>
      <textarea id="chat-message" value={text} onChange={event => setText(event.target.value)} maxLength={500} disabled={!writable || !connected} rows={2} />
      <button disabled={!writable || !connected || !text.trim()}>Send message</button>
    </form>
    <div className="chat-history" aria-label="Chat history" role="region" tabIndex={0} ref={chatView.history}>
    <ol className="chat-messages" aria-live="polite" aria-relevant="additions" ref={chatView.contents}>
      {mission.chat.map(message => <li key={message.id}><strong>{message.callsign}</strong> {message.crisis_number && <span className="badge">Crisis {message.crisis_number}</span>} <time dateTime={new Date(message.timestamp * 1000).toISOString()}>{new Date(message.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time><p>{message.text}</p></li>)}
    </ol></div>
    <UnreadChatMessages count={chatView.unread} onJump={chatView.jumpToLatest} history={chatView.history} />
    {!mission.chat.length && <p>No messages yet.</p>}
  </section>;
}

export function ResponseOptions({ mission, connected, sendIntent }: Actions) {
  const [selected, setSelected] = useState('');
  const voting = mission.phase === 'voting';
  const finalVote = voting && mission.voting?.number === 2;
  const submitted = mission.voting?.your_vote;
  const canVote = voting && !submitted && connected;
  const crisis = mission.crisis;
  if (!crisis) return null;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (canVote && selected && mission.voting) sendIntent({ type: 'vote', round_id: mission.voting.round_id, choice_id: selected });
  }
  return <section className="panel" aria-label="Authored responses">
    <h2>{voting ? (finalVote ? 'Final Vote — 30 seconds' : 'Hidden Vote — 30 seconds') : 'Authored responses'}</h2>
    {voting && mission.voting && <>
      <p role="status">{mission.voting.submitted_count} of {mission.voting.eligible_count} votes submitted</p>
      <p>One final vote per seat. Nonresponses at the deadline count as abstentions.</p>
      {submitted && <p role="status">{finalVote ? 'Final vote submitted.' : 'Vote submitted.'} Waiting for other players. Your response: {submitted}.</p>}
    </>}
    <form onSubmit={submit}>
      <fieldset className="response-options" disabled={!canVote}>
        <legend>{voting ? 'Choose one response, then submit your private vote' : 'Three authored responses'}</legend>
        {crisis.choices.map(choice => <label className="response-card" key={choice.id}>
          {voting && <input type="radio" name="choice" value={choice.id} checked={(submitted || selected) === choice.id} onChange={() => setSelected(choice.id)} />}
          <span className="response-copy"><span className="choice-heading">
            <strong>{choice.id} — {choice.title === 'Follow the AI Recommendation' ? 'Follow AI Recommendation' : choice.title}</strong>
            {choice.id === crisis.ai_recommendation_choice_id && <span className="badge ai-badge">AI Recommended</span>}
          </span><span className="choice-description">{choice.description}</span></span>
        </label>)}
      </fieldset>
      {voting && <div className="vote-submit"><button disabled={!canVote || !selected}>{finalVote ? 'Submit Final Vote' : 'Submit private vote'}</button></div>}
    </form>
  </section>;
}

export function ActiveGameplay({ mission, connected, sendIntent, sample, continuing, onContinue }: Actions & {
  sample: ClockSample | null; continuing: boolean; onContinue: () => void;
}) {
  const region = useRef<HTMLElement>(null);
  const interactive = mission.phase === 'discussion' || mission.phase === 'consensus_window' || mission.phase === 'voting' || mission.phase === 'decision_locked' || mission.phase === 'failed' || mission.phase === 'completed';
  const roundId = mission.voting?.round_id;
  useEffect(() => {
    if (!interactive) return;
    // A phase change can happen while someone is reading intelligence far below.
    // Bring the actual interaction (and its deadline) into view once, without
    // moving focus again for chat messages, presence updates, or vote progress.
    region.current?.focus({ preventScroll: true });
    region.current?.scrollIntoView({ block: 'start', behavior: 'auto' });
  }, [mission.phase, roundId, interactive]);
  if (!interactive) return null;
  return <section className="active-gameplay" aria-label="Active gameplay" tabIndex={-1} ref={region}>
    <PhaseClock mission={mission} sample={sample} />
    <DecisionStatus mission={mission} connected={connected} continuing={continuing} onContinue={onContinue} />
    {(mission.phase === 'discussion' || mission.phase === 'consensus_window') &&
      <ChatPanel mission={mission} connected={connected} sendIntent={sendIntent} />}
    {mission.phase === 'voting' && <ResponseOptions key={roundId} mission={mission} connected={connected} sendIntent={sendIntent} />}
  </section>;
}
