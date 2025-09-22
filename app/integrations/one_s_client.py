from typing import List, Dict, Any

from .base_client import BaseApiClient
from app.core.config import settings


class OneSApiClient(BaseApiClient):
    def __init__(self):
        # Базовый URL теперь ведет к нашему кастомному сервису
        base_url = f"{settings.API_1C_URL.rstrip('/')}/hs/integrationapi/"
        super().__init__(base_url=base_url)
        self.client.auth = (settings.API_1C_USER, settings.API_1C_PASSWORD)

    async def get_deficit_products(self, warehouse_id: str) -> List[Dict[str, Any]]:
        """
        Получает список дефицитных товаров через кастомный эндпоинт.
        """
        url = f"deficit/{warehouse_id}"
        # Pydantic-валидация здесь не нужна, так как мы доверяем нашему же API,
        # который возвращает простые dict.
        return await self._request("GET", url)

    async def get_stock_for_product(self, product_id: str, warehouse_id: str) -> float:
        """
        Получает остаток товара через кастомный эндпоинт.
        """
        url = f"stock/{warehouse_id}/{product_id}"
        response = await self._request("GET", url)
        return response.get('stock', 0.0)

    async def create_transfer_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает "Заказ на перемещение" через кастомный эндпоинт.
        """
        url = "orders/transfer"
        return await self._request("POST", url, json=payload)

    async def get_moysklad_id_for_product(self, product_id_1c: str) -> str | None:
        """
        ЗАГЛУШКА: Получает ID номенклатуры в МойСклад по ID из 1С.
        """
        return product_id_1c
