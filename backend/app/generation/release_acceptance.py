"""Exactly one authorized synthetic release request; no live mission database."""
import argparse
import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from .config import GenerationSettings
from .context import build_context
from .contract import GenerationRequest
from .release_budget import ReleaseBudget,BoundedReleaseProvider
from .service import GenerationService,authored_selector
from ..campaign import load_campaign_catalog
from ..domain import GenerationDiagnostic
from ..missions import MissionStore
from ..persistence import SQLiteMissions


async def run(path, settings=None, client=None):
    budget=ReleaseBudget(path)
    status=budget.status()
    if status['phase']!='acceptance' or status['attempts']!=0 or status['halted']:
        raise RuntimeError('The single acceptance request is unavailable or already consumed.')
    settings=settings or GenerationSettings.from_env()
    if not settings.enabled:raise RuntimeError('Generation must be explicitly enabled for acceptance.')
    provider=BoundedReleaseProvider(settings,budget,client)
    with tempfile.TemporaryDirectory(prefix='ce-release-synthetic-') as directory:
        db=Path(directory)/'synthetic.sqlite3'
        store=MissionStore(persistence=SQLiteMissions(db),campaign_loader=load_campaign_catalog,generation_enabled=True)
        store.initialize()
        try:
            mission,host=store.create('Synthetic Host','generated')
            _,guest=store.join(mission.token,'Synthetic Guest')
            credentials=(host.credential,guest.credential)
            for player in mission.players:store.set_connected(mission.token,player.id,True)
            store.start(mission.token,credentials[0])
            outcome=await GenerationService(settings,provider,authored_selector(mission.campaign,0,[])).generate(
                GenerationRequest(context=build_context(mission)))
            report={'generated':outcome.source=='generated','source':outcome.source,
                    'failure':outcome.failure,'attempts':budget.status()['attempts'],
                    'reserved_microusd':budget.status()['reserved_microusd'],
                    'usage':outcome.measurement.usage.model_dump() if outcome.measurement and outcome.measurement.usage else None,
                    'live_mission_writes':0,'endgame_requests':0}
            if outcome.source!='generated':return dict(report,passed=False)
            diagnostic=GenerationDiagnostic(crisis_number=1,source='generated',category='success',
                duration_seconds=outcome.duration_seconds,http_status=outcome.http_status,measurement=outcome.measurement)
            assert store.accept_generation(mission.token,mission.generation.id,outcome.snapshot,'generated',diagnostic)
            token=mission.token
            snapshot=mission.crisis.model_dump_json()
            for player in mission.players:
                state=store.project(token,player.id)
                assert set(state['private_intelligence'])==set(player.roles)
                assert all(credential not in json.dumps(state) for credential in credentials)
            store.close()
            store=MissionStore(persistence=SQLiteMissions(db),campaign_loader=load_campaign_catalog,generation_enabled=True)
            store.initialize()
            restored=store.get(token)
            assert restored.crisis.model_dump_json()==snapshot and not restored.results
            for player in restored.players:
                assert set(store.project(token,player.id)['private_intelligence'])==set(player.roles)
            with closing(sqlite3.connect(db)) as check:
                assert check.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
            assert budget.status()['attempts']==1
            budget.mark_verified()
            return dict(report,passed=True,integrity='ok',isolated_restart='same_snapshot_no_provider_replay',
                        role_privacy='ok',snapshot_sha256=hashlib.sha256(snapshot.encode()).hexdigest())
        finally:store.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-one-request',action='store_true',required=True)
    parser.add_argument('--budget',default='/data/consensus-llm-budget.sqlite3')
    args=parser.parse_args()
    report=asyncio.run(run(args.budget))
    print(json.dumps(report,sort_keys=True))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
