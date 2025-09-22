import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception


def is_retryable_exception(exception: BaseException) -> bool:
    """Определяет, является ли исключение основанием для повторной попытки."""
    if isinstance(exception, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout)):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        # Повторяем только при серверных ошибках (5xx)
        return 500 <= exception.response.status_code < 600
    return False


class BaseApiClient:
    def __init__(self, base_url: str):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(is_retryable_exception),
    )
    async def _request(self, method: str, url: str, **kwargs):
        response = await self.client.request(method, url, **kwargs)
        response.raise_for_status()  # Вызовет исключение для статусов 4xx/5xx

        # Пустой ответ (например, 204 No Content)
        if response.status_code == 204 or not response.content:
            return {}

        # Пытаемся распарсить JSON только если content-type указывает на JSON
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type or content_type.startswith("application/" ):
            try:
                return response.json()
            except Exception:
                # Некорректный JSON — возвращаем пустой словарь, чтобы не падать в вызывающем коде
                return {}

        # Нежданный тип содержимого — возвращаем пустой словарь для безопасности
        return {}

    async def close(self):
        await self.client.aclose()
