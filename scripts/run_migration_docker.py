#!/usr/bin/env python3
"""
Скрипт для выполнения миграции через Docker
"""
import subprocess
import sys

def run_migration():
    """Выполнить миграцию через Docker"""
    try:
        # Команда для выполнения миграции внутри контейнера
        cmd = [
            "docker", "run", "--rm",
            "--network", "container:bisnesmedia_db",
            "-v", f"{sys.path[0]}/../:/app",
            "-w", "/app",
            "python:3.11-slim",
            "bash", "-c",
            "pip install alembic sqlalchemy psycopg2-binary && alembic upgrade head"
        ]

        print("Выполняем миграцию...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("Миграция выполнена успешно!")
            print(result.stdout)
        else:
            print("Ошибка при выполнении миграции:")
            print(result.stderr)
            return False

        return True

    except Exception as e:
        print(f"Ошибка: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)