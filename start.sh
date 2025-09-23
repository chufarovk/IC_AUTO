#!/usr/bin/env bash
set -e

export PYTHONPATH=/app

# Alembic должен использовать sync-драйвер
export ALEMBIC_DATABASE_URL="${DATABASE_URL/asyncpg/psycopg2}"

echo "[prestart] Running alembic migrations..."
alembic upgrade head || {
  echo "[prestart] Alembic failed, applying safety DDL for integration_logs..."
  python - <<'PY'
import os, psycopg2
url = os.getenv("ADMIN_DB_URL") or "postgresql://user:password@db:5432/bisnesmedia"
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
  run_id        varchar,
  request_id    varchar,
  job_id        varchar,
  external_system varchar,
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
}

echo "[prestart] Starting app..."
# здесь — твой реальный запуск сервиса (пример)
exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
