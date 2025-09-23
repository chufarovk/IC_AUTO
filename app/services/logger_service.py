import datetime as dt
import json
import os
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert

from app.models.log import IntegrationLog
from app.core.logging import job_id_var, job_name_var, run_id_var, request_id_var


def _as_uuid(value: Any) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _ensure_jsonable(value: Any) -> Any:
    if value is None:
        return None
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except (TypeError, ValueError):
        # Fallback: coerce into JSON-serializable structure via dumps/loads
        try:
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))
        except Exception:
            return {"_repr": str(value)}


class LoggerService:
    def __init__(self, session: AsyncSession, process_name: str):
        self.session = session
        self.process_name = process_name

    async def _log(self, level: str, message: str, payload: dict | None = None):
        log_entry = IntegrationLog(
            process_name=self.process_name,
            log_level=level,
            message=message,
            payload=_ensure_jsonable(payload),
            run_id=_as_uuid(run_id_var.get()),
            request_id=_as_uuid(request_id_var.get()),
            job_id=_as_uuid(job_id_var.get()),
            job_name=job_name_var.get(),
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
                    run_id: str | UUID | None = None, request_id: str | UUID | None = None,
                    job_id: str | UUID | None = None, job_name: str | None = None,
                    payload: dict[str, Any] | None = None):
    """
    Centralized function to log standardized events to integration_logs table.
    Uses new observability fields for structured logging.
    """
    if os.getenv("LOG_DB_WRITE", "true").lower() not in ("1", "true", "yes"):
        return

    from app.db.session import async_session

    context_run_id = run_id_var.get()
    context_request_id = request_id_var.get()
    context_job_id = job_id_var.get()
    context_job_name = job_name_var.get()

    rec = {
        "ts": dt.datetime.utcnow(),
        "run_id": _as_uuid(run_id or context_run_id),
        "request_id": _as_uuid(request_id or context_request_id),
        "job_id": _as_uuid(job_id or context_job_id),
        "job_name": job_name or context_job_name,
        "step": step,
        "status": status,
        "external_system": external_system or "INTERNAL",
        "elapsed_ms": elapsed_ms,
        "retry_count": retry_count,
        "payload_hash": payload_hash,
        "details": _ensure_jsonable(details or {}),
        "payload": _ensure_jsonable(payload),
    }

    async with async_session() as sess:
        await sess.execute(insert(IntegrationLog).values(**rec))
        await sess.commit()
