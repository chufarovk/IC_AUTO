from __future__ import annotations

import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# импортируем базовый класс и модели, чтобы автогенерация видела таблицы
from app.db.base_class import Base
from app.models.log import IntegrationLog  # noqa: F401 - регистрируем модель
from app.models.transfer import PendingTransfer  # noqa: F401 - регистрируем модель
from app.models.outbox import OutboxEvent  # noqa: F401 - регистрируем модель

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

def _alembic_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    # Alembic работает синхронно; если в env asyncpg – заменим на psycopg2
    return url.replace("+asyncpg", "+psycopg2")

config.set_main_option("sqlalchemy.url", _alembic_url())

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
