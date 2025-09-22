# Changelog

Все заметные изменения в этом проекте документируются здесь.

Формат основан на Keep a Changelog.

## [Unreleased]

### Added
- Создан скрипт `scripts/test_1c_connection.py` для быстрой проверки доступности и аутентификации в API 1С.
- Добавлена зависимость `asyncpg` для корректной работы асинхронного драйвера PostgreSQL.
- **Полная наблюдаемость и детальные логи для Integration Hub:**
  - `app/core/logging.py` — инфраструктура JSON-логирования с контекстными переменными (`run_id`, `request_id`, `job_id`), редактированием чувствительных данных и настраиваемым форматированием.
  - `app/core/observability.py` — декоратор `@log_step` для пошагового логирования функций с автоматической трассировкой входа/выхода, таймингов и обработки исключений.
  - Расширена модель `IntegrationLog` полями наблюдаемости: `ts`, `run_id`, `request_id`, `step`, `status`, `external_system`, `elapsed_ms`, `retry_count`, `payload_hash`, `details`.
  - Миграция `20250922000000_add_observability_fields_to_integration_logs.py` для добавления новых полей с обратной совместимостью.
  - Функция `log_event()` в `logger_service.py` для стандартизированного логирования событий в БД.
  - Детальное HTTP-логирование в `base_client.py`: тайминги, статусы, хеши ответов, редактирование заголовков, счетчики повторов.
  - Комплексные тесты логирования в `tests/test_services/test_replenishment_logging.py` и `tests/test_integrations/test_http_logging.py`.
  - Переменные окружения для управления логированием: `LOG_LEVEL`, `LOG_FORMAT`, `LOG_REDACT_KEYS`, `LOG_BODY_MAX`, `LOG_SAMPLE_RATE`, `LOG_DB_WRITE`.

### Changed
- Улучшен скрипт `test_1c_connection.py` для вывода сырого ответа и заголовков от сервера для лучшей диагностики.
- Скрипт `test_1c_connection.py` теперь явно запрашивает JSON-ответ от сервера 1С.
- `app/integrations/one_s_client.py` переписан для работы с кастомным 1С API (`/hs/integrationapi/`) вместо OData; методы возвращают простые dict.
- Обновлены переменные окружения: `API_1C_URL` теперь указывает на базу публикации (без `/odata/...`), пример в `.env.example`.
- Docker: переведены Dockerfile/Dockerfile.admin на сборку зависимостей через `poetry export` + `pip install`.
- Docker: добавлен `ENTRYPOINT ["python","-m"]` для гарантированного запуска CLI (`uvicorn`, `streamlit`) независимо от PATH.
- Docker Compose (dev): команды упрощены до `uvicorn ...` и `streamlit ...`; благодаря ENTRYPOINT они выполняются как `python -m ...`.
- Dockerfile.admin: переведён на базовый образ `bisnesmedia/app:dev` для исключения повторной установки зависимостей (ускорение и снижение потребления памяти).
- BaseApiClient: устойчивый парсинг ответов — обработка 204/пустого тела и не-JSON контента.
- main.py: убраны устаревшие декораторы `@asyncio.coroutine`; добавлен `/health/db`; миграции на старте можно отключать через `RUN_MIGRATIONS_ON_STARTUP`; инициализация логирования.
- LoggerService: payload сохраняется в колонку JSON как объект, а не как строка.
- **ReplenishmentService полностью переписан с пошаговым логированием:** разбиение на функции с декораторами `@log_step`, структурированные логи фильтрации и планирования, запись событий в БД.
- **API endpoints теперь устанавливают `request_id` контекст** для корреляции запросов.
- **Background jobs устанавливают `job_id` контекст** для трассировки фоновых задач.

## [1.0.0] - YYYY-MM-DD

### Added
- Асинхронное подключение к БД и фабрика сессий (`app/db/session.py`).
- Базовый класс моделей и TimestampMixin (`app/db/base_class.py`).
- Модель `IntegrationLog` и миграции Alembic для таблицы `integration_logs`.
- Конфигурация Alembic (`alembic.ini`, `migrations/`).
- Read-only клиент для 1С: базовый клиент и `OneSApiClient`.
- `LoggerService` для записи событий в `integration_logs`.
- `ReplenishmentService` (ядро Алгоритма 1, read-only).
- Эндпоинт API `POST /api/v1/trigger/internal-replenishment` для запуска процесса.
- Модели `PendingTransfer` и `OutboxEvent` для управления состоянием и Transactional Outbox.
- Реализована логика создания "Заказа на перемещение" через паттерн Transactional Outbox (создание записей `PendingTransfer` и `OutboxEvent`).
- Фоновый процесс (APScheduler) для обработки очереди `outbox_events` и отправки запросов в 1С.
- Настроен автоматический запуск процесса внутреннего пополнения по расписанию (Пн-Пт в 9:00 МСК).
- API‑клиент для МойСклад с методами получения остатков и создания "Заказа покупателя".
- Реализована логика создания "Заказа покупателя" в МойСклад при отсутствии товара на внутренних складах (через outbox).
- Создана Панель Администратора на Streamlit для мониторинга логов и ручного запуска процессов.
- Настроен CI/CD пайплайн для автоматического тестирования и сборки Docker-образов.

### Changed
- Сервис `ReplenishmentService` теперь проверяет наличие активных перемещений перед созданием нового заказа.
- `OutboxProcessorService` теперь обрабатывает события типа `CREATE_MS_CUSTOMER_ORDER`.

## [0.1.0] - YYYY-MM-DD

### Added
- Начальная структура проекта: FastAPI, Poetry, Docker.
- Основные документы: PRD, PROJECT_STRUCTURE, README.
- Настроен CI/CD пайплайн для линтинга и тестирования.
