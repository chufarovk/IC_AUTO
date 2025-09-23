Вот готовое ТЗ для разработчика — компактно, по пунктам, с критериями приёмки и командами для воспроизведения.

---

# ТЗ: Починить миграции/ORM, логирование и сборку Docker

## Контекст/проблемы

1. В контейнере `app` не находится `alembic` в `$PATH` → миграции не применяются вручную.
2. БД и ORM были «рассинхронизированы»: `integration_logs.run_id/request_id/job_id` в БД — `UUID`, а приложение пыталось писать `VARCHAR`; поля `payload/details` должны быть `JSONB`.
3. Фоновые задачи APScheduler падают при записи логов из-за несовпадения типов и импорта `async_session`.
4. Админ-панель валится на сравнении `DataFrame == "TABLE_NOT_EXISTS"` (ошибка `The truth value of a DataFrame is ambiguous`).
5. Сборка образа ломается на `apt-get` (502 Bad Gateway) — нет ретраев; в `docker-compose.dev.yml` устаревшее поле `version`.
6. На старте приложение печатает “Failed to get migration heads” — Alembic не видит каталог миграций/метадату.

---

## Цели

* Привести модели/миграции и код логирования к схеме БД (UUID/JSONB).
* Обеспечить стабильное применение миграций на старте и вручную из контейнера.
* Починить импорт и экспорт `async_session`.
* Исправить логику отображения логов в админ-панели.
* Устойчиво собирать Docker-образы.
* Убрать устаревшие настройки compose.

---

## Задачи

### A. Миграции и запуск

1. **Alembic в контейнере**

   * Убедиться, что `alembic` установлен в виртуальную среду `/app/.venv`.
   * В `start.sh` вызывать миграции так, чтобы не требовался глобальный `alembic`:

     * Вариант 1: `/app/.venv/bin/alembic upgrade head`
     * Вариант 2: `python -m alembic upgrade head` (из рабочей директории `/app`)
   * Проверить, что `alembic.ini` доступен по пути `/app/alembic.ini`, а `script_location = migrations`.

2. **Здоровье Alembic**

   * В `migrations/env.py` корректно задать `target_metadata` (импорт из ваших моделей).
   * На старте приложения, если «голов нет» (`heads == []`), выводить понятный лог и не падать; запускать `upgrade head`.

3. **Синхронизация схемы**

   * Оставить/добавить миграцию, которая:

     * Кастует `integration_logs.run_id/request_id/job_id` → `UUID` (некорректные строки — в `NULL`, с логом количества).
     * Кастует `details/payload` → `JSONB`.
     * Пересоздаёт индексы при необходимости.
   * Миграция должна быть идемпотентной (повторный прогон не ломает схему).

### B. ORM и логирование

1. **Модель логов**

   * В `app/models/log.py` поля `run_id/request_id/job_id` типизировать как `UUID` (Python `uuid.UUID`) и в БД `UUID`.
   * `details/payload` — тип `JSONB`.
   * Проверить маппинг и индексы.

2. **Сервис логирования**

   * В `app/services/logger_service.py` при записи логов:

     * Нормализовать `run_id`, `request_id`, `job_id`: приводить к `uuid.UUID` (или `None`) если пришли строками.
     * `payload/details` — гарантировать сериализуемость в JSON.
   * Для фоновых задач: если нужно хранить «имя» задачи (например, `process_outbox_events_job`), **добавить отдельное поле** `job_name TEXT` (опционально, но желательно). `job_id` оставить UUID.

3. **Сессия БД**

   * В `app/db/session.py` использовать `async_sessionmaker` и экспортировать ожидаемые символы:

     * Фабрика: `async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)`
     * Совместимость: экспорт `async_session` как **callable** (или контекст-менеджер), чтобы старые импорты `from app.db.session import async_session` работали.
   * Проверить все места, где импортируется `async_session` (например, `logger_service.py`) — никаких `ImportError`.

### C. Админ-панель

1. Исправить проверку результата выборки логов (строка/DF):

   ```python
   # было: if logs_df == "TABLE_NOT_EXISTS":
   if isinstance(logs_df, str) and logs_df == "TABLE_NOT_EXISTS":
       st.warning("Таблица логов отсутствует. Примените миграции.")
   elif logs_df is None or (isinstance(logs_df, pd.DataFrame) and logs_df.empty):
       st.info("Нет записей за выбранный период.")
   else:
       st.dataframe(logs_df, use_container_width=True)
   ```
2. По возможности отказаться от «магической строки» и возвращать строго `pd.DataFrame` или поднимать/ловить исключение — но это необязательно для текущего фикса.

### D. Docker: сборка и compose

1. **Устойчивое `apt-get`**

   * В `Dockerfile` (builder stage) добавить ретраи и/или `--fix-missing`, например:

     ```dockerfile
     RUN set -eux; \
       apt-get update; \
       apt-get install -y --no-install-recommends build-essential libpq-dev \
       || (sleep 3 && apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev); \
       rm -rf /var/lib/apt/lists/*
     ```
   * Либо `-o Acquire::Retries=3`.

2. **Compose**

   * Удалить устаревшее поле `version` из `docker-compose.dev.yml` (Docker сейчас ругается, но запускает).

### E. Документация/диагностика

1. В `README`/`F1` добавить:

   * Как применить миграции **вручную**:

     ```bash
     docker compose -f docker-compose.dev.yml exec -w /app app bash -lc "/app/.venv/bin/alembic upgrade head"
     # или
     docker compose -f docker-compose.dev.yml exec -w /app app bash -lc "python -m alembic upgrade head"
     ```
   * Команды проверки типов колонок:

     ```bash
     docker compose -f docker-compose.dev.yml exec db psql -U $POSTGRES_USER -d $POSTGRES_DB \
       -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='integration_logs' ORDER BY 1;"
     ```
   * Как смотреть логи:

     ```bash
     docker compose -f docker-compose.dev.yml logs -f --tail=200 app db admin
     docker compose -f docker-compose.dev.yml logs app --since=30m
     ```

---

## Критерии приёмки (DoD)

* ✅ При старте стека (`docker compose up -d`) в логах `app` видно успешное применение миграций; отсутствуют сообщения “Failed to get migration heads”.
* ✅ Таблица `integration_logs` имеет типы:
  `run_id/request_id/job_id` → `uuid`; `payload/details` → `jsonb`.
* ✅ POST `/api/v1/trigger/internal-replenishment` записывает лог без ошибок `DatatypeMismatchError` и без `ImportError: async_session`.
* ✅ APScheduler-джоб `process_outbox_events_job` пишет `INFO`-сообщения в `integration_logs` без исключений каждые 30 сек.
* ✅ Страница логов в админ-панели открывается без `ValueError: The truth value of a DataFrame is ambiguous`; при пустом результате выводится информативное сообщение.
* ✅ Сборка образов проходит стабильно; больше нет падений из-за 502 на `apt-get`.
* ✅ В `docker-compose.dev.yml` нет поля `version`.

---

## Шаги для проверки (QA)

1. Полный rebuild:

   ```bash
   docker compose -f docker-compose.dev.yml build --no-cache app
   docker compose -f docker-compose.dev.yml up -d --force-recreate
   ```
2. Ручной прогон миграции (на всякий случай):

   ```bash
   docker compose -f docker-compose.dev.yml exec -w /app app bash -lc "/app/.venv/bin/alembic upgrade head"
   ```
3. Проверка схемы:

   ```bash
   docker compose -f docker-compose.dev.yml exec db psql -U $POSTGRES_USER -d $POSTGRES_DB \
     -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='integration_logs' ORDER BY 1;"
   ```
4. Триггерни процесс:

   * Через админ-панель или:

     ```bash
     curl -X POST http://localhost:8000/api/v1/trigger/internal-replenishment
     ```
   * Убедись, что в логах `app` нет ошибок, а в БД появилась запись:

     ```bash
     docker compose -f docker-compose.dev.yml exec db psql -U $POSTGRES_USER -d $POSTGRES_DB \
       -c "SELECT run_id, request_id, job_id, jsonb_typeof(payload) AS ptype FROM integration_logs ORDER BY created_at DESC LIMIT 5;"
     ```
5. Дай фоновому джобу отработать 1–2 минуты и проверь, что новые записи появляются без ошибок в `app/db` логах и видны в админке.

---

## Файлы к изменению (ориентировочно)

* `start.sh` — вызов миграций через venv/`python -m alembic`.
* `alembic.ini` — `script_location = migrations` (если отличается).
* `migrations/env.py` — `target_metadata`.
* `migrations/versions/*` — миграция приведения типов UUID/JSONB + индексы.
* `app/models/log.py` — типы `UUID`, `JSONB`.
* `app/services/logger_service.py` — нормализация UUID/JSON, использование `async_session`.
* `app/db/session.py` — `async_sessionmaker` и экспорт `async_session`.
* `admin_panel/app.py` — исправление проверки `DataFrame`.
* `Dockerfile` — ретраи `apt-get`.
* `docker-compose.dev.yml` — убрать `version`.
* `README.md` — разделы про миграции/логи.

---

Если нужно — добавлю SQL/миграцию-скелет и точечные диффы по файлам.