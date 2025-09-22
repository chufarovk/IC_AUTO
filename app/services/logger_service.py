import datetime as dt
import os
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert

from app.models.log import IntegrationLog
from app.core.logging import run_id_var, request_id_var


class LoggerService:
    def __init__(self, session: AsyncSession, process_name: str):
        self.session = session
        self.process_name = process_name

    async def _log(self, level: str, message: str, payload: dict | None = None):
        log_entry = IntegrationLog(
            process_name=self.process_name,
            log_level=level,
            message=message,
            payload=payload,
        )
        self.session.add(log_entry)
        await self.session.commit()

    async def info(self, message: str, payload: dict | None = None):
        await self._log("INFO", message, payload)

    async def error(self, message: str, payload: dict | None = None):
        await self._log("ERROR", message, payload)

    async def warning(self, message: str, payload: dict | None = None):
        await self._log("WARNING", message, payload)

    async def debug(self, message: str, payload: dict | None = None):
        await self._log("DEBUG", message, payload)


async def log_event(*, step: str, status: str, external_system: str | None = None,
                    elapsed_ms: int | None = None, retry_count: int | None = None,
                    payload_hash: str | None = None, details: dict[str, Any] | None = None,
                    run_id: str | None = None, request_id: str | None = None):
    """
    Centralized function to log standardized events to integration_logs table.
    Uses new observability fields for structured logging.
    """
    if os.getenv("LOG_DB_WRITE", "true").lower() not in ("1", "true", "yes"):
        return

    from app.db.session import async_session

    rec = {
        "ts": dt.datetime.utcnow(),
        "run_id": run_id_var.get() or run_id,
        "request_id": request_id_var.get() or request_id,
        "step": step,
        "status": status,
        "external_system": external_system or "INTERNAL",
        "elapsed_ms": elapsed_ms,
        "retry_count": retry_count,
        "payload_hash": payload_hash,
        "details": details or {},
    }

    async with async_session() as sess:
        await sess.execute(insert(IntegrationLog).values(**rec))
        await sess.commit()
