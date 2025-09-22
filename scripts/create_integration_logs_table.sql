-- Создание таблицы integration_logs
CREATE TABLE IF NOT EXISTS integration_logs (
  id bigserial PRIMARY KEY,
  ts timestamptz,
  created_at timestamptz DEFAULT now(),
  process_name text,
  step text,
  log_level text,
  status text,
  message text,
  run_id uuid,
  request_id text,
  job_id text,
  external_system text,
  elapsed_ms integer,
  retry_count integer DEFAULT 0,
  payload jsonb,
  payload_hash text,
  details jsonb
);

-- Создание индекса для оптимизации запросов по времени
CREATE INDEX IF NOT EXISTS ix_integration_logs_time ON integration_logs (COALESCE(ts, created_at));