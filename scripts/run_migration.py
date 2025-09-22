#!/usr/bin/env python3
"""
Скрипт для запуска миграций Alembic с правильными переменными окружения
"""
import os
import subprocess
import sys

def run_migration():
    """Запускает миграции Alembic"""

    # Устанавливаем переменные окружения
    env = os.environ.copy()
    env['PYTHONPATH'] = '/app'
    env['DATABASE_URL'] = 'postgresql+asyncpg://user:password@localhost:5433/bisnesmedia'

    # Запускаем alembic
    try:
        result = subprocess.run([
            '/app/.venv/bin/alembic',
            'upgrade',
            'head'
        ], env=env, cwd='/app', capture_output=True, text=True)

        print("STDOUT:")
        print(result.stdout)
        print("STDERR:")
        print(result.stderr)
        print(f"Return code: {result.returncode}")

        return result.returncode == 0

    except Exception as e:
        print(f"Error running migration: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)