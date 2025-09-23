Отличная новость про Task010! Теперь по свежим ошибкам вижу три конкретных недочёта. Ниже — готовое ТЗ (Task011) с быстрыми хотфиксами и «правильными» фиксациями через миграции/код.

---

# Task011 — довести логирование и админку до идеала

## 1) Колонка `job_name` отсутствует в БД

**Симптом:** `UndefinedColumnError: column "job_name" of relation "integration_logs" does not exist` при вставке логов.

**Причина:** приложение уже пишет поле `job_name`, а миграции — нет.

### Быстрый хотфикс (можно сразу выполнить)

```sql
ALTER TABLE integration_logs ADD COLUMN job_name VARCHAR NULL;
```

Командой в контейнере:

```bash
docker compose -f docker-compose.dev.yml exec db psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "ALTER TABLE integration_logs ADD COLUMN IF NOT EXISTS job_name VARCHAR NULL;"
```

### Правильная фиксация (миграция)

Создать Alembic-миграцию `20250923113000_add_job_name_to_integration_logs.py`:

```python
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20250923113000"
down_revision = "20250923093000"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("integration_logs", sa.Column("job_name", sa.String(), nullable=True))

def downgrade():
    op.drop_column("integration_logs", "job_name")
```

И применить:

```bash
docker compose -f docker-compose.dev.yml exec -w /app app bash -lc ".venv/bin/python -m alembic upgrade head"
```

**Критерий приёмки:** вставки в `integration_logs` больше не падают на `job_name`.

---

## 2) SQL в админке: синтаксис интервала и оператор сравнения

**Симптомы:**

* `syntax error at or near "60"` из-за `INTERVAL 60 || ' minutes'`
* Использован символ `≥` вместо `>=`

**Исправление запроса:**

* Поменять условие времени на одно из корректных:

  * Вариант 1 (простой):
    `ts >= NOW() - (%(minutes)s || ' minutes')::interval`
  * Вариант 2 (самый чистый):
    `ts >= NOW() - make_interval(mins => %(minutes)s)`
* Заменить `≥` на `>=`.

### Как должно быть (фрагмент SQL в админке)

```sql
SELECT
  ts, run_id, request_id, job_id, job_name, step, status, external_system,
  elapsed_ms, retry_count, payload_hash, details, payload, process_name, log_level, message
FROM integration_logs
WHERE ts >= NOW() - make_interval(mins => %(minutes)s)
  AND (%(level)s  = 'ВСЁ' OR log_level = %(level)s)
  AND (%(system)s = 'ВСЁ' OR external_system = %(system)s)
  AND (%(status)s = 'ВСЁ' OR status = %(status)s)
  AND (%(step)s   IS NULL OR step ILIKE '%%' || %(step)s || '%%')
  AND (%(run_id)s IS NULL OR run_id::text = %(run_id)s)
ORDER BY ts DESC
LIMIT %(limit)s
```

> Если используете SQLAlchemy text(), просто замените строку запроса; параметры остаются те же.

**Критерий приёмки:** выборка логов отрабатывает без синтаксических ошибок при любом числе минут.

---

## 3) Streamlit в `admin`: `PermissionError: [Errno 13] Permission denied: '/nonexistent'`

**Симптом:** Streamlit пытается писать кэш/машинный ID в недоступный путь.

**Причина:** переменная окружения `HOME` или директории кеша указывают на недоступный путь в контейнере.

### Исправление (любой из вариантов, лучше оба)

1. В `Dockerfile.admin` (или `docker-compose.dev.yml` для сервиса admin) задать валидный домашний каталог и директории кэша:

```dockerfile
ENV HOME=/app \
    STREAMLIT_CONFIG_DIR=/app/.streamlit \
    XDG_CACHE_HOME=/tmp/xdg-cache
RUN mkdir -p /app/.streamlit /tmp/xdg-cache && chmod -R 777 /app/.streamlit /tmp/xdg-cache
```

или в compose:

```yaml
services:
  admin:
    environment:
      - HOME=/app
      - STREAMLIT_CONFIG_DIR=/app/.streamlit
      - XDG_CACHE_HOME=/tmp/xdg-cache
    volumes:
      - ./admin_data:/app/.streamlit
```

2. Запускать Streamlit с `--server.headless=true` (если не так уже).

**Критерий приёмки:** админка стартует без `PermissionError` и открывает страницу журналов.

---

## Проверка после фиксов

```bash
# Применить миграции
docker compose -f docker-compose.dev.yml exec -w /app app bash -lc ".venv/bin/python -m alembic upgrade head"

# Проверить схему
docker compose -f docker-compose.dev.yml exec db psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='integration_logs' ORDER BY 1;"

# Триггернуть процесс и убедиться, что логи пишутся
curl -X POST http://localhost:8000/api/v1/trigger/internal-replenishment

# В админке выбрать, например, 60 минут и убедиться, что выборка работает и строки видны
```

---

## Замечание по `job_id` vs `job_name`

Вы сделали правильно, что `job_id` оставили UUID, а «человеческое» имя джобы кладёте в `job_name` (TEXT). Это полностью решает риск из предыдущего таска (строковые идентификаторы фоновых задач).

---
