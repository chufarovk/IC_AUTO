# Changelog

Все заметные изменения в этом проекте документируются здесь.

Формат основан на Keep a Changelog.

## [Unreleased]

### Added
- Создан скрипт `scripts/test_1c_connection.py` для быстрой проверки доступности и аутентификации в API 1С.
 - Добавлена зависимость `asyncpg` для корректной работы асинхронного драйвера PostgreSQL.

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
 - main.py: убраны устаревшие декораторы `@asyncio.coroutine`; добавлен `/health/db`; миграции на старте можно отключать через `RUN_MIGRATIONS_ON_STARTUP`.
 - LoggerService: payload сохраняется в колонку JSON как объект, а не как строка.

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
