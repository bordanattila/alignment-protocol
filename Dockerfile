FROM python:3.12-slim AS sqlite-build
# Upstream 3.51.3 includes the WAL-reset fix. Keep Python's stdlib driver and
# SQLite file format; verify both the archive and the published amalgamation.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN python - <<'PY'
import hashlib
import io
import tarfile
import urllib.request
archive = urllib.request.urlopen('https://www.sqlite.org/2026/sqlite-autoconf-3510300.tar.gz', timeout=60).read()
assert hashlib.sha256(archive).hexdigest() == '81f5be397049b0cae1b167f2225af7646fc0f82e4a9b3c48c9ea3a533e21d77a'
with tarfile.open(fileobj=io.BytesIO(archive)) as source:
    amalgamation = source.extractfile('sqlite-autoconf-3510300/sqlite3.c').read()
assert hashlib.sha3_256(amalgamation).hexdigest() == '32d5424f97e0a7fc5ed2f6335afbb58be4e0298bd7117a34e39d345ff13d859e'
with open('sqlite3.c', 'wb') as output:
    output.write(amalgamation)
PY
RUN mkdir -p /opt/sqlite/lib && gcc -O2 -fPIC -shared -pthread \
    -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_RTREE \
    -DSQLITE_ENABLE_COLUMN_METADATA -Wl,-soname,libsqlite3.so.0 \
    -o /opt/sqlite/lib/libsqlite3.so.0 sqlite3.c -lm -ldl

FROM python:3.12-slim
COPY --from=sqlite-build /opt/sqlite/lib /opt/sqlite/lib
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CONSENSUS_LLM_ENABLED=false CONSENSUS_DB_PATH=/data/consensus-engine.sqlite3 \
    LD_LIBRARY_PATH=/opt/sqlite/lib
RUN python - <<'PY'
import sqlite3
assert sqlite3.sqlite_version == '3.51.3'
assert sqlite3.connect(':memory:').execute('SELECT sqlite_source_id()').fetchone()[0] == '2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618'
assert sqlite3.threadsafety == 3
PY
WORKDIR /app
# Only backend source enters the image; never include local databases or secrets.
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
RUN pip install --no-cache-dir ./backend
CMD ["sh", "-c", "exec uvicorn app.railway:create_railway_app --factory --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --ws-max-size 4096 --no-access-log --no-proxy-headers"]
