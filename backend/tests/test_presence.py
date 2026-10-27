"""Existing server-owned socket presence, reconnect races and progression gates."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocket

from app.connections import LobbyConnections
from app.domain import Phase
from app.missions import MissionError, MissionStore
from test_milestone3 import Clock
from test_persistence import team, voting, votes, restart


def test_joined_seats_are_offline_until_authenticated_and_broadcasts_restore_presence():
    async def run():
        store=MissionStore(); mission,host=store.create('Host'); _,guest=store.join(mission.token,'Guest')
        assert not any(p.connected for p in mission.players)
        connections=LobbyConnections(store); a=AsyncMock(spec=WebSocket); b=AsyncMock(spec=WebSocket)
        connections.add(mission.token,host.id,a); await connections.broadcast(mission.token)
        first=a.send_json.call_args.args[0]['mission']
        assert [p['connected'] for p in first['players']]==[True,False]
        connections.add(mission.token,guest.id,b); await connections.broadcast(mission.token)
        assert all(p['connected'] for p in a.send_json.call_args.args[0]['mission']['players'])
        connections.remove(mission.token,guest.id,b); await connections.broadcast(mission.token)
        offline=a.send_json.call_args.args[0]['mission']
        assert [p['connected'] for p in offline['players']]==[True,False]
        replacement=AsyncMock(spec=WebSocket); connections.add(mission.token,guest.id,replacement)
        await connections.broadcast(mission.token)
        restored=replacement.send_json.call_args.args[0]['mission']
        assert [p['id'] for p in restored['players']]==[host.id,guest.id]
        assert all(p['connected'] for p in restored['players'])
        assert first['revision']<offline['revision']<restored['revision']
    asyncio.run(run())


def test_superseded_socket_cleanup_never_marks_a_live_seat_offline():
    store=MissionStore(); mission,host=store.create('Host'); connections=LobbyConnections(store)
    old,new=AsyncMock(spec=WebSocket),AsyncMock(spec=WebSocket)
    connections.add(mission.token,host.id,old); connections.add(mission.token,host.id,new)
    connections.remove(mission.token,host.id,old)
    connections.remove(mission.token,host.id,old)  # delayed cleanup is idempotent
    assert host.connected and connections.sockets[mission.token][host.id]=={new}
    connections.remove(mission.token,host.id,new)
    assert not host.connected and not connections.sockets


def test_presence_broadcasts_are_mission_scoped_and_public_roster_contains_no_secrets():
    async def run():
        store=MissionStore(); first,host=store.create('First'); second,other=store.create('Second')
        connections=LobbyConnections(store); a,b=AsyncMock(spec=WebSocket),AsyncMock(spec=WebSocket)
        connections.add(first.token,host.id,a); connections.add(second.token,other.id,b)
        await connections.broadcast(first.token)
        b.send_json.assert_not_awaited()
        state=a.send_json.call_args.args[0]['mission']
        assert [p['id'] for p in state['players']]==[host.id]
        assert other.id not in json.dumps(state) and other.callsign not in json.dumps(state)
        assert host.credential not in json.dumps(state)
        assert set(state['players'][0])=={'id','callsign','connected','roles'}
        with pytest.raises(MissionError): store.project(first.token,other.id)
    asyncio.run(run())


@pytest.mark.parametrize('finished',[False,True])
def test_restart_resets_presence_then_restores_original_seats_and_private_projections(tmp_path,finished):
    path=tmp_path/'presence.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    if finished:
        for choice in 'BBBCCBCAAC':
            voting(store,mission,credentials,clock); votes(store,mission,credentials,[choice]*3)
            store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
        assert mission.phase==Phase.COMPLETED
    identities=[(p.id,p.roles.copy()) for p in mission.players]
    token=mission.token; store=restart(store,path,clock)
    try:
        recovered=store.get(token); assert not any(p.connected for p in recovered.players)
        connections=LobbyConnections(store)
        for index,credential in enumerate(credentials):
            player=store.authorize(token,credential); connections.add(token,player.id,AsyncMock(spec=WebSocket))
            state=store.project(token,player.id)
            assert sum(p['connected'] for p in state['players'])==index+1
            assert [(p.id,p.roles) for p in recovered.players]==identities
            assert state['private_intelligence']=={role:recovered.crisis.private_intelligence[role] for role in player.roles}
            for role,secret in recovered.crisis.private_intelligence.items():
                assert (secret in json.dumps(state))==(role in player.roles)
            assert not any(c in json.dumps(state) for c in credentials)
        if finished: assert state['summary']['outcome']=='victory'
    finally: store.close()


def test_missing_vote_is_nonresponse_and_next_crisis_requires_every_assigned_seat(tmp_path):
    path=tmp_path/'vote.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    try:
        voting(store,mission,credentials,clock); round_id=mission.rounds[-1].id; deadline=mission.deadline
        roles=[p.roles.copy() for p in mission.players]
        store.set_connected(mission.token,mission.players[2].id,False)
        for credential in credentials[:2]: store.vote(mission.token,credential,round_id,'B')
        assert mission.phase==Phase.VOTING and mission.deadline==deadline
        clock.now=deadline; store.advance_due(mission.token)
        assert mission.phase==Phase.DECISION_LOCKED
        assert mission.rounds[-1].abstentions==1 and mission.decision.totals=={'A':0,'B':2,'C':0}
        with pytest.raises(MissionError): store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
        with pytest.raises(MissionError): store.vote(mission.token,credentials[2],round_id,'C')
        assert len(mission.results)==1
        store.set_connected(mission.token,mission.players[2].id,True)
        assert [p.roles for p in mission.players]==roles
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
        assert mission.phase==Phase.BRIEFING and mission.crisis_index==1
    finally: store.close()
