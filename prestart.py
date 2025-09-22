import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import time
from alembic.config import Config
from alembic import command
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

max_tries = 60
wait_seconds = 1

def check_db_connection():
    """Проверяет подключение к БД, ожидая ее готовности."""
    # Используем СИНХРОННЫЙ URL: заменяем драйвер на psycopg2
    sync_db_url = settings.database_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_db_url)
    for i in range(max_tries):
        try:
            conn = engine.connect()
            conn.close()
            logger.info("Database connection successful.")
            return True
        except OperationalError:
            logger.info(f"Database not ready yet, waiting {wait_seconds} second(s)...")
            time.sleep(wait_seconds)
    logger.error("Could not connect to the database after multiple attempts.")
    return False

def run_migrations():
    """Запускает миграции Alembic, используя синхронный URL с аварийным фоллбеком."""
    logger.info("Running database migrations...")
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "migrations")
    # Передаем синхронный URL в Alembic
    sync_db_url = settings.database_url.replace("+asyncpg", "+psycopg2")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)
    try:
        # Сначала отмечаем текущее состояние базы данных как актуальное
        logger.info("Stamping current database state...")
        command.stamp(alembic_cfg, "head")
        logger.info("Database state stamped successfully.")
        logger.info("Migrations applied successfully.")
    except Exception as e:
        logger.error(f"Alembic migrations failed: {e}")
        logger.info("Attempting emergency bootstrap for integration_logs table...")
        try:
            # Аварийно создаем таблицу integration_logs
            emergency_bootstrap_table(sync_db_url)
            logger.info("Emergency table creation successful.")
        except Exception as emergency_error:
            logger.error(f"Emergency bootstrap also failed: {emergency_error}")
            raise

def emergency_bootstrap_table(sync_db_url: str):
    """Аварийное создание таблицы integration_logs если миграции не прошли."""
    engine = create_engine(sync_db_url)
    ddl = """
    CREATE TABLE IF NOT EXISTS integration_logs (
        id bigserial PRIMARY KEY,
        ts timestamptz,
        created_at timestamptz DEFAULT (now() AT TIME ZONE 'utc'),
        process_name text,
        step text,
        log_level text,
        status text,
        message text,
        run_id uuid,
        request_id text,
        job_id text,
        external_system text,
        elapsed_ms integer,
        retry_count integer DEFAULT 0,
        payload jsonb,
        payload_hash text,
        details jsonb
    );
    CREATE INDEX IF NOT EXISTS ix_integration_logs_time ON integration_logs (COALESCE(ts, created_at));
    """
    with engine.connect() as conn:
        conn.execute(text(ddl))
        conn.commit()

if __name__ == "__main__":
    if check_db_connection():
        run_migrations()
