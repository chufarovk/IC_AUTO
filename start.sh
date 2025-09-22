#!/bin/bash
set -e

# Запускаем скрипт prestart, который проверит БД и накатит миграции
./.venv/bin/python prestart.py

# После успешного выполнения prestart, запускаем Uvicorn без hot-reload
exec ./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 80
