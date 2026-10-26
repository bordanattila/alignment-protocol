import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import App from '../src/App';
import type { LobbyState, Role } from '../src/types';

function state(phase: LobbyState['phase'], viewer = 0): LobbyState {
  const roles: Role[][] = [['infrastructure', 'safety'], ['community'], ['economy']];
  return {
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
