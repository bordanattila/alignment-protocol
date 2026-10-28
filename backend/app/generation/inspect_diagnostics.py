"""Local read-only diagnostics; never an HTTP endpoint or gameplay projection."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

from ..domain import GenerationDiagnostic


def inspect(database: Path, mission_index: int = 1) -> list[dict]:
    if mission_index < 1: raise ValueError('Mission index must be positive')
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT payload FROM missions ORDER BY rowid DESC LIMIT 1 OFFSET ?',
                                 (mission_index - 1,)).fetchone()
        if row is None: raise ValueError('Mission unavailable')
        raw = json.loads(row[0])
        return [GenerationDiagnostic.model_validate(item).model_dump(mode='json')
                for item in raw.get('generation_diagnostics', [])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--mission-index', type=int, default=1, help='1 is the most recently created mission')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.database, args.mission_index), indent=2))
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError, RecursionError):
        print('Generation diagnostics unavailable; check the database and mission index.', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__': main()
