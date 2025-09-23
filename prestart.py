import logging
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_TRIES = 60
WAIT_SECONDS = 1


def _sync_db_url() -> str:
    return settings.database_url.replace("+asyncpg", "+psycopg2")


def check_db_connection() -> bool:
    """Ensure database is reachable before running migrations."""
    engine = create_engine(_sync_db_url())
    for _ in range(MAX_TRIES):
        try:
            with engine.connect():
                logger.info("Database connection successful.")
                return True
        except OperationalError:
            logger.info("Database not ready yet, waiting %s second(s)...", WAIT_SECONDS)
            time.sleep(WAIT_SECONDS)
    logger.error("Could not connect to the database after multiple attempts.")
    return False


def run_migrations() -> None:
    """Run Alembic migrations using the local configuration."""
    logger.info("Running database migrations...")
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "migrations")
    alembic_cfg.set_main_option("sqlalchemy.url", _sync_db_url())
    try:
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations applied successfully.")
    except Exception as exc:
        logger.error("Alembic migrations failed: %s", exc)
        logger.info("Attempting emergency bootstrap for integration_logs table...")
        try:
            emergency_bootstrap_table()
            logger.info("Emergency table creation successful.")
        except Exception as emergency_error:
            logger.error("Emergency bootstrap also failed: %s", emergency_error)
            raise


def emergency_bootstrap_table() -> None:
    """Create integration_logs with the expected schema as a last-resort fallback."""
    engine = create_engine(_sync_db_url())
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
        request_id uuid,
        job_id uuid,
        job_name text,
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
