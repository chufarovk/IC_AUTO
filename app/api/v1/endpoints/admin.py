from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db_session
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/admin/init_logs_table", summary="Создать таблицу integration_logs")
async def init_logs_table(db: AsyncSession = Depends(get_db_session)):
    """
    Создает таблицу integration_logs если она не существует.
    Используется админ-панелью для инициализации логирования.
    """
    try:
        # DDL согласно Task006.md
        create_table_sql = text("""
            CREATE TABLE IF NOT EXISTS integration_logs (
              id          bigserial PRIMARY KEY,
              ts          timestamptz,
              created_at  timestamptz DEFAULT (now() AT TIME ZONE 'utc'),
              process_name text,
              step         text,
              log_level    text,
              status       text,
              message      text,
              run_id       text,
              request_id   text,
              job_id       text,
              external_system text,
              elapsed_ms   integer,
              retry_count  integer DEFAULT 0,
              payload      jsonb,
              payload_hash text,
              details      jsonb
            );
        """)

        create_index_sql = text("""
            CREATE INDEX IF NOT EXISTS ix_integration_logs_time
              ON integration_logs (COALESCE(ts, created_at));
        """)

        await db.execute(create_table_sql)
        await db.execute(create_index_sql)
        await db.commit()

        logger.info("Integration logs table created/verified successfully")
        return {"status": "success", "message": "Table integration_logs created or already exists"}

    except Exception as e:
        logger.error(f"Failed to create integration_logs table: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create table: {str(e)}")