вижу обе причины на скрине:

1. **Триггер не доходит до приложения**
   `HTTPConnectionPool(host='app', port=8000)... Connection refused` — внутри docker-сети у контейнера `app` **внутренний порт 80** (снаружи он смаплен на 8000). Значит из админки нужно бить на `http://app` или `http://app:80`, а не `:8000`.

2. **SQL синтаксис периода**
   `syntax error at or near "60" ... INTERVAL %(:mins)s MINUTE` — это MySQL-стиль. В PostgreSQL так нельзя. Нужен `make_interval(mins => :mins)` (или `(:mins || ' minutes')::interval`).

Ниже даю чёткую задачу для кодера с **полными правками** (можно вставлять как единый промпт).

---

# TASK: Починить админ-панель — триггер и SQL под PostgreSQL

## 1) ENV: правильный URL приложения внутри docker-сети

В `.env` поменять:

```env
# было:
# ADMIN_APP_URL=http://app:8000
# стало (внутри сети сервис app слушает 80):
ADMIN_APP_URL=http://app
```

(Альтернатива: `http://app:80`.)

> На хосте по-прежнему открывается `http://localhost:8000`, но это не про межконтейнерное обращение.

## 2) `admin_panel/app.py` — заменить выражение с INTERVAL на Postgres-совместимое

### Было (фрагмент SQL):

```python
where.append("(COALESCE(ts, created_at) >= NOW() AT TIME ZONE 'UTC' - INTERVAL :mins MINUTE)")
```

### Стало (вариант 1 — предпочтительно, через make\_interval):

```python
where.append("(COALESCE(ts, created_at) >= (NOW() AT TIME ZONE 'UTC') - make_interval(mins => :mins))")
```

> `:mins` должен быть `int`.

### Если по версии PG нет `make_interval` — используем текстовый каст (вариант 2):

```python
where.append("(COALESCE(ts, created_at) >= (NOW() AT TIME ZONE 'UTC') - (:mins::text || ' minutes')::interval)")
```

### Итоговый блок выборки (полный кусок для замены)

```python
where = []
params: Dict[str, Any] = {"limit": limit, "mins": minutes}

# окно по времени (PG-совместимо)
where.append("(COALESCE(ts, created_at) >= (NOW() AT TIME ZONE 'UTC') - make_interval(mins => :mins))")

if level and level != "Все":
    where.append("(COALESCE(log_level, details->>'level') = :level)")
    params["level"] = level

if system and system != "Все":
    where.append("(COALESCE(external_system, 'INTERNAL') = :system)")
    params["system"] = system

if status and status != "Все":
    where.append("(COALESCE(status, 'INFO') = :status)")
    params["status"] = status

if step_like:
    where.append("(COALESCE(step, '') ILIKE :step)")
    params["step"] = f"%{step_like}%"

if run_id:
    where.append("(COALESCE(run_id, '') = :run_id)")
    params["run_id"] = run_id

where_sql = " AND ".join(where) if where else "TRUE"
sql = text(
    f"""
    SELECT
      COALESCE(ts, created_at) AS created_at,
      COALESCE(process_name, step) AS process_name,
      COALESCE(log_level, status) AS log_level,
      COALESCE(message, details->>'message') AS message,
      run_id, request_id, job_id, step, status, external_system,
      elapsed_ms, retry_count, payload_hash, details, payload
    FROM integration_logs
    WHERE {where_sql}
    ORDER BY COALESCE(ts, created_at) DESC
    LIMIT :limit
    """
)
```

## 3) Кнопка «Запустить оценку дефицита» — проверить URL

В `admin_panel/app.py` у места вызова:

```python
url = APP_URL.rstrip("/") + "/api/v1/trigger/internal-replenishment"
# APP_URL берётся из ENV; после шага (1) это http://app
```

Если нужен склад из поля `warehouse_id`, и ваш эндпоинт умеет его принимать — оставляем как было:

```python
payload = {"warehouse_id": warehouse_id.strip()} if warehouse_id.strip() else None
resp = requests.post(url, headers=headers, json=payload, timeout=30)
```

## 4) docker-compose: убедиться, что ENV проброшены в admin\_panel

```yaml
admin_panel:
  env_file:
    - .env
  environment:
    - ADMIN_DB_URL=${ADMIN_DB_URL}
    - ADMIN_APP_URL=${ADMIN_APP_URL}
    - ADMIN_POLL_SECONDS=${ADMIN_POLL_SECONDS:-5}
    - ADMIN_PAGE_SIZE=${ADMIN_PAGE_SIZE:-500}
  depends_on:
    - app
    - db
```

## 5) Перезапуск

```bash
docker compose -f docker-compose.dev.yml up -d --build admin_panel
```

## 6) Быстрая проверка

* Вверху панели должно показываться:
  `DB: db:5432/bisnesmedia | App: http://app`
* Кнопка «Запустить оценку дефицита» должна вернуть HTTP-статус 200/202 и JSON из вашего FastAPI.
* Таблица логов — без SQL ошибок; фильтр по периоду работает.

---

### Почему это сработает

* Межконтейнерные обращения идут по **внутренним портам сервисов**, а не по хостовым mapping-портам — поэтому нужен `http://app` (80), а не `:8000`.
* PostgreSQL не принимает `INTERVAL :mins MINUTE` — корректные варианты приведены выше.

Если после этого триггер всё ещё «refused» — это значит, что контейнер `app` не в сети `admin_panel` (проверь `depends_on`/`networks`) или приложение внутри `app` слушает не `0.0.0.0:80`. Тогда в `app` проверь команду запуска (uvicorn/gunicorn) — должен слушать `0.0.0.0`, порт 80.
