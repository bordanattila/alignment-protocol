"""Single-owner SQLite authority, versioned JSON aggregates and result invariants."""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3

from .domain import Mission, Phase, Role, Crisis
from .callsigns import callsign_key
from .campaign import validate_catalog, STAGES


class PersistenceError(Exception):
    """Safe operational message only: never include state/credentials/SQL values."""


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def credential_digest(credential: str) -> str:
    return hashlib.sha256(credential.encode()).hexdigest()


class SQLiteMissions:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.connection = None
        self.owner = None

    def open(self):
        try:
            if self.path != ':memory:':
                path = Path(self.path)
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.owner = open(str(path) + '.lock', 'a')
                fcntl.flock(self.owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
                os.close(descriptor)
                os.chmod(path, 0o600)
            self.connection = sqlite3.connect(self.path, check_same_thread=False, timeout=2)
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA journal_mode=WAL')
            self.connection.execute('PRAGMA synchronous=FULL')
            if self.connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise PersistenceError('Mission database integrity check failed; recovery stopped.')
            version = self.connection.execute('PRAGMA user_version').fetchone()[0]
            if version == 0:
                if self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise PersistenceError('Unversioned mission database; recovery stopped.')
                with self.connection:
                    self.connection.execute("BEGIN IMMEDIATE")
                    self.connection.execute('CREATE TABLE missions (token TEXT PRIMARY KEY, format_version INTEGER NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)')
                    self.connection.execute('CREATE TABLE resolutions (mission_token TEXT NOT NULL REFERENCES missions(token), result_id TEXT NOT NULL, crisis_number INTEGER NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(mission_token,result_id), UNIQUE(mission_token,crisis_number))')
                    self.connection.execute('PRAGMA user_version=2')
            elif version == 1:
                self._migrate_v1()
            elif version != 2:
                raise PersistenceError('Unsupported mission database version; recovery stopped.')
            self._check_columns('missions', ['token', 'format_version', 'payload', 'checksum'])
            self._check_columns('resolutions', ['mission_token', 'result_id', 'crisis_number', 'record_hash'])
        except (OSError, sqlite3.Error):
            self.close()
            raise PersistenceError('Mission database unavailable, locked, or corrupt; recovery stopped.') from None
        except PersistenceError:
            self.close()
            raise

    def _check_columns(self, table: str, expected: list[str]):
        # Table names are internal constants; never use request input here.
        actual = [row[1] for row in self.connection.execute(f'PRAGMA table_info({table})')]
        if actual != expected:
            raise PersistenceError('Mission database schema does not match its version; recovery stopped.')

    def _migrate_v1(self):
        """Both shipped v1 layouts must migrate before the first write."""
        try:
            with self.connection:
                self.connection.execute('BEGIN IMMEDIATE')
                self._check_columns('missions', ['token', 'format_version', 'payload', 'checksum'])
                columns = [row[1] for row in self.connection.execute('PRAGMA table_info(resolutions)')]
                if columns == ['mission_token', 'result_id', 'crisis_number', 'record']:
                    self.connection.execute('ALTER TABLE resolutions RENAME TO resolutions_v1')
                    self.connection.execute('CREATE TABLE resolutions (mission_token TEXT NOT NULL REFERENCES missions(token), result_id TEXT NOT NULL, crisis_number INTEGER NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(mission_token,result_id), UNIQUE(mission_token,crisis_number))')
                    for token, result_id, number, text in self.connection.execute('SELECT mission_token,result_id,crisis_number,record FROM resolutions_v1'):
                        record = json.loads(text)
                        if record['id'] != result_id or record['crisis_number'] != number:
                            raise ValueError('Legacy resolution identity mismatch')
                        digest = hashlib.sha256(canonical(record).encode()).hexdigest()
                        self.connection.execute('INSERT INTO resolutions VALUES (?,?,?,?)', (token,result_id,number,digest))
                else:
                    self._check_columns('resolutions', ['mission_token', 'result_id', 'crisis_number', 'record_hash'])
                # Validate every aggregate and result before committing any DDL
                # or version change. A failure retains the original database.
                self.load()
                if columns[-1:] == ['record']:
                    self.connection.execute('DROP TABLE resolutions_v1')
                self.connection.execute('PRAGMA user_version=2')
        except (ValueError, TypeError, KeyError, RecursionError):
            raise PersistenceError('Legacy mission history is invalid; schema migration rolled back.') from None

    @staticmethod
    def payload(mission: Mission) -> str:
        state = mission.model_dump(mode='json', exclude={'crisis'})
        for player in state['players']:
            player['credential_hash'] = player['credential_hash'] or credential_digest(player['credential'])
            player['credential'] = ''
            player['connected'] = False
        return canonical(state)

    @staticmethod
    def validate_generated(mission: Mission):
        if mission.mode == 'authored':
            if mission.admissions or mission.generation or mission.phase == Phase.PREPARING:
                raise ValueError('Authored generation invariant')
            return
        if mission.phase == Phase.LOBBY:
            if mission.sequence or mission.admissions or mission.generation:
                raise ValueError('Generated lobby invariant')
            return
        if mission.campaign is None or len(mission.admissions) != len(mission.sequence) or len(mission.sequence) > 10:
            raise ValueError('Generated admission invariant')
        if len({c.id for c in mission.sequence}) != len(mission.sequence):
            raise ValueError('Generated uniqueness invariant')
        for crisis, record in zip(mission.sequence, mission.admissions):
            if (hashlib.sha256(record.canonical_json.encode()).hexdigest() != record.content_hash
                    or Crisis.model_validate_json(record.canonical_json) != crisis):
                raise ValueError('Accepted snapshot invariant')
        if mission.phase == Phase.PREPARING:
            attempt = mission.generation
            if (attempt is None or attempt.target_index != len(mission.results)
                    or len(mission.sequence) != len(mission.results) or attempt.target_index >= 10
                    or mission.crisis_index != max(0, attempt.target_index - 1)
                    or mission.deadline is not None or mission.rounds or mission.decision):
                raise ValueError('Generation attempt invariant')
        elif mission.generation is not None or not mission.sequence:
            raise ValueError('Unexpected generation attempt')
        if mission.phase == Phase.COMPLETED and len(mission.results) != 10:
            raise ValueError('Generated completion invariant')

    @staticmethod
    def validate(mission: Mission):
        SQLiteMissions.validate_generated(mission)
        if mission.campaign is not None:
            validate_catalog(mission.campaign.scenarios)
            if mission.mode == 'authored' and (len(mission.sequence) != 10 or len({c.id for c in mission.sequence}) != 10):
                raise ValueError('Campaign length/uniqueness invariant')
            catalog = {s.crisis.id:s for s in mission.campaign.scenarios}
            for index,crisis in enumerate(mission.sequence):
                if mission.mode == 'generated':
                    if mission.admissions[index].source == 'generated': continue
                if crisis.id not in catalog or catalog[crisis.id].stage != STAGES[index]:
                    raise ValueError('Campaign stage invariant')
                dependency = catalog[crisis.id].prerequisite
                if index <= mission.crisis_index and dependency:
                    if not any(r.crisis_id == dependency.crisis_id and r.decision.choice_id in dependency.choice_ids
                               for r in mission.results[:index]):
                        raise ValueError('Campaign prerequisite invariant')
        players = mission.players
        ids = {p.id for p in players}
        if not 1 <= len(players) <= 4 or len(ids) != len(players) or mission.host_id not in ids:
            raise ValueError('Membership invariant')
        if len({callsign_key(p.callsign) for p in players}) != len(players):
            raise ValueError("Callsign invariant")
        times = [mission.deadline, mission.recovery_deadline] + [r.deadline for r in mission.rounds] + [m.timestamp for m in mission.chat] + list(mission.last_chat_at.values())
        if any(value is not None and not math.isfinite(value) for value in times):
            raise ValueError("Timestamp invariant")
        if any(p.credential or len(p.credential_hash) != 64 or any(c not in '0123456789abcdef' for c in p.credential_hash) for p in players):
            raise ValueError('Credential invariant')
        if mission.revision < 0 or len({r.id for r in mission.results}) != len(mission.results):
            raise ValueError('Ledger invariant')
        if [r.crisis_number for r in mission.results] != list(range(1, len(mission.results)+1)):
            raise ValueError('Ledger order')
        if mission.phase != Phase.LOBBY:
            empty_preparation = mission.mode == 'generated' and mission.phase == Phase.PREPARING and not mission.sequence
            if ((not empty_preparation and (not mission.sequence or not 0 <= mission.crisis_index < len(mission.sequence)))
                    or mission.initial_metrics is None):
                raise ValueError('Sequence invariant')
            roles = [role for p in players for role in p.roles]
            if len(roles) != 4 or set(roles) != set(Role):
                raise ValueError('Role invariant')
            previous = mission.initial_metrics
            for result in mission.results:
                if result.before != previous or result.crisis_id != mission.sequence[result.crisis_number-1].id:
                    raise ValueError('History invariant')
                if result.applied_deltas.model_dump() != {k:result.after.model_dump()[k]-v for k,v in result.before.model_dump().items()}:
                    raise ValueError('Consequence invariant')
                previous = result.after
            if mission.metrics != previous:
                raise ValueError('Metric invariant')
        timed = (Phase.DISCUSSION, Phase.VOTING, Phase.CONSENSUS_WINDOW)
        if mission.phase in timed and mission.deadline is None:
            raise ValueError('Missing phase deadline')
        if mission.phase == Phase.RECONNECT_WAIT:
            if mission.recovery_phase not in timed or mission.deadline is not None:
                raise ValueError('Recovery invariant')
            if mission.recovery_deadline is None and mission.recovery_phase != Phase.CONSENSUS_WINDOW:
                raise ValueError('Recovery deadline invariant')
        elif mission.recovery_phase is not None:
            raise ValueError('Unexpected recovery phase')
        effective_phase = mission.recovery_phase if mission.phase == Phase.RECONNECT_WAIT else mission.phase
        effective_deadline = mission.recovery_deadline if mission.phase == Phase.RECONNECT_WAIT else mission.deadline
        if effective_phase == Phase.VOTING and (not mission.rounds or mission.rounds[-1].deadline != effective_deadline):
            raise ValueError('Voting deadline invariant')
        if effective_phase == Phase.CONSENSUS_WINDOW and (len(mission.rounds) != 1 or mission.rounds[0].totals is None):
            raise ValueError("Consensus invariant")
        if mission.sequence:
            expected = (len(mission.sequence) if mission.phase == Phase.PREPARING else
                        mission.crisis_index + (1 if mission.phase in (Phase.DECISION_LOCKED, Phase.COMPLETED, Phase.FAILED) else 0))
            if len(mission.results) != expected:
                raise ValueError("Current crisis ledger invariant")
        if any(set(r.votes)-set(r.eligible) or set(r.eligible)-ids for r in mission.rounds):
            raise ValueError('Voting membership invariant')

    def load(self) -> dict[str, Mission]:
        missions = {}
        try:
            for token, version, payload, checksum in self.connection.execute('SELECT token,format_version,payload,checksum FROM missions'):
                if not isinstance(payload, str) or not isinstance(token, str) or version != 1 or hashlib.sha256(payload.encode()).hexdigest() != checksum:
                    raise ValueError('Record format/checksum')
                raw = json.loads(payload)
                # Additive aggregate extensions; finalized result hashes stay unchanged.
                if isinstance(raw, dict) and 'campaign' not in raw: raw['campaign'] = None
                if isinstance(raw, dict):
                    for key, default in (('mode', 'authored'), ('generation', None), ('admissions', [])):
                        raw.setdefault(key, default)
                if not isinstance(raw, dict) or set(raw) != set(Mission.model_fields)-{'crisis'}:
                    raise ValueError('Record fields do not match format version')
                sequence = raw.get('sequence', [])
                raw['crisis'] = sequence[raw['crisis_index']] if sequence else None
                mission = Mission.model_validate(raw)
                if mission.token != token: raise ValueError('Mission identity invariant')
                self.validate(mission)
                rows = self.connection.execute('SELECT result_id,crisis_number,record_hash FROM resolutions WHERE mission_token=? ORDER BY crisis_number', (token,)).fetchall()
                if rows != [(r.id,r.crisis_number,hashlib.sha256(canonical(r.model_dump(mode='json')).encode()).hexdigest()) for r in mission.results]:
                    raise ValueError('Resolution index mismatch')
                missions[token] = mission
        except (ValueError, IndexError, KeyError, TypeError, RecursionError, sqlite3.Error):
            raise PersistenceError('Persisted mission record is invalid or incompatible; recovery stopped. Records retained for repair.') from None
        return missions

    def save(self, mission: Mission):
        self.validate_generated(mission)
        payload = self.payload(mission)
        checksum = hashlib.sha256(payload.encode()).hexdigest()
        try:
            with self.connection:
                previous = self.connection.execute('SELECT payload FROM missions WHERE token=?', (mission.token,)).fetchone()
                if previous:
                    old = json.loads(previous[0])
                    prior = old.get('admissions', [])
                    if (old.get('mode', 'authored') != mission.mode
                            or mission.model_dump(mode='json')['admissions'][:len(prior)] != prior
                            or len(mission.admissions) < len(prior)):
                        raise PersistenceError('Accepted mission mode and crises cannot be changed or removed.')
                existing = self.connection.execute('SELECT result_id,record_hash FROM resolutions WHERE mission_token=?', (mission.token,)).fetchall()
                records = {r.id:hashlib.sha256(canonical(r.model_dump(mode='json')).encode()).hexdigest() for r in mission.results}
                if any(records.get(key) != record for key,record in existing):
                    raise PersistenceError('Finalized history cannot be changed or removed.')
                self.connection.execute('INSERT INTO missions VALUES (?,?,?,?) ON CONFLICT(token) DO UPDATE SET payload=excluded.payload, checksum=excluded.checksum', (mission.token,1,payload,checksum))
                for result in mission.results:
                    self.connection.execute('INSERT INTO resolutions VALUES (?,?,?,?) ON CONFLICT(mission_token,result_id) DO NOTHING', (mission.token,result.id,result.crisis_number,records[result.id]))
        except sqlite3.Error:
            raise PersistenceError('Mission storage failed. The operation was not accepted; retry after storage recovers.') from None

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.owner is not None:
            self.owner.close()
            self.owner = None
