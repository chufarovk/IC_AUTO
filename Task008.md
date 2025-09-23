
> **таблицы `integration_logs` нет в БД**, а приложение и админка пытаются в неё писать/читать.

Ниже — «боевой» план из двух частей: **быстрый хотфикс** (создаст таблицу за минуту) и **перманентное исправление** (правильные миграции Alembic + автоприменение на старте). Сразу даю готовые куски, которые можно копировать.

---

# A. Срочный хотфикс (создать таблицу сейчас)

1. Выполни SQL прямо в контейнере БД:

```bash
docker compose -f docker-compose.dev.yml exec db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "
CREATE TABLE IF NOT EXISTS integration_logs (
  id            BIGSERIAL PRIMARY KEY,
  ts            timestamptz,
  created_at    timestamptz DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at    timestamptz DEFAULT (now() AT TIME ZONE 'utc'),
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
"
```

2. Проверь:

```bash
docker compose -f docker-compose.dev.yml exec db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "\dt+ integration_logs"
```

3. Посмотри логи `app` — ошибки `relation "integration_logs" does not exist` должны исчезнуть, а в админ-панели пропадёт предупреждение «Таблица логов не создана».

Это снимет пожар прямо сейчас. Далее — делаем правильно.

---

# B. Перманентное исправление (миграции Alembic + автозапуск)

## B1. Приводим ENV к «контейнерным» адресам

В `.env` должны быть **такие** строки (не `localhost`, а `db` внутри сети):

```env
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=bisnesmedia

DATABASE_URL=postgresql+asyncpg://user:password@db:5432/bisnesmedia
ADMIN_DB_URL=postgresql+psycopg2://user:password@db:5432/bisnesmedia

# чтобы админка не билась в порт 8000 внутри сети
ADMIN_APP_URL=http://app
```

*(это же мы обсуждали ранее; сейчас у тебя по логам админка уже ок, но фикс закрепляю здесь.)*

## B2. Alembic: читаем URL из ENV и подменяем драйвер

Открой `alembic.ini` — там должна быть ссылка на переменную окружения (а не хардкод):

```ini
# alembic.ini
sqlalchemy.url = ${DATABASE_URL}
```

В `migrations/env.py` добавь безопасную подмену `asyncpg` → `psycopg2`, чтобы Alembic (синхронный) не падал:

```python
# migrations/env.py (фрагмент вверху файла)
import os

def _alembic_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    # Alembic работает синхронно; если в env asyncpg – заменим на psycopg2
    return url.replace("+asyncpg", "+psycopg2")

config.set_main_option("sqlalchemy.url", _alembic_url())
```

## B3. Миграция «create\_integration\_logs»

Создай файл `migrations/versions/20240922_create_integration_logs.py` со следующим содержимым:

```python
"""create integration_logs

Revision ID: 20240922_create_integration_logs
Revises:
Create Date: 2025-09-22 21:05:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "20240922_create_integration_logs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now() AT TIME ZONE 'utc')")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now() AT TIME ZONE 'utc')")),
        sa.Column("process_name", sa.Text(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("log_level", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("external_system", sa.String(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("payload_hash", sa.String(), nullable=True),
        sa.Column("details", JSONB, nullable=True),
    )
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_integration_logs_time
        ON integration_logs (COALESCE(ts, created_at));
    """)


def downgrade():
    op.drop_index("ix_integration_logs_time", table_name="integration_logs")
    op.drop_table("integration_logs")
```

> Поля и типы подобраны **под те INSERT/SELECT**, которые видно в твоих логах и в SQL админ-панели.

## B4. Автозапуск миграций при старте `app`

В твоём `Dockerfile` для `app` уже есть запуск `./start.sh`. Убедись, что **перед** стартом uvicorn мы вызываем `alembic upgrade head`. Если у тебя нет отдельного скрипта — создай/замени `start.sh` так:

```bash
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
```

> Важно: **миграции выполняются до старта планировщика**. Иначе APScheduler снова попытается писать в несуществующую таблицу.

# C. Короткая памятка «почему ломалось»

* Alembic (или ручное DDL) **не создавал** `integration_logs`.
* APScheduler-задача `process_outbox_events_job` пишет лог **сразу после старта** → падает на `UndefinedTableError`.
* Админ-панель делает `SELECT FROM integration_logs` → тоже падает, отсюда баннер.

**Решение:** гарантированное создание таблицы миграцией при старте `app` (с безопасным DDL-фоллбеком) + правильные ENV/URL для контейнерной сети.

---