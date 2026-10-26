"""Three-client delivery evidence for frontend scroll tests; controlled clocks."""
import json
from pathlib import Path

from test_campaign import CampaignClients


def chat_acceptance():
    evidence=[]
    with CampaignClients(3) as game:
        game.post('start'); _,frames=game.post('discussion')
        evidence.append(frames)
        for index in range(7):
            game.clock.now += 1
            game.sockets[0].send_json({'type':'chat','text':f'Grid observation {index+1}: compare the risks.'})
            frames=game.states()
            assert all(len(state['chat'])==index+1 for state in frames)
            assert all(state['chat'][-1]['callsign']=='Eagle1' for state in frames)
            assert all(state['chat'][-1]['crisis_number']==1 for state in frames)
            evidence.append(frames)
        # Rejection broadcasts unchanged state, then an error to the sender.
        game.sockets[0].send_json({'type':'chat','text':'Too soon'})
        rejected=game.states()
        assert all(state['chat']==frames[0]['chat'] for state in rejected)
        error=game.sockets[0].receive_json()
        assert error['type']=='error'
        assert len(game.mission.chat)==7
        frames=game.tick(); assert frames[0]['phase']=='voting'
        frames=game.votes(['B','B','A'])
        _,frames=game.post('continue',{'result_id':frames[0]['result']['id']})
        assert frames[0]['phase']=='briefing' and frames[0]['crisis_number']==2
        _,frames=game.post('discussion')
        assert len(frames[0]['chat'])==7
        evidence.append(frames)
        game.sockets[2].send_json({'type':'chat','text':'Water isolation needs accessible deliveries.'})
        frames=game.states(); evidence.append(frames)
        assert all(len(state['chat'])==8 for state in frames)
        assert all([m['crisis_number'] for m in state['chat']]==[1]*7+[2] for state in frames)
        assert all(len({m['id'] for m in state['chat']})==8 for state in frames)
    return evidence


def test_three_client_chat_delivery_rejection_voting_and_next_crisis_history():
    assert len(chat_acceptance())==10


if __name__=='__main__':
    output=Path('/tmp/ce-chat-5-1.json')
    output.write_text(json.dumps(chat_acceptance()))
    print(f'PASS: three-client discussion, 7 shared messages, rejected send, voting, next crisis and origin labels; snapshots: {output}')
