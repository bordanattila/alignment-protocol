"""Three-seat regression for the reported A/B/C consensus-to-final cycle."""
import pytest
from fastapi.testclient import TestClient

from app.domain import Phase
from app.main import create_app
from test_foundation import authenticate, create
from test_milestone3 import Clock, setup, expire, cast


@pytest.mark.parametrize('final_votes,reason,winner', [
    (['B','B','A'], 'final_plurality', 'B'),
    (['A','B','C'], 'ai_tie_break', 'A'),
    ([], 'no_vote_ai_fallback', 'A'),
])
def test_three_players_have_a_fresh_full_final_opportunity(final_votes, reason, winner):
    store, mission, clock = setup(3)
    expire(store, mission, clock)
    cast(store, mission, ['A','B','C'])
    assert mission.phase == Phase.CONSENSUS_WINDOW
    first_votes = dict(mission.rounds[0].votes)
    consensus_started = clock.now
    assert mission.deadline == consensus_started + 20
    for player in mission.players:
        store.send_chat(mission.token, player.credential, f'Reconsider: {player.callsign}')
    for player in mission.players:
        assert len(store.project(mission.token, player.id)['chat']) == 3
    clock.now = consensus_started + 19.999
    assert not store.advance_due(mission.token)
    expire(store, mission, clock)
    final_started = clock.now
    assert mission.phase == Phase.VOTING
    assert len(mission.rounds) == 2 and mission.rounds[1].votes == {}
    assert mission.deadline == final_started + 30
    for player in mission.players:
        state = store.project(mission.token, player.id)
        assert state['voting']['number'] == 2
        assert state['voting']['your_vote'] is None
        assert state['voting']['eligible_count'] == 3
    assert not store.advance_due(mission.token)
    clock.now = final_started + 29.999
    assert not store.advance_due(mission.token)
    assert mission.phase == Phase.VOTING and mission.decision is None
    cast(store, mission, final_votes)
    if not final_votes:
        expire(store, mission, clock)
    assert mission.decision.reason == reason
    assert mission.decision.choice_id == winner
    assert mission.decision.abstentions == (0 if final_votes else 3)
    assert mission.rounds[0].votes == first_votes
    assert mission.rounds[1].votes == {player.id: choice for player, choice in zip(mission.players, final_votes)}
    assert mission.rounds[1].votes is not mission.rounds[0].votes
    assert mission.phase == Phase.DECISION_LOCKED


def test_delayed_consensus_tick_still_opens_a_full_final_round():
    store, mission, clock = setup(3)
    expire(store, mission, clock)
    cast(store, mission, ['A','B','C'])
    clock.now = mission.deadline + 100
    assert store.advance_due(mission.token)
    assert mission.phase == Phase.VOTING
    assert mission.deadline == clock.now + 30
    assert mission.decision is None
    assert not store.advance_due(mission.token)


def test_three_player_transport_consensus_chat_final_plurality_and_reconnect():
    clock = Clock()
    app = create_app(clock)
    with TestClient(app) as client:
        host = create(client)
        token = host['token']
        guests = [client.post(f'/api/missions/{token}/join', json={'callsign': name}).json() for name in ['Lee','Chen']]
        url = f'/api/missions/{token}/ws'
        headers = {'X-Mission-Session': host['credential']}
        with client.websocket_connect(url) as first, client.websocket_connect(url) as second:
            authenticate(first, host['credential'])
            authenticate(second, guests[0]['credential'])
            first.receive_json()
            def frames(sockets):
                result = [s.receive_json()['mission'] for s in sockets]
                assert all(s['phase'] == result[0]['phase'] for s in result)
                return result
            def tick(sockets):
                async def advance():
                    async with app.state.lock:
                        clock.now = app.state.missions.get(token).deadline
                    await app.state.tick()
                client.portal.call(advance)
                return frames(sockets)
            def vote(socket, round_id, choice, sockets):
                socket.send_json({'type':'vote','round_id':round_id,'choice_id':choice})
                return frames(sockets)
            with client.websocket_connect(url) as third:
                authenticate(third, guests[1]['credential'])
                first.receive_json(); second.receive_json()
                sockets = [first,second,third]
                for endpoint in ['start','discussion']:
                    assert client.post(f'/api/missions/{token}/{endpoint}', headers=headers).status_code == 200
                    frames(sockets)
                initial = tick(sockets)
                initial_id = initial[0]['voting']['round_id']
                for socket, choice in zip(sockets, ['A','B','C']):
                    consensus = vote(socket, initial_id, choice, sockets)
                assert all(s['phase'] == 'consensus_window' for s in consensus)
                assert consensus[0]['closed_rounds'][0]['totals'] == {'A':1,'B':1,'C':1}
                consensus_deadline = consensus[0]['deadline']
                third.send_json({'type':'chat','text':'Let us distribute the burden.'})
                for state in frames(sockets):
                    assert state['chat'][-1]['callsign'] == 'Chen'
                    assert state['chat'][-1]['text'] == 'Let us distribute the burden.'
            assert not frames([first,second])[0]['players'][2]['connected']
            with client.websocket_connect(url) as third:
                restored = authenticate(third, guests[1]['credential'])
                assert restored['phase'] == 'consensus_window'
                assert restored['deadline'] == consensus_deadline
                assert restored['voting']['your_vote'] == 'C'
                frames([first,second])
                sockets = [first,second,third]
                final = tick(sockets)
                final_id = final[0]['voting']['round_id']
                assert final_id != initial_id
                assert all(s['phase'] == 'voting' and s['voting']['number'] == 2 for s in final)
                assert all(s['voting']['your_vote'] is None for s in final)
                assert final[0]['deadline'] - final[0]['server_now'] == 30
                final_deadline = final[0]['deadline']
                vote(first, final_id, 'B', sockets)
                partial = vote(third, final_id, 'A', sockets)
                assert partial[2]['voting']['your_vote'] == 'A'
                assert partial[1]['voting']['your_vote'] is None
            frames([first,second])
            with client.websocket_connect(url) as third:
                restored = authenticate(third, guests[1]['credential'])
                assert restored['phase'] == 'voting' and restored['voting']['number'] == 2
                assert restored['voting']['your_vote'] == 'A'
                assert restored['deadline'] == final_deadline
                frames([first,second])
                results = vote(second, final_id, 'B', [first,second,third])
                assert all(s['phase'] == 'decision_locked' for s in results)
                assert all(s['decision'] == results[0]['decision'] for s in results)
                assert results[0]['decision']['reason'] == 'final_plurality'
                assert results[0]['decision']['choice_id'] == 'B'
                assert results[0]['decision']['totals'] == {'A':1,'B':2,'C':0}
                assert results[0]['decision']['abstentions'] == 0
