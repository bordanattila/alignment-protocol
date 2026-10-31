"""The pre-upgrade operator script must work without deploying app.backup."""
from pathlib import Path
import runpy
import sqlite3

import pytest

from test_milestone3 import Clock
from test_persistence import team, voting, votes


operator = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'deploy' / 'backup_current.py'))


@pytest.mark.parametrize('completed', [False, True])
def test_current_container_online_backup_preserves_wal_and_source(tmp_path, completed):
    source = tmp_path / 'live.sqlite3'
    store, mission, credentials = team(source, Clock())
    try:
        for choice in ('BBBCCBCAAC' if completed else 'B'):
            voting(store, mission, credentials, store.clock)
            votes(store, mission, credentials, [choice] * 3)
            store.continue_mission(mission.token, credentials[0], mission.results[-1].id)
        connection = store.persistence.connection
        before = connection.execute('SELECT * FROM missions').fetchall()
        assert Path(str(source) + '-wal').stat().st_size > 0
        report = operator['prepare_backup'](source, tmp_path / 'private-backups')
        assert report['isolated_restore'] == 'identical_all_rows'
        assert report['results'] == (10 if completed else 1)
        assert report['application_validation'] == 'ok'
        assert report['off_disk_transfer'] == 'required_before_deployment'
        snapshot = Path(report['snapshot'])
        assert snapshot.stat().st_mode & 0o777 == 0o600
        assert snapshot.parent.stat().st_mode & 0o777 == 0o700
        assert connection.execute('SELECT * FROM missions').fetchall() == before
        assert set(snapshot.parent.iterdir()) == {snapshot, snapshot.parent / 'SHA256SUMS'}
    finally:
        store.close()


def test_current_container_backup_rejects_bad_source_and_removes_partial_snapshot(tmp_path):
    source = tmp_path / 'bad.sqlite3'
    with sqlite3.connect(source) as connection:
        connection.execute('PRAGMA user_version=2')
        connection.execute('CREATE TABLE unexpected (value TEXT)')
    output = tmp_path / 'private-backups'
    with pytest.raises(Exception):
        operator['prepare_backup'](source, output)
    assert list(output.iterdir()) == []


def test_current_container_backup_rejects_public_destination(tmp_path):
    source = tmp_path / 'live.sqlite3'
    store, _mission, _credentials = team(source, Clock())
    try:
        output = tmp_path / 'public-backups'
        output.mkdir(mode=0o755)
        with pytest.raises(AssertionError):
            operator['prepare_backup'](source, output)
        assert list(output.iterdir()) == []
    finally:
        store.close()
