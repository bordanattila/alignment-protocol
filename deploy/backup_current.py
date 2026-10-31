"""Run with the CURRENT container's Python; no new app.backup module required.

Creates a new verified snapshot and temporary restore; never replaces a source.
Only sanitized metadata is printed. Run from /app in the existing service Shell,
or stream this file to Python over authenticated SSH. No packages are installed.
"""
import argparse
from contextlib import closing
import hashlib
from itertools import zip_longest
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time


def readonly(path):
    return sqlite3.connect(Path(path).resolve(strict=True).as_uri() + '?mode=ro',
                           uri=True, timeout=5)


def copy_online(source, destination):
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    started = time.monotonic()

    def progress(_status, _remaining, _pages):
        if time.monotonic() - started > 60:
            raise TimeoutError('Snapshot timed out')

    try:
        with closing(readonly(source)) as origin, closing(sqlite3.connect(destination)) as target:
            origin.backup(target, pages=128, progress=progress, sleep=0.01)
            # Only the NEW snapshot is checkpointed, never the production source.
            target.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            # A self-contained transfer artifact must not depend on WAL sidecars.
            assert target.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete'
        with open(destination, 'rb') as snapshot:
            os.fsync(snapshot.fileno())
    except Exception:
        Path(destination).unlink(missing_ok=True)
        raise


def verify(path):
    # This class is already available in the deployed image. Do not call open():
    # that would acquire writer ownership and might initialize/migrate a schema.
    from app.persistence import SQLiteMissions
    with closing(readonly(path)) as connection:
        connection.execute('BEGIN')
        assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert connection.execute('PRAGMA foreign_key_check').fetchone() is None
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        validator = SQLiteMissions(path)
        validator.connection = connection
        missions = validator.load()  # aggregate checksums, domain and immutable result index
        results = sum(len(mission.results) for mission in missions.values())
        assert results == connection.execute('SELECT count(*) FROM resolutions').fetchone()[0]
        return {'missions': len(missions), 'results': results, 'schema_version': 2,
                'aggregate_format': 1, 'integrity': 'ok', 'application_validation': 'ok'}


def compare_restore(snapshot, restored):
    with closing(readonly(snapshot)) as original, closing(readonly(restored)) as copy:
        schema = original.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        assert schema == copy.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        orders = {'missions': 'token', 'resolutions': 'mission_token,result_id', 'mission_activity': 'token'}
        for name, _sql in schema:
            assert name in orders
            query = 'SELECT * FROM ' + name + ' ORDER BY ' + orders[name]
            for left, right in zip_longest(original.execute(query), copy.execute(query)):
                assert left == right


def prepare_backup(source, output_directory):
    source = Path(source).resolve(strict=True)
    assert source.is_file()
    output_directory = Path(output_directory).absolute()
    assert not output_directory.is_symlink()
    output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    assert output_directory.stat().st_mode & 0o077 == 0
    assert not any((p / '.git').exists() or (p / '.openai' / 'hosting.json').exists()
                   for p in output_directory.resolve().parents)
    with closing(readonly(source)) as connection:
        runtime = connection.execute('SELECT sqlite_version(),sqlite_source_id()').fetchone()
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        size = connection.execute('PRAGMA page_count').fetchone()[0] * connection.execute('PRAGMA page_size').fetchone()[0]
    # Space for BOTH snapshot and temporary restore; do not consume the reserve.
    assert shutil.disk_usage(output_directory).free >= 2 * size + 64 * 1024 * 1024
    directory = Path(tempfile.mkdtemp(prefix='consensus-snapshot-', dir=output_directory))
    snapshot = directory / 'consensus-engine.sqlite3'
    try:
        copy_online(source, snapshot)
        report = verify(snapshot)
        with tempfile.TemporaryDirectory(prefix='isolated-restore-', dir=directory) as temporary:
            restored = Path(temporary) / 'restore.sqlite3'
            copy_online(snapshot, restored)
            assert verify(restored) == report
            compare_restore(snapshot, restored)
        with open(snapshot, 'rb') as snapshot_file:
            digest = hashlib.file_digest(snapshot_file, 'sha256').hexdigest()
        with open(directory / 'SHA256SUMS', 'x') as manifest:
            os.chmod(manifest.name, 0o600)
            manifest.write(digest + '  consensus-engine.sqlite3\n')
            manifest.flush()
            os.fsync(manifest.fileno())
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {**report, 'isolated_restore': 'identical_all_rows', 'sha256': digest,
                'bytes': snapshot.stat().st_size, 'snapshot': str(snapshot),
                'source_sqlite_version': runtime[0], 'source_sqlite_id': runtime[1],
                'off_disk_transfer': 'required_before_deployment'}
    except Exception:
        shutil.rmtree(directory)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='/data/consensus-engine.sqlite3')
    parser.add_argument('--output-directory', default='/data/operator-backups')
    args = parser.parse_args()
    try:
        print(json.dumps(prepare_backup(args.source, args.output_directory), sort_keys=True))
    except Exception:
        parser.exit(1, 'Backup/isolated-restore verification failed; no production restore attempted. Inspect access, free space and database integrity privately.\n')


if __name__ == '__main__':
    main()
