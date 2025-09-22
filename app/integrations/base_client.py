import asyncio
import hashlib
import httpx
import logging
import os
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.core.logging import _redact


def is_retryable_exception(exception: BaseException) -> bool:
    """Определяет, является ли исключение основанием для повторной попытки."""
    if isinstance(exception, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout)):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        # Повторяем только при серверных ошибках (5xx)
        return 500 <= exception.response.status_code < 600
    return False


LOG_SAMPLE_RATE = float(os.getenv("LOG_SAMPLE_RATE", "1.0"))
LOG_BODY_MAX = int(os.getenv("LOG_BODY_MAX", "2000"))

class BaseApiClient:
    def __init__(self, base_url: str):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self._logger = logging.getLogger("http")

    def _maybe_hash(self, body: str) -> str:
        return hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest()[:16]

    async def _request_with_retry(self, method: str, url: str, tries: int = 5, **kwargs):
        """Internal method with retry logic and detailed logging."""
        t0 = time.perf_counter()
        last_exc = None

        for attempt in range(1, tries + 1):
            try:
                # Log request details
                req_body = kwargs.get("content") or kwargs.get("data") or (kwargs.get("json") and str(kwargs["json"])) or ""
                headers = _redact(dict(kwargs.get("headers") or {}))

                self._logger.debug("HTTP %s %s (attempt %d)", method, url, attempt,
                                 extra={"extra": {"method": method, "url": url, "attempt": attempt,
                                                "headers": headers, "body_preview": str(req_body)[:LOG_BODY_MAX]}})

                response: httpx.Response = await self.client.request(method, url, **kwargs)
                dt = round((time.perf_counter() - t0) * 1000)

                # Log response details
                body_text = response.text or ""
                body_hash = self._maybe_hash(body_text)

                if LOG_SAMPLE_RATE >= 1.0:
                    body_preview = body_text[:LOG_BODY_MAX]
                else:
                    body_preview = f"[sampled hash:{body_hash}]"

                self._logger.info("HTTP %s %s -> %d in %dms", method, url, response.status_code, dt,
                                extra={"extra": {"method": method, "url": url, "status_code": response.status_code,
                                               "elapsed_ms": dt, "response_preview": body_preview,
                                               "response_hash": body_hash}})

                response.raise_for_status()
                return self._parse_response(response)

            except httpx.HTTPError as e:
                last_exc = e
                if attempt >= tries or not is_retryable_exception(e):
                    dt = round((time.perf_counter() - t0) * 1000)
                    self._logger.error("HTTP FAIL %s %s after %d tries: %s", method, url, attempt, repr(e),
                                     extra={"extra": {"method": method, "url": url, "elapsed_ms": dt,
                                                    "attempts": attempt}}, exc_info=True)
                    raise

                # Wait before retry
                wait_time = min(2 ** (attempt - 1), 60)
                self._logger.debug("HTTP retry %s %s in %ds", method, url, wait_time)
                await asyncio.sleep(wait_time)

        # Should not reach here, but just in case
        raise last_exc

    def _parse_response(self, response: httpx.Response):
        """Parse HTTP response with safe JSON handling."""
        # Пустой ответ (например, 204 No Content)
        if response.status_code == 204 or not response.content:
            return {}

        # Пытаемся распарсить JSON только если content-type указывает на JSON
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type or content_type.startswith("application/"):
            try:
                return response.json()
            except Exception:
                # Некорректный JSON — возвращаем пустой словарь, чтобы не падать в вызывающем коде
                return {}

        # Нежданный тип содержимого — возвращаем пустой словарь для безопасности
        return {}

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(is_retryable_exception),
    )
    async def _request(self, method: str, url: str, **kwargs):
        """Legacy method for backward compatibility - delegates to new logging method."""
        tries = kwargs.pop("tries", 5)
        return await self._request_with_retry(method, url, tries=tries, **kwargs)

    async def close(self):
        await self.client.aclose()
