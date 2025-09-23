#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH=/app
export PROJECT_ROOT=/app

# Alembic expects sync driver in URL
export ALEMBIC_DATABASE_URL="${DATABASE_URL/asyncpg/psycopg2}"

ALEMBIC_CMD="./.venv/bin/python -m alembic"

cd /app

echo "[prestart] Applying alembic migrations via ${ALEMBIC_CMD} upgrade head..."
if ! ${ALEMBIC_CMD} upgrade head; then
  echo "[prestart] Alembic failed, applying safety DDL for integration_logs..."
  ./.venv/bin/python - <<'PY'
import os
import psycopg2

url = os.getenv("ADMIN_DB_URL") or os.getenv("ALEMBIC_DATABASE_URL") or "postgresql://user:password@db:5432/bisnesmedia"
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS integration_logs (
  id BIGSERIAL PRIMARY KEY,
  ts timestamptz,
  created_at timestamptz DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at timestamptz DEFAULT (now() AT TIME ZONE 'utc'),
  process_name  text,
  step          text,
  log_level     text,
  status        text,
  message       text,
  run_id        uuid,
  request_id    uuid,
  job_id        uuid,
  job_name      text,
  external_system text,
  elapsed_ms    integer,
  retry_count   integer DEFAULT 0,
  payload       jsonb,
  payload_hash  varchar,
  details       jsonb
);
CREATE INDEX IF NOT EXISTS ix_integration_logs_time ON integration_logs (COALESCE(ts, created_at));
""")
conn.commit()
cur.close()
conn.close()
PY
fi

echo "[prestart] Starting app..."
exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
