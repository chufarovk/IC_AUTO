вижу 2 очевидных причины твоего текущего «залома»:

1. **`Connection refused` из админки** — админка бьётся в `http://app:8000`, но контейнер **app слушает внутри на 80** (ты мапишь `8000:80`). Внутри docker-сети порт публикации не участвует, сервисы ходят на **внутренний порт**. Отсюда отказ в соединении.

2. **«integration\_logs не создана»** — миграция не применена/выполняется не тем драйвером/не тем URL. Таблицы нет (или alembic не запускался на старте).

Даю «боевое» ТЗ для кодера. Выполнить по пунктам; в конце — чек-лист приёмки.

---

# TASK: починить связку admin → app и гарантировать БД/миграции

## Цели

* Кнопка «Запустить оценку дефицита» в админке триггерит app **без** `Connection refused`.
* Таблица `integration_logs` создаётся миграцией автоматически; админка видит логи.
* Окружение (compose + .env) единообразно; никаких «локалхостов» внутри контейнеров.

---

## 1) Адрес приложения для админки (исправляем порт)

### Что происходит

Внутри docker-сети админка ходит на `app:8000`, а app слушает **80** (у тебя mapping `8000:80`). Внутренний запрос на 8000 → отказ.

### Сделать

* В `.env` заменить:

```
ADMIN_APP_URL=http://app
```

(без порта; по умолчанию это 80, как нам и нужно).

* В `admin_panel/app.py` поправить резолвер (если добавляли ранее), чтобы дефолт был **[http://app](http://app)**, а не `http://app:8000`:

```python
# admin_panel/app.py
import os, socket

def resolve_app_base_url() -> str:
    url = os.getenv("ADMIN_APP_URL", "").strip()
    if url:
        return url
    try:
        socket.gethostbyname("app")
        # app слушает внутри контейнера порт 80
        return "http://app"
    except Exception:
        # если админку гоняют вне Docker локально
        return "http://localhost:8000"

APP_BASE = resolve_app_base_url()
```

> Альтернатива (НЕ предпочтительна сейчас): перевести app на внутренний порт 8000 (менять `start.sh`/`uvicorn` и в compose `ports: "8000:8000"`). Проще и безопаснее — оставить как есть и править URL.

---

## 2) Убрать дубли и рассинхрон в compose

У тебя в сообщении две секции compose подряд. Должен быть **один** файл `docker-compose.dev.yml`. Оставляем версию с `build` для `app` и `admin_panel` и с `ports: "8000:80"` у app. Убедись, что:

```yaml
services:
  db:
    image: postgres:15
    container_name: bisnesmedia_db
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    ports:
      - "5433:5432"         # наружу 5433; внутри сети всегда db:5432
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  app:
    build:
      context: .
      dockerfile: Dockerfile
    image: bisnesmedia/app:dev
    container_name: bisnesmedia_app
    volumes:
      - ./app:/app/app
      - ./prestart.py:/app/prestart.py
      - ./start.sh:/app/start.sh
    environment:
      DATABASE_URL: ${DATABASE_URL}
      API_1C_URL: ${API_1C_URL}
      API_1C_USER: ${API_1C_USER}
      API_1C_PASSWORD: ${API_1C_PASSWORD}
      PROJECT_NAME: ${PROJECT_NAME}
      DEBUG: ${DEBUG}
    ports:
      - "8000:80"           # хост:контейнер
    depends_on:
      db:
        condition: service_healthy

  admin_panel:
    build:
      context: .
      dockerfile: Dockerfile.admin
    image: bisnesmedia/admin:dev
    container_name: bisnesmedia_admin
    command: ./.venv/bin/python -m streamlit run admin_panel/app.py --server.port=8501 --server.address=0.0.0.0
    volumes:
      - ./admin_panel:/app/admin_panel
      - ./app:/app/app
    environment:
      ADMIN_DB_URL: ${ADMIN_DB_URL}
      ADMIN_APP_URL: ${ADMIN_APP_URL}
      ADMIN_POLL_SECONDS: ${ADMIN_POLL_SECONDS}
      ADMIN_PAGE_SIZE: ${ADMIN_PAGE_SIZE}
      ADMIN_TRIGGER_TOKEN: ${ADMIN_TRIGGER_TOKEN}
      HOME: /tmp
      STREAMLIT_CACHE_DIR: /tmp/streamlit-cache
      STREAMLIT_SERVER_HEADLESS: "true"
      STREAMLIT_BROWSER_GATHER_USAGE_STATS: "false"
    ports:
      - "8501:8501"
    depends_on:
      app:
        condition: service_started
      db:
        condition: service_healthy

volumes:
  postgres_data:
```

---

## 3) Миграции и `integration_logs`

### Проблема

Миграция не доезжает (или alembic берёт неправильный URL). Таблицы нет — админка честно пишет «integration\_logs не создана».

### Сделать

* В `.env` убедиться, что **оба** URL «смотрят» в контейнерную БД:

```
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/bisnesmedia
ADMIN_DB_URL=postgresql+psycopg2://user:password@db:5432/bisnesmedia
```

* В `alembic.ini` (или месте, где Alembic берёт URL) — использовать переменную окружения; например:

```
sqlalchemy.url = ${DATABASE_URL}
```

* В `start.sh` перед запуском uvicorn выполнить миграции **с sync-драйвером**:

```bash
#!/usr/bin/env bash
set -e

# Alembic лучше кормить sync-драйвером; если в env asyncpg — временно подменим:
PY_ALEMBIC_URL="${DATABASE_URL/asyncpg/psycopg2}"
export PYTHONPATH=/app

echo "Running migrations..."
ALembicURL="${PY_ALEMBIC_URL}" alembic upgrade head || {
  echo "Alembic failed, trying psql bootstrap for integration_logs..."
  # аварийно создадим таблицу, чтобы админка жила
  psql "postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@db:5432/$POSTGRES_DB" -c "
  CREATE TABLE IF NOT EXISTS integration_logs (
    id bigserial PRIMARY KEY,
    ts timestamptz,
    created_at timestamptz DEFAULT (now() AT TIME ZONE 'utc'),
    process_name text, step text, log_level text, status text, message text,
    run_id uuid, request_id text, job_id text, external_system text,
    elapsed_ms integer, retry_count integer DEFAULT 0, payload jsonb, payload_hash text, details jsonb
  );
  CREATE INDEX IF NOT EXISTS ix_integration_logs_time ON integration_logs (COALESCE(ts, created_at));
  "
}

echo "Starting app..."
exec ./start.sh  # если у тебя отдельный entrypoint для uvicorn — здесь его вызов
```

> Если у тебя уже есть `start.sh`, просто добавь блок «Running migrations…» **перед** стартом uvicorn/fastapi. Смысл: гарантированно создать `integration_logs` либо миграцией, либо аварийным DDL.
---

## Почему «не работало» (краткое резюме для фиксации в CHANGELOG)

* Админка ходила на неверный **порт** внутреннего сервиса `app` (`8000` вместо `80`) → `Connection refused`.
* Миграции не применялись на старте и/или alembic использовал `asyncpg`/неправильный URL → таблица `integration_logs` отсутствовала.

Исправлено перенастройкой `ADMIN_APP_URL` на `http://app`, синхронизацией `.env`/compose и гарантированным созданием таблицы миграцией (с аварийным DDL-фоллбеком).
