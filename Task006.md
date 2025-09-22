# IC\_AUTO — полное обследование и план починки

## Что уже видно по репо

* В репозитории есть **два compose-файла**: `docker-compose.dev.yml` и `docker-compose.yml` — это нормально, но сейчас они расходятся и путают окружение. Нужно привести к единому контракту переменных и DNS-имён сервисов. ([GitHub][1])
* README ориентирует на запуск всего стека через `docker-compose.dev.yml` и админку на `:8501`. Это и берём за основу рабочего сценария. ([GitHub][1])
* README описывает, что админ-панель дергает приложение по `ADMIN_APP_URL` (дефолт `http://app:8000`) и ходит в БД по `ADMIN_DB_URL` (дефолт `db:5432`). Значит, именно эти значения должны быть по умолчанию **внутри Docker-сети**. ([GitHub][1])

---

## Цели задачи

1. Кнопка «Запустить оценку дефицита» в админ-панели **стабильно** триггерит API приложения (без `Name or service not known`).
2. БД доступна из **app** и **admin\_panel** по адресу `db:5432`.
3. Логи в админ-панели отображаются (таблица `integration_logs` существует или корректно создаётся миграцией).
4. Бекенд корректно понимает любые ответы 1С по эндпоинту дефицита (чтобы не падать `string indices must be integers, not 'str'`).
5. Единый `.env.example` и `.env` с валидными дефолтами; README обновлён.

---

## Рабочие пакеты (выполнять по порядку)

### A. Окружение: переменные и Docker DNS

**Задача A1.** Привести `.env.example` и `.env` к единому контракту (для Docker):

```dotenv
# APP
PROJECT_NAME="bisnesmedia Integration Hub"
DEBUG=true

# DB (для контейнеров!)
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=bisnesmedia
POSTGRES_SERVER=db
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/bisnesmedia

# 1C API
API_1C_URL=http://84.23.42.102/businessmedia_ut
API_1C_USER=Программист
API_1C_PASSWORD=cO7cu4vi

# ADMIN PANEL
ADMIN_DB_URL=postgresql+psycopg2://user:password@db:5432/bisnesmedia
ADMIN_APP_URL=http://app:8000
ADMIN_POLL_SECONDS=5
ADMIN_PAGE_SIZE=500
ADMIN_TRIGGER_TOKEN=
```

> Пояснение: **никаких `localhost` внутри контейнеров**. Имена сервисов — `app` и `db`. В README это и зафиксировано (дефолт `http://app:8000`, `db:5432`). ([GitHub][1])

**Задача A2.** В `docker-compose.dev.yml` зафиксировать одинаковые имена сервисов (`app`, `db`, `admin_panel`) и переменные окружения только через `.env`. Убедиться, что:

* `db` слушает наружу `5433:5432`, но **внутри** сети все ходят на `db:5432`.
* `app` публикуется на `8000:80`.
* `admin_panel` зависит от `db` (healthy) и `app` (started).
  README рекомендует именно `docker-compose.dev.yml` как основной сценарий запуска. ([GitHub][1])

**Задача A3.** В `admin_panel/app.py` добавить надёжный фоллбек адреса приложения:

```python
# admin_panel/app.py
import os, socket

def resolve_app_base_url() -> str:
    url = os.getenv("ADMIN_APP_URL", "").strip()
    if url:
        return url
    try:
        socket.gethostbyname("app")
        return "http://app:8000"
    except Exception:
        return "http://localhost:8000"  # если админку запускают вне Docker

APP_BASE = resolve_app_base_url()
```

Все HTTP-вызовы приложения делать через `APP_BASE`. Это закроет ошибку `Name or service not known`.

---

### B. База данных и логи

**Задача B1.** Миграция Alembic: создать таблицу `integration_logs`, если её нет.

DDL:

```sql
CREATE TABLE IF NOT EXISTS integration_logs (
  id          bigserial PRIMARY KEY,
  ts          timestamptz,
  created_at  timestamptz DEFAULT (now() AT TIME ZONE 'utc'),
  process_name text,
  step         text,
  log_level    text,
  status       text,
  message      text,
  run_id       uuid,
  request_id   text,
  job_id       text,
  external_system text,
  elapsed_ms   integer,
  retry_count  integer DEFAULT 0,
  payload      jsonb,
  payload_hash text,
  details      jsonb
);
CREATE INDEX IF NOT EXISTS ix_integration_logs_time
  ON integration_logs (COALESCE(ts, created_at));
```

**Задача B2.** В админ-панели: SQL-запрос логов должен:

* Работать, даже если часть колонок отсутствует (использовать `COALESCE`/`NULLIF`).
* Возвращать данные за период с параметром по минутам (use `make_interval(mins => :mins)`).
* Уметь «мягко» пережить отсутствие таблицы: ловить `UndefinedTable` и показывать баннер «таблица логов не создана» с кнопкой «создать сейчас» (POST в app на вспомогательный `/admin/init_logs_table`).

---

### C. Бекенд: надёжный парсер ответов 1С (дефицит)

Симптом из логов: `string indices must be integers, not 'str'` — это значит, мы пытались читать словарь по строковому ключу, а пришёл **массив**/строка/«двойной JSON». Задача — сделать единый «нормализатор» ответов 1С.

**Задача C1.** В модуле интеграции 1С (клиент 1С API) добавить функцию:

```python
def parse_1c_json(text: str) -> dict | list:
    """
    Пытаемся распарсить:
    1) Чистый JSON: объект или список
    2) Двойной JSON (строка, внутри которой ещё JSON)
    3) XDTO-форма: {"#value":[{"name":{"#value":"error"},"Value":{"#value":"..."}} ...]}
    4) Тело с BOM/мусором по краям
    Возвращаем питоновский объект или бросаем IntegrationError с нормальным сообщением.
    """
```

Алгоритм:

1. Сначала `json.loads(text)`; если упало — попробовать `json.loads(json.loads(text))` (двойная сериализация).
2. Если результат — dict с ключом `#value`, преобразовать в нормальный dict/список вида:

   * Если внутри `name/#value == "error"` → поднять `IntegrationError(message=<Value/#value>)`.
   * Если внутри лежат поля сущностей — вернуть нормальный список объектов.
3. Если это строка — попытаться «ещё раз» (двойной JSON).
4. Все числовые поля привести к `Decimal`/`float` (например `min_stock`, `max_stock`, `current_stock`).
5. Если структура не распознана — лог и `IntegrationError("Unexpected 1C response schema")`.

**Задача C2.** В коде процесса пополнения:

* Использовать нормализатор выше и **валидацию** каждого элемента: обязательные поля `id`, `name`, `min_stock`, `current_stock` (и опционально `max_stock`).
* Явно поддержать **пустой массив** (дефицита нет) — это не ошибка.
* На любой ошибке 1С (HTTP 4xx/5xx или XDTO-ошибка) логировать **детали** и выбрасывать осмысленное исключение с текстом из 1С.

**Задача C3.** Юнит-тесты на парсер с фикстурами 4 формата:

* `[]` (дефицита нет);
* валидный массив объектов;
* XDTO-ошибка (`#value` → `error`);
* двойной JSON/строка.

---

### D. Здоровье и старт

**Задача D1.** Health-эндпойнты:

* `GET /` → `{ "status": "ok" }` (описано в README) — проверить, что отрабатывает. ([GitHub][1])
* `GET /health/db` — успешный коннект к `DATABASE_URL` → `{ "db": "ok" }`.

**Задача D2.** Скрипт запуска `start.sh`: убедиться, что (опционально) выполняются миграции Alembic на старте (переменная `RUN_MIGRATIONS_ON_STARTUP=true/false`), как советует README для dev. ([GitHub][1])

---

### E. CI и артефакты

**Задача E1.** GitHub Actions:

* Линт + тесты (pytest) на PR в `master`.
* Сборка dev-образов `app` и `admin_panel`.
* (Опционально) push в GHCR по тегу `:dev` на `master`.

---

### F. Документация

**Задача F1.** Обновить README:

* «Быстрый старт»:

  ```bash
  cp .env.example .env
  docker compose -f docker-compose.dev.yml up -d --build
  # app: http://localhost:8000, admin: http://localhost:8501
  ```
* Пояснение про DNS-имена в Docker сети (`app`, `db`), и фоллбек `localhost` при локальном запуске админки вне Docker.
* Раздел «Типичные ошибки и решения»:

  * `Name or service not known` — см. ADMIN\_APP\_URL и DNS (`app`).
  * `UndefinedTable integration_logs` — прогоните миграцию или воспользуйтесь кнопкой «создать таблицу логов».
  * Ошибки 1С — см. нормализатор/логи.



## Примечания

* Мы опираемся на текущую модель запуска из README (`docker-compose.dev.yml` и дефолтные пути/порты). Это задокументировано прямо в репозитории (разделы «Быстрый старт», «Админ-панель», конфиги по умолчанию) — держим поведение таким же. ([GitHub][1])
