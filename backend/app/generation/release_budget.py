"""Single-instance release allowance. Reservations are durable before inference.

Separate operator ledger: never alters a mission database or replenishes itself.
"""
import argparse
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

from .config import GenerationSettings
from .contract import GenerationError, FailureCategory
from .provider import ChatCompletionsProvider

ATTEMPTS = 100
RESERVATION_MICROUSD = 10_000
CEILING_MICROUSD = 1_000_000
MAX_REQUEST_BYTES = 32_768
# UTF-8 byte bound plus a conservative allowance for two-message/schema framing.
INPUT_TOKEN_BOUND = MAX_REQUEST_BYTES + 4_096
OUTPUT_TOKEN_BOUND = 8_192
# Standard pricing in microdollars/token, no cache-discount assumption.
assert INPUT_TOKEN_BOUND * 0.1 + OUTPUT_TOKEN_BOUND * 0.5 < RESERVATION_MICROUSD


class BudgetUnavailable(RuntimeError):
    pass


class ReleaseBudget:
    def __init__(self, path):
        self.path = Path(path)

    @classmethod
    def initialize(cls, path):
        path = Path(path)
        # Exclusive creation: startup and retries must never reset an allowance.
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(path)) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('''
                CREATE TABLE allowance(id INTEGER PRIMARY KEY CHECK(id=1),
                    phase TEXT NOT NULL CHECK(phase IN ('acceptance','public')),
                    attempts INTEGER NOT NULL CHECK(attempts BETWEEN 0 AND 100),
                    reserved INTEGER NOT NULL CHECK(reserved BETWEEN 0 AND 1000000),
                    halted INTEGER NOT NULL CHECK(halted IN (0,1)),
                    verified INTEGER NOT NULL CHECK(verified IN (0,1)));
                INSERT INTO allowance VALUES(1,'acceptance',0,0,0,0);
                CREATE TABLE attempts(id INTEGER PRIMARY KEY, operation TEXT NOT NULL,
                    reserved INTEGER NOT NULL CHECK(reserved=10000));
            ''')
            db.commit()
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        return cls(path)

    def connect(self):
        db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=rw', uri=True, timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        return db

    @staticmethod
    def validate(db):
        rows = db.execute('SELECT phase,attempts,reserved,halted,verified FROM allowance WHERE id=1').fetchall()
        if len(rows) != 1: raise BudgetUnavailable()
        phase, count, reserved, halted, verified = rows[0]
        ledger = db.execute('SELECT COUNT(*),COALESCE(SUM(reserved),0) FROM attempts').fetchone()
        if (phase not in ('acceptance','public') or type(count) is not int or not 0 <= count <= ATTEMPTS
                or reserved != count * RESERVATION_MICROUSD or reserved > CEILING_MICROUSD
                or halted not in (0,1) or verified not in (0,1) or ledger != (count,reserved)
                or (phase == 'public' and not verified)):
            raise BudgetUnavailable()
        return phase,count,reserved,halted,verified

    def status(self):
        try:
            with closing(self.connect()) as db:
                phase,count,reserved,halted,verified = self.validate(db)
                return dict(phase=phase,attempts=count,reserved_microusd=reserved,
                            halted=bool(halted),acceptance_verified=bool(verified),
                            maximum_attempts=ATTEMPTS,ceiling_microusd=CEILING_MICROUSD)
        except (OSError,sqlite3.Error,ValueError) as exc: raise BudgetUnavailable() from exc

    def reserve(self, operation):
        try:
            with closing(self.connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                phase,count,reserved,halted,_ = self.validate(db)
                if halted or count >= (1 if phase == 'acceptance' else ATTEMPTS): raise BudgetUnavailable()
                db.execute('INSERT INTO attempts VALUES(?,?,?)',(count+1,operation,RESERVATION_MICROUSD))
                db.execute('UPDATE allowance SET attempts=?,reserved=? WHERE id=1',
                           (count+1,reserved+RESERVATION_MICROUSD))
                db.commit()
        except (OSError,sqlite3.Error,ValueError) as exc: raise BudgetUnavailable() from exc

    def halt(self):
        with closing(self.connect()) as db:
            db.execute('UPDATE allowance SET halted=1 WHERE id=1'); db.commit()

    def mark_verified(self):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            phase,count,_,halted,verified = self.validate(db)
            if phase != 'acceptance' or count != 1 or halted or verified: raise BudgetUnavailable()
            db.execute('UPDATE allowance SET verified=1 WHERE id=1'); db.commit()

    def open_public(self):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            _,count,_,halted,verified = self.validate(db)
            if count != 1 or halted or not verified: raise BudgetUnavailable()
            db.execute("UPDATE allowance SET phase='public' WHERE id=1"); db.commit()


class BoundedReleaseProvider(ChatCompletionsProvider):
    def __init__(self, settings: GenerationSettings, budget: ReleaseBudget, client=None):
        if (settings.model != 'gpt-6-luna' or settings.endpoint != 'https://api.openai.com/v1/chat/completions'
                or settings.response_format != 'json_schema' or not settings.require_api_key
                or not settings.api_key or settings.timeout_seconds > 60):
            raise ValueError('Release inference requires the approved provider configuration.')
        super().__init__(settings,client)
        self.budget = budget
        self.semaphore = asyncio.Semaphore(1)
        self._reserved = False

    def prepare_payload(self, payload, request):
        payload.update(max_completion_tokens=OUTPUT_TOKEN_BOUND,service_tier='default',store=False)
        if len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()) > MAX_REQUEST_BYTES:
            raise GenerationError(FailureCategory.CONFIGURATION,provider_attempted=False)
        from .endgame import EndgameRequest
        operation = 'endgame' if isinstance(request,EndgameRequest) else 'crisis'
        try: self.budget.reserve(operation)
        except (BudgetUnavailable,sqlite3.Error,OSError):
            raise GenerationError(FailureCategory.DISABLED,provider_attempted=False) from None
        self._reserved = True

    async def generate(self, request):
        async with self.semaphore:
            self._reserved = False
            try:
                response = await super().generate(request)
                usage = response.usage
                if (usage is None or usage.input_tokens is None or usage.output_tokens is None
                        or usage.input_tokens > INPUT_TOKEN_BOUND
                        or usage.output_tokens > OUTPUT_TOKEN_BOUND
                        or usage.input_tokens * 0.1 + usage.output_tokens * 0.5 > RESERVATION_MICROUSD):
                    self.budget.halt()
                    raise GenerationError(FailureCategory.UNSUPPORTED_RESPONSE)
                return response
            except BaseException:
                # Bad configuration/budget preflight consumes no attempt. Any
                # attempted or uncertain failure consumes its reservation and
                # disables further paid attempts; gameplay uses existing fallback.
                if self._reserved:
                    self.budget.halt()
                raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['initialize','status','mark-verified','open-public'])
    parser.add_argument('--path',default='/data/consensus-llm-budget.sqlite3')
    args=parser.parse_args(); budget=ReleaseBudget(args.path)
    if args.action=='initialize':budget=ReleaseBudget.initialize(args.path)
    elif args.action=='mark-verified':budget.mark_verified()
    elif args.action=='open-public':budget.open_public()
    print(json.dumps(budget.status(),sort_keys=True))


if __name__=='__main__':main()
