"""Operator-only local CLI. No HTTP endpoint, inference, or remote transfer.

Run through authenticated Render SSH/shell. Outputs counts and sizes only.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from contextlib import contextmanager

from .persistence import SQLiteMissions, PersistenceError
from .retention import MissionActivity


@contextmanager
def readonly(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Expected an existing database file.')
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        yield connection
    finally:
        connection.close()


def verify(path):
    with readonly(path) as connection:
        connection.execute('BEGIN')
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Backup integrity verification failed.')
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('Backup foreign key verification failed.')
        if connection.execute('PRAGMA user_version').fetchone()[0] != 2:
            raise ValueError('Unsupported database schema for verification.')
        validator = SQLiteMissions(path)
        validator.connection = connection
        missions = validator.load()  # Includes content hashes and immutable result-index validation.
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='mission_activity'").fetchone():
            for token, created, last, ended, creator in connection.execute('SELECT * FROM mission_activity'):
                if token not in missions: raise ValueError('Orphaned activity metadata.')
                MissionActivity(created, last, ended, creator).validate()
        return {'missions': len(missions), 'results': sum(len(m.results) for m in missions.values()),
                'schema_version': 2, 'integrity': 'ok'}


def disk_status(path):
    path = Path(path).resolve(strict=True)
    with readonly(path) as connection:
        page_size = connection.execute('PRAGMA page_size').fetchone()[0]
        pages = connection.execute('PRAGMA page_count').fetchone()[0]
        free_pages = connection.execute('PRAGMA freelist_count').fetchone()[0]
    usage = shutil.disk_usage(path.parent)
    wal = Path(str(path) + '-wal')
    return {'database_bytes': path.stat().st_size, 'wal_bytes': wal.stat().st_size if wal.exists() else 0,
            'logical_bytes': pages * page_size, 'reusable_bytes': free_pages * page_size,
            'disk_total_bytes': usage.total, 'disk_free_bytes': usage.free,
            'warning': usage.free < 134217728}


def backup_database(source, destination, timeout=60):
    source, destination = Path(source).resolve(strict=True), Path(destination).absolute()
    if source == destination.resolve():
        raise ValueError('Backup destination must differ from source.')
    if any((parent / '.git').exists() or (parent / '.openai' / 'hosting.json').exists()
           for parent in destination.resolve().parents):
        raise ValueError('Backups must be outside Git and Sites source trees.')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.parent.is_symlink() or destination.parent.stat().st_mode & 0o077:
        raise ValueError('Backup directory must be private (mode 0700).')
    status = disk_status(source)
    if shutil.disk_usage(destination.parent).free < status['logical_bytes'] + 67108864:
        raise ValueError('Insufficient disk headroom for an online backup.')
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    started = time.monotonic()

    def progress(_status, _remaining, _total):
        if time.monotonic() - started > timeout:
            raise TimeoutError('Backup exceeded its time budget.')

    try:
        with readonly(source) as origin:
            target = sqlite3.connect(destination)
            try:
                origin.backup(target, pages=128, progress=progress, sleep=0.01)
            finally:
                target.close()
        return verify(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def restore_check(backup):
    # Destination is always a new isolated temporary path, never the live DB.
    with tempfile.TemporaryDirectory(prefix='consensus-restore-') as directory:
        restored = Path(directory) / 'isolated.sqlite3'
        report = backup_database(backup, restored)
        with readonly(backup) as original, readonly(restored) as copy:
            tables = [('missions', 'token'), ('resolutions', 'mission_token,result_id')]
            if original.execute("SELECT 1 FROM sqlite_master WHERE name='mission_activity'").fetchone():
                tables.append(('mission_activity', 'token'))
            for table, order in tables:
                if original.execute(f'SELECT * FROM {table} ORDER BY {order}').fetchall() != copy.execute(f'SELECT * FROM {table} ORDER BY {order}').fetchall():
                    raise ValueError('Isolated restored records differ from the backup.')
        return {**report, 'isolated_restore': 'identical'}


def compact_offline(path):
    """Requires exclusive backend ownership; refuses a running server's lock."""
    path = Path(path).resolve(strict=True)
    verify(path)  # Never create an empty database because of a mistyped path.
    ledger = SQLiteMissions(path)
    ledger.open()
    try:
        before = verify(path)
        if disk_status(path)['disk_free_bytes'] < disk_status(path)['logical_bytes'] + 67108864:
            raise ValueError('Insufficient disk headroom for offline compaction.')
        ledger.connection.execute('VACUUM')
        ledger.connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        if before != verify(path):
            raise ValueError('Compaction verification failed.')
        return disk_status(path)
    finally:
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--output', type=Path)
    operation.add_argument('--verify', action='store_true')
    operation.add_argument('--restore-check', action='store_true')
    operation.add_argument('--status', action='store_true')
    operation.add_argument('--compact-offline', action='store_true')
    args = parser.parse_args()
    try:
        if args.output:
            report = backup_database(args.source, args.output)
        elif args.restore_check:
            report = restore_check(args.source)
        elif args.status:
            report = disk_status(args.source)
        elif args.compact_offline:
            report = compact_offline(args.source)
        else:
            report = verify(args.source)
        print(json.dumps(report, sort_keys=True))
    except (OSError, ValueError, sqlite3.Error, PersistenceError, TimeoutError):
        parser.exit(1, 'Operator database operation failed; inspect paths, ownership, integrity and free space privately.\n')


if __name__ == '__main__':
    main()
