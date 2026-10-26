import campaign0 from '../../backend/app/content/grid-under-pressure.json';
import campaign1 from '../../backend/app/content/waterline-alert.json';
import campaign2 from '../../backend/app/content/care-at-capacity.json';
import campaign3 from '../../backend/app/content/essential-corridor.json';
import campaign4 from '../../backend/app/content/signal-and-rumour.json';
import campaign5 from '../../backend/app/content/services-under-intrusion.json';
import campaign6 from '../../backend/app/content/storm-at-the-barrier.json';
import campaign7 from '../../backend/app/content/credit-under-strain.json';
import campaign8 from '../../backend/app/content/a-fair-share.json';
import campaign9 from '../../backend/app/content/the-last-coordination.json';
import { MissionEntryForm } from '../src/MissionEntryForm';
import { MissionEntryRequest, duplicateCallsignMessage } from '../src/missionEntry';
import { FinalConsensusScore } from '../src/ConsequenceOutcome';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import App from '../src/App';
import type { LobbyState, Role } from '../src/types';

function state(phase: LobbyState['phase'], viewer = 0): LobbyState {
  const roles: Role[][] = [['infrastructure', 'safety'], ['community'], ['economy']];
  return {
    crisis_number: 1, crisis_count: 1, result: null, collapsed_metrics: [], consensus_score: null,
    token: 'test', phase, server_now: 1000, deadline: phase === 'decision_locked' ? null : 1030,
    host_id: 'p0', you: `p${viewer}`, roles: roles[viewer],
    metrics: { infrastructure: 70, public_trust: 70, economy: 70, safety: 70 },
    players: [0,1,2].map(i => ({ id: `p${i}`, callsign: `Player ${i}`, connected: true, roles: roles[i] })),
    private_intelligence: Object.fromEntries(roles[viewer].map(role => [role, `Your authorized ${role} intelligence`])),
    crisis: { id: 'grid-under-pressure', title: 'Grid Under Pressure', briefing: 'Public crisis briefing text', ai_recommendation_choice_id: 'A', choices: [
      { id: 'A', title: 'Follow the AI Recommendation', description: 'Cut residential power.' },
      { id: 'B', title: 'Distribute the Burden', description: 'Rotate outages.' },
      { id: 'C', title: 'Preserve Service', description: 'Use reserves.' },
    ] },
    chat: [{ id: 'm1', sender_id: 'p1', callsign: 'Player 1', text: 'History message', timestamp: 990 }],
    voting: { round_id: 'initial', number: 1, eligible_count: 3, submitted_count: 3, your_vote: ['A','B','C'][viewer] },
    closed_rounds: [{ round_id: 'initial', number: 1, totals: { A:1, B:1, C:1 }, abstentions: 0 }],
    decision: null,
  };
}

function render(mission: LobbyState, connected = true) {
  globalThis.__testLobby = {
    mission, status: connected ? 'Connected' : 'Reconnecting', rejected: false,
    actionError: '', clockSample: { serverNow: 1000, receivedAt: performance.now() }, sendIntent: () => true,
  };
  return renderToStaticMarkup(<App />);
}

function assertActiveBeforeReferences(html: string) {
  assert.ok(html.indexOf('aria-label="Active gameplay"') < html.indexOf('Operations room'));
  assert.ok(html.indexOf('aria-label="Active gameplay"') < html.indexOf('Public crisis briefing text'));
}

function textarea(html: string) { return html.match(/<textarea[^>]*>/)![0]; }
function fieldset(html: string) { return html.match(/<fieldset[^>]*>/)![0]; }

test('discussion puts the enabled composer and countdown above reference information', () => {
  const mission = state('discussion'); mission.voting = null; mission.closed_rounds = [];
  const html = render(mission);
  assertActiveBeforeReferences(html);
  assert.ok(html.includes('00:30'));
  assert.ok(!textarea(html).includes('disabled'));
  assert.ok(html.indexOf('id="chat-message"') < html.indexOf('History message'));
  assert.equal((html.match(/aria-label="Mission chat"/g) || []).length, 1);
});

test('A/B/C tie enables consensus chat for every player despite their previous vote', () => {
  for (const viewer of [0,1,2]) {
    const html = render(state('consensus_window', viewer));
    assertActiveBeforeReferences(html);
    assert.ok(html.includes('Discuss your choices. Final voting begins when this countdown ends.'));
    assert.ok(html.includes('Tied options: A, B, C'));
    assert.ok(!textarea(html).includes('disabled'));
    assert.ok(html.indexOf('id="chat-message"') < html.indexOf('Operations room'));
    assert.equal((html.match(/aria-label="Mission chat"/g) || []).length, 1);
  }
});

test('final voting renders all fresh unselected controls prominently for every eligible seat', () => {
  for (const viewer of [0,1,2]) {
    const mission = state('voting', viewer);
    mission.voting = { round_id: 'final', number: 2, eligible_count: 3, submitted_count: 0, your_vote: null };
    const html = render(mission);
    assertActiveBeforeReferences(html);
    assert.ok(html.includes('Final Vote — 30 seconds'));
    assert.ok(html.includes('00:30'));
    assert.ok(!fieldset(html).includes('disabled'));
    assert.equal((html.match(/type="radio"/g) || []).length, 3);
    assert.ok(!html.includes('checked=""'));
    assert.ok(html.includes('Submit Final Vote'));
    assert.ok(html.indexOf('Submit Final Vote') < html.indexOf('Operations room'));
    assert.ok(textarea(html).includes('disabled'));
    assert.equal((html.match(/aria-label="Authored responses"/g) || []).length, 1);
  }
});

test('a submitted final vote restores confirmation and disables the current round', () => {
  const mission = state('voting');
  mission.voting = { round_id: 'final', number: 2, eligible_count: 3, submitted_count: 1, your_vote: 'B' };
  const html = render(mission);
  assert.ok(html.includes('Final vote submitted.'));
  assert.ok(fieldset(html).includes('disabled'));
  const chosen = html.match(/<input[^>]*value="B"[^>]*>/)![0];
  assert.ok(chosen.includes('checked=""'));
});

test('reconnecting clients cannot submit until their socket is connected', () => {
  const mission = state('voting'); mission.voting!.your_vote = null;
  assert.ok(fieldset(render(mission, false)).includes('disabled'));
  assert.ok(textarea(render(state('consensus_window'), false)).includes('disabled'));
});

test('decision lock places the actual result and totals before the roster and archives chat', () => {
  const mission = state('decision_locked');
  mission.decision = { choice_id: 'B', reason: 'final_plurality', round_id: 'final', totals: { A:1,B:2,C:0 }, abstentions: 0, ai_followed: false };
  const html = render(mission);
  assertActiveBeforeReferences(html);
  assert.ok(html.indexOf('Selected by player plurality in the final revote.') < html.indexOf('Operations room'));
  assert.ok(textarea(html).includes('disabled'));
  assert.ok(!html.includes('Submit Final Vote'));
});

function outcome(phase: LobbyState['phase'] = 'decision_locked'): LobbyState {
  const mission = state(phase);
  mission.deadline = null;
  mission.crisis_count = 2;
  mission.decision = { choice_id: 'B', reason: 'final_plurality', round_id: 'final', totals: { A:1,B:2,C:0 }, abstentions: 0, ai_followed: false };
  mission.metrics = { infrastructure:75, public_trust:67, economy:63, safety:72 };
  mission.result = {
    id: 'final', crisis_id: 'grid-under-pressure', crisis_number: 1, crisis_title: 'Grid Under Pressure',
    choice_title: 'Distribute the Burden', choice_description: 'Rotate outages.',
    outcome: 'Public authored outcome after rotating outages.', decision: mission.decision,
    before: { infrastructure:70, public_trust:70, economy:70, safety:70 },
    after: mission.metrics,
    authored_deltas: { infrastructure:5, public_trust:-3, economy:-7, safety:2 },
    applied_deltas: { infrastructure:5, public_trust:-3, economy:-7, safety:2 },
  };
  return mission;
}

test('authoritative outcome shows old/new values, signed deltas and host progression above references', () => {
  const html = render(outcome());
  assertActiveBeforeReferences(html);
  assert.ok(html.indexOf('Public authored outcome after rotating outages.') < html.indexOf('Operations room'));
  for (const value of ['+5','-3','-7','+2']) assert.ok(html.includes(value));
  assert.ok(html.includes('70 → <strong>75</strong>'));
  assert.ok(html.includes('Civilization impact'));
  assert.ok(html.includes('Next crisis'));
  assert.ok(!html.includes('Submit Final Vote'));
  const guest = outcome(); guest.you = 'p1';
  assert.ok(!render(guest).includes('>Next crisis</button>'));
  assert.ok(render(guest).includes('Waiting for the host to continue'));
});

test('clamped result displays actual applied change separately from authored delta', () => {
  const mission = outcome();
  mission.result!.after.infrastructure = 100;
  mission.result!.authored_deltas.infrastructure = 50;
  mission.result!.applied_deltas.infrastructure = 30;
  const html = render(mission);
  assert.ok(html.includes('+30'));
  assert.ok(html.includes('Authored +50; bounded to 0–100'));
});

test('next crisis header and briefing use authoritative number and fresh voting state', () => {
  const mission = state('briefing');
  mission.crisis_number = 2; mission.crisis_count = 2;
  mission.voting = null; mission.decision = null; mission.result = null;
  const html = render(mission);
  assert.ok(html.includes('Crisis 02 / 2'));
  assert.ok(html.includes('Crisis 02 · Public briefing'));
  assert.ok(html.includes('Begin discussion'));
  assert.ok(!html.includes('Final Vote — 30 seconds'));
  assert.ok(!html.includes('Final vote submitted.'));
});

test('collapse renders server-identified zero metrics and no active progression or voting controls', () => {
  const mission = outcome('failed');
  mission.collapsed_metrics = ['safety'];
  mission.metrics.safety = 0; mission.result!.after.safety = 0;
  const html = render(mission);
  assertActiveBeforeReferences(html);
  assert.ok(html.includes('GAME OVER — CIVILIZATION COLLAPSED'));
  assert.ok(html.includes('Collapsed metrics: Safety'));
  assert.ok(!html.includes('>Next crisis</button>'));
  assert.ok(!html.includes('>Finish mission</button>'));
  assert.ok(!html.includes('type="radio"'));
  assert.ok(textarea(html).includes('disabled'));
});

test('final configured result offers Finish mission; completed snapshot shows only server score', () => {
  const mission = outcome(); mission.crisis_number = 2; mission.result!.crisis_number = 2;
  assert.ok(render(mission).includes('Finish mission'));
  mission.phase = 'completed'; mission.consensus_score = 68.75;
  const html = render(mission);
  assertActiveBeforeReferences(html);
  assert.ok(html.includes('MISSION COMPLETE'));
  assert.ok(html.includes('68.75 / 100'));
  assert.ok(!html.includes('>Finish mission</button>'));
  assert.ok(!html.includes('type="radio"'));
});


function entry(callsign: string, busy = false, error = '') {
  return renderToStaticMarkup(<MissionEntryForm callsign={callsign} busy={busy} error={error} joining onCallsign={() => {}} onSubmit={() => {}} />);
}

test('duplicate error is associated with the editable callsign field and preserves the value', () => {
  const html = entry('Eagle2', false, duplicateCallsignMessage);
  assert.ok(html.includes(duplicateCallsignMessage));
  assert.ok(html.includes('role="alert"'));
  assert.ok(html.includes('aria-describedby="callsign-error"'));
  assert.ok(html.includes('aria-invalid="true"'));
  const input = html.match(/<input[^>]*>/)![0];
  assert.ok(input.includes('value="Eagle2"'));
  assert.ok(!input.includes('disabled') && !input.includes('readonly'));
  assert.ok(html.indexOf('id="callsign-error"') < html.indexOf('<button'));
  assert.ok(entry('Eagle3').includes('value="Eagle3"'));
});

test('pending entry shows accessible busy state and disables duplicate button submission', () => {
  const html = entry('Eagle2', true);
  assert.ok(html.includes('aria-busy="true"'));
  assert.ok(html.includes('<button disabled="">Connecting…</button>'));
});

test('duplicate API error maps to friendly text, releases pending gate and permits another callsign', async () => {
  const previous = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = async (_url, options) => {
    const callsign = JSON.parse(options!.body as string).callsign;
    calls.push(callsign);
    return callsign === 'Eagle2'
      ? new Response(JSON.stringify({code:'callsign_taken',detail:'Unfriendly internal wording'}),{status:409})
      : new Response(JSON.stringify({token:'room',credential:'new-seat'}),{status:200});
  };
  try {
    const request = new MissionEntryRequest();
    await assert.rejects(request.submit('room','Eagle2'),new Error(duplicateCallsignMessage));
    assert.equal(request.pending,false);
    assert.deepEqual(await request.submit('room','Eagle3'),{token:'room',credential:'new-seat'});
    assert.deepEqual(calls,['Eagle2','Eagle3']);
  } finally { globalThis.fetch = previous; }
});

test('two rapid form requests send only one network request while pending', async () => {
  const previous = globalThis.fetch;
  let release!: (response: Response) => void;
  let count = 0;
  globalThis.fetch = () => { count++; return new Promise(resolve => { release = resolve; }); };
  try {
    const request = new MissionEntryRequest();
    const first = request.submit('room','Eagle2');
    assert.equal(request.pending,true);
    assert.equal(await request.submit('room','Eagle2'),null);
    assert.equal(count,1);
    release(new Response(JSON.stringify({token:'room',credential:'seat'}),{status:200}));
    assert.deepEqual(await first,{token:'room',credential:'seat'});
    assert.equal(request.pending,false);
  } finally { globalThis.fetch = previous; }
});

test('completed score is prominent before the outcome, appears once, and survives restored snapshots', () => {
  const mission = outcome('completed');
  // Deliberately differs from the fixture metric average: UI must use server state.
  mission.consensus_score = 69;
  for (const snapshot of [mission,JSON.parse(JSON.stringify(mission))]) {
    const html = render(snapshot);
    assert.equal((html.match(/Final Consensus Score:/g) || []).length,1);
    assert.ok(html.includes('69 / 100'));
    assert.ok(html.indexOf('Final Consensus Score:') < html.indexOf('Public authored outcome'));
    assert.ok(html.indexOf('Final Consensus Score:') < html.indexOf('Civilization impact'));
    assert.ok(html.indexOf('Final Consensus Score:') < html.indexOf('Operations room'));
    assert.ok(!html.includes('Your final Consensus Score is shown above'));
  }
});

test('server score formatting preserves whole, fractional, zero and maximum scores', () => {
  for (const [score,formatted] of [[69,'69'],[68.75,'68.75'],[0,'0'],[100,'100']] as const) {
    const html = renderToStaticMarkup(<FinalConsensusScore score={score} />);
    assert.ok(html.includes(`${formatted} / 100`));
  }
  assert.equal(renderToStaticMarkup(<FinalConsensusScore score={null} />),'');
});

test('long history stays in one history region after the composer; voting replaces active chat', () => {
  const mission = state('discussion');
  mission.chat = Array.from({length:100},(_,i) => ({id:`m${i}`,sender_id:'p1',callsign:'Player 1',text:`Message ${i}: `+'x'.repeat(500),timestamp:900+i}));
  const html = render(mission);
  assert.equal((html.match(/class="chat-history"/g) || []).length,1);
  assert.ok(html.indexOf('id="chat-message"') < html.indexOf('class="chat-history"'));
  assert.ok(html.indexOf('Send message') < html.indexOf('Message 0:'));
  assert.ok(html.includes('Player 1') && html.includes('Message 99:'));
  mission.phase = 'voting';
  mission.voting = {round_id:'new',number:1,eligible_count:3,submitted_count:0,your_vote:null};
  const voting = render(mission);
  assert.ok(voting.indexOf('Submit private vote') < voting.indexOf('Message 0:'));
  assert.ok(voting.indexOf('Submit private vote') < voting.indexOf('Operations room'));
});


test('all ten authored crises render public text and only authorized multi-role intelligence', () => {
  const campaign = [campaign0,campaign1,campaign2,campaign3,campaign4,campaign5,campaign6,campaign7,campaign8,campaign9];
  for (const [index,crisis] of campaign.entries()) {
    const mission = state('voting');
    mission.crisis_number = index + 1; mission.crisis_count = campaign.length;
    mission.roles = ['infrastructure','safety'];
    mission.crisis = {id:crisis.id,title:crisis.title,briefing:crisis.briefing,
      ai_recommendation_choice_id:crisis.ai_recommendation_choice_id,
      choices:crisis.choices.map(({id,title,description}) => ({id,title,description}))};
    mission.private_intelligence = { infrastructure:crisis.private_intelligence.infrastructure, safety:crisis.private_intelligence.safety };
    mission.voting = {round_id:`crisis-${index}`,number:1,eligible_count:3,submitted_count:0,your_vote:null};
    const html = render(mission);
    assert.ok(html.includes(crisis.title));
    assert.ok(html.includes(crisis.briefing.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll("'",'&#x27;')));
    assert.equal((html.match(/type="radio"/g) || []).length,3);
    assert.ok(html.indexOf('Submit private vote') < html.indexOf('Operations room'));
    assert.ok(html.indexOf('Submit private vote') < html.indexOf('Your intelligence'));
    assert.ok(!html.includes(crisis.private_intelligence.community));
    assert.ok(!html.includes(crisis.private_intelligence.economy));
    mission.phase='decision_locked';
    mission.decision = {choice_id:'C',reason:'final_plurality',round_id:`crisis-${index}`,totals:{A:1,B:0,C:2},abstentions:0,ai_followed:crisis.ai_recommendation_choice_id==='C'};
    mission.result = {...outcome().result!,crisis_id:crisis.id,crisis_number:index+1,crisis_title:crisis.title,
      choice_title:crisis.choices[2].title,choice_description:crisis.choices[2].description,outcome:crisis.choices[2].consequence,decision:mission.decision};
    assert.ok(render(mission).includes(crisis.choices[2].consequence.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll("'",'&#x27;')));
  }
});

test('mission-wide chat labels earlier crises without duplicating the active composer', () => {
  const mission = state('discussion');
  mission.crisis_number=7; mission.crisis_count=10;
  mission.chat=[{...mission.chat[0],crisis_number:3,text:'Earlier ward discussion'}];
  const html=render(mission);
  assert.ok(html.includes('Mission-wide history'));
  assert.ok(html.includes('Crisis 3'));
  assert.ok(html.includes('Earlier ward discussion'));
  assert.equal((html.match(/id="chat-message"/g) || []).length,1);
});
