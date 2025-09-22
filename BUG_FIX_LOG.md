# Журнал Исправленных Ошибок (Bug Fix Log)

| ID  | Дата       | Компонент            | Описание Проблемы                                   | Описание Решения                                         | Версия Исправления |
|:----|:-----------|:---------------------|:----------------------------------------------------|:---------------------------------------------------------|:-------------------|
| B-1 | 2025-09-22 | `admin_panel`        | Триггер не доходит до приложения: ошибка подключения `HTTPConnectionPool(host='app', port=8000)... Connection refused` | Исправлен URL для межконтейнерных обращений с `http://app:8000` на `http://app` (внутренний порт 80) | Unreleased         |
| B-2 | 2025-09-22 | `admin_panel`        | SQL синтаксис ошибка: `syntax error at or near "60" ... INTERVAL %(:mins)s MINUTE` в PostgreSQL | Заменен MySQL-стиль SQL на PostgreSQL-совместимый: `INTERVAL :mins MINUTE` → `make_interval(mins => :mins)` | Unreleased         |
| B-3 | 2025-09-22 | `admin_panel`        | Отсутствие переменных окружения для админ-панели | Добавлены переменные окружения: `ADMIN_APP_URL`, `ADMIN_DB_URL`, `ADMIN_POLL_SECONDS`, `ADMIN_PAGE_SIZE` | Unreleased         |
| B-4 | 2025-09-22 | `docker-compose`     | Переменные окружения не пробрасывались в контейнер admin_panel | Обновлена конфигурация docker-compose для корректного проброса environment variables | Unreleased         |

