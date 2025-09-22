import asyncio
import functools
import inspect
import logging
import time
from typing import Any, Callable, Dict

from .logging import _redact

logger = logging.getLogger("steps")

def log_step(step: str):
    """
    Логирует вход, выход, тайминги и исключения шага.
    Пример: @log_step("replenishment.fetch_deficit")
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def awrapped(*args, **kwargs):
            t0 = time.perf_counter()
            logger.debug("ENTER %s", step, extra={"extra": {"step": step, "args": _redact(kwargs)}})
            try:
                result = await fn(*args, **kwargs)
                dt = round((time.perf_counter() - t0) * 1000)
                logger.info("EXIT %s", step, extra={"extra": {"step": step, "elapsed_ms": dt, "result_preview": str(result)[:200]}})
                return result
            except Exception as e:
                dt = round((time.perf_counter() - t0) * 1000)
                logger.error("ERROR %s: %s", step, e, extra={"extra": {"step": step, "elapsed_ms": dt}}, exc_info=True)
                raise

        def wrapped(*args, **kwargs):
            t0 = time.perf_counter()
            logger.debug("ENTER %s", step, extra={"extra": {"step": step, "args": _redact(kwargs)}})
            try:
                result = fn(*args, **kwargs)
                dt = round((time.perf_counter() - t0) * 1000)
                logger.info("EXIT %s", step, extra={"extra": {"step": step, "elapsed_ms": dt, "result_preview": str(result)[:200]}})
                return result
            except Exception as e:
                dt = round((time.perf_counter() - t0) * 1000)
                logger.error("ERROR %s: %s", step, e, extra={"extra": {"step": step, "elapsed_ms": dt}}, exc_info=True)
                raise

        # Выбрать обертку по типу функции (async или sync)
        if inspect.iscoroutinefunction(fn):
            return awrapped
        else:
            return wrapped

    return decorator