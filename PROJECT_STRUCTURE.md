# Project Structure Document

Этот документ описывает каноническую структуру каталогов и модулей проекта "bisnesmedia Integration Hub". Все изменения и добавления в кодовую базу должны строго соответствовать этой структуре.

## Общая Структура Каталогов
```
bisnesmedia/
├── .github/
│   └── workflows/
│       └── ci-cd.yml # CI/CD пайплайн
├── admin_panel/
│   └── app.py # Streamlit административная панель (MVP)
├── alembic.ini # Конфигурация Alembic
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── deps.py # Зависимости для API
│   │       └── endpoints/ # Роутеры (контроллеры)
│   ├── background/
│   │   └── jobs.py # Фоновые задачи (APScheduler)
│   ├── core/
│   │   └── config.py # Конфигурация (Pydantic Settings)
│   ├── db/
│   │   ├── base_class.py # Базовый класс и TimestampMixin SQLAlchemy
│   │   └── session.py # Управление асинхронными сессиями БД
│   ├── integrations/
│   │   ├── base_client.py # Базовый API-клиент
│   │   ├── one_s_client.py # Клиент для 1С
│   │   └── moysklad_client.py # Клиент для МойСклад
│   ├── models/ # Модели SQLAlchemy (ORM)
│   ├── schemas/ # Схемы Pydantic (DTO)
│   ├── services/ # Слой бизнес-логики
│   └── main.py # Точка входа FastAPI
├── migrations/
│   ├── env.py # Настройка Alembic окружения
│   └── versions/
│       └── <timestamp>_create_integration_logs_table.py
├── tests/
│   ├── conftest.py
│   ├── test_api/
│   └── test_services/
├── .env.example
├── .gitignore
├── Dockerfile
├── Dockerfile.admin
├── docker-compose.yml # Production оркестрация (готовые образы)
├── docker-compose.dev.yml # Development оркестрация (hot-reload, локальная сборка)
├── Dockerfile.admin
├── scripts/
│   └── test_1c_connection.py # Скрипт проверки подключения к API 1С
├── poetry.lock
├── pyproject.toml
└── README.md
```

## Описание Ключевых Директорий

### `app/`
Основной пакет с исходным кодом приложения.

- **`app/api/`**: Слой Маршрутизации (Routing Layer).
  - Назначение: Принимать HTTP-запросы, валидировать их с помощью схем из `schemas`, вызывать соответствующую функцию из `services` и возвращать HTTP-ответ.
  - Правило: Роутеры должны быть "тонкими" и не содержать никакой бизнес-логики.

- **`app/services/`**: Слой Бизнес-логики (Business Logic Layer).
  - Назначение: Это сердце приложения. Вся логика принятия решений, расчеты, координация между API-клиентами и базой данных находится здесь.
  - Правило: Сервисы не должны ничего знать о HTTP. Они принимают простые типы данных или Pydantic-модели и возвращают их же.

- **`app/integrations/`**: Слой Интеграций (Integration Layer).
  - Назначение: Изолирует всю логику взаимодействия с внешними API (1С, МойСклад, Telegram). Здесь реализуются отказоустойчивые клиенты с `HTTPX` и `tenacity`.
  - Правило: Код в других частях приложения никогда не должен вызывать `httpx` напрямую, а только через клиенты из этого модуля.

- **`app/models/`**: Слой Данных (Data Models Layer).
  - Назначение: Определения таблиц базы данных с помощью SQLAlchemy ORM. Описывает, как наши данные хранятся в PostgreSQL.

- **`app/schemas/`**: Слой Контрактов Данных (Data Contracts Layer).
  - Назначение: Определения структур данных для API с помощью Pydantic. Они служат "контрактом" для входящих и исходящих данных API и используются для валидации.

- **`app/db/`**: Управление Базой Данных.
  - Назначение: Содержит код для настройки подключения к БД, управления сессиями и базовые классы для ORM-моделей.

- **`app/core/`**: Ядро Приложения.
  - Назначение: Глобальная конфигурация приложения, загружаемая из переменных окружения.

- **`app/background/`**: Фоновые Процессы.
  - Назначение: Определение и конфигурация фоновых задач, которые будут выполняться с помощью `APScheduler` (например, опрос статусов в 1С).

### `tests/`
Содержит все автоматизированные тесты. Структура директорий внутри `tests/` должна зеркально отражать структуру `app/` для удобства навигации.

### `scripts/`
Вспомогательные скрипты и утилиты, не являющиеся частью основного приложения, для локальных проверок, отладки и ад-хок задач.

- `scripts/test_1c_connection.py` — standalone-скрипт для быстрой проверки доступности и аутентификации в API 1С (использует переменные `API_1C_*` из `.env`).

## Дополнения к сервисам и эндпоинтам (Epic 2)

- В `app/services/` добавлены:
  - `logger_service.py` — запись событий в таблицу `integration_logs`.
  - `replenishment_service.py` — ядро Алгоритма 1 (read-only), использует 1С‑клиент.
- В `app/api/v1/endpoints/` добавлен:
  - `replenishment.py` — эндпоинт-триггер `POST /api/v1/trigger/internal-replenishment`.

## Дополнения к моделям (Epic 3)

- В `app/models/` добавлены:
  - `transfer.py` — модель `PendingTransfer` для управления состоянием внутренних перемещений.
  - `outbox.py` — модель `OutboxEvent` для паттерна Transactional Outbox.

## Фоновые процессы (Epic 3)

- В `app/services/` добавлен:
  - `outbox_processor_service.py` — сервис обработки очереди `outbox_events`, отправляет запросы во внешние системы и обновляет статусы.
- В `app/background/` добавлен:
  - `jobs.py` — содержит задачу `process_outbox_events_job` для запуска через APScheduler.

## Обновление задач планировщика (Epic 4)

- Планировщик `APScheduler` запускается с часовым поясом `Europe/Moscow`.
- В `app/background/jobs.py` добавлена задача:
  - `run_internal_replenishment_job` — ежедневный запуск процесса пополнения по будням в 09:00 (МСК).

## Дополнения к интеграциям и схемам (Epic 5)

- В `app/integrations/` добавлен:
  - `moysklad_client.py` — клиент для API МойСклад (проверка остатков, создание "Заказа покупателя").
- В `app/schemas/` добавлен:
  - `moy_sklad.py` — Pydantic‑схемы для работы с объектами МойСклад (meta, позиции заказа, payload/response заказа).

## Панель Администратора (Epic 5)

- В корне добавлена директория `admin_panel/` с приложением Streamlit:
  - `admin_panel/app.py` — отображает журнал `integration_logs` и предоставляет кнопки для ручного запуска процессов.
- Добавлен `Dockerfile.admin` для сборки контейнера панели администратора.

## Оркестрация и CI/CD (Epic 6)

- CI/CD: в `.github/workflows/ci-cd.yml` настроены линтеры (ruff, mypy), тесты (pytest) и сборка/публикация образов в GHCR.
- Docker: два compose-файла — `docker-compose.dev.yml` для разработки (hot-reload), `docker-compose.yml` для production (готовые образы, restart: always).
