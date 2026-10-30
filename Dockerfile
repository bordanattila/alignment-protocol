FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CONSENSUS_LLM_ENABLED=false CONSENSUS_DB_PATH=/data/consensus-engine.sqlite3
WORKDIR /app
# Only backend source enters the image; never include local databases or secrets.
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
RUN pip install --no-cache-dir ./backend
CMD ["sh", "-c", "exec uvicorn app.railway:create_railway_app --factory --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --ws-max-size 4096 --no-access-log"]
