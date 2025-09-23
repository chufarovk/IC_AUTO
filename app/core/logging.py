import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict
# Context vars for request tracing
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
job_name_var: ContextVar[str | None] = ContextVar("job_name", default=None)

REDACT_KEYS = {k.strip().lower() for k in os.getenv("LOG_REDACT_KEYS", "password,authorization,apikey,token").split(",") if k.strip()}
LOG_FORMAT = os.getenv("LOG_FORMAT", "json").lower()
LOG_BODY_MAX = int(os.getenv("LOG_BODY_MAX", "2000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in REDACT_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    if isinstance(value, str) and len(value) > LOG_BODY_MAX:
        return value[:LOG_BODY_MAX] + f"...(+{len(value)-LOG_BODY_MAX} chars)"
    return value

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "ts": round(time.time() * 1000),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": run_id_var.get(),
            "request_id": request_id_var.get(),
            "job_id": job_id_var.get(),
            "job_name": job_name_var.get(),
        }
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            base.update(_redact(extra))
        return json.dumps(base, ensure_ascii=False)

def configure_logging():
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    if LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root.addHandler(handler)

def set_run_id(value: str | None = None) -> str:
    rid = value or str(uuid.uuid4())
    run_id_var.set(rid)
    return rid

def set_request_id(value: str | None) -> str | None:
    request_id_var.set(value)
    return value

def set_job_id(value: str | None) -> str | None:
    job_name_var.set(None)
    if value is None:
        job_id_var.set(None)
        return None
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        job_id_var.set(None)
        job_name_var.set(str(value))
        return value
    job_id_var.set(str(value))
    return job_id_var.get()

def set_job_name(value: str | None) -> str | None:
    job_name_var.set(value)
    return value

