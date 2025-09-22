from typing import List, Dict, Any

from .base_client import BaseApiClient
from .onec_json_normalizer import normalize_deficit_payload, normalize_stock
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
        Теперь принимает любые форматы ответов от 1С (JSON, XDTO, text) и нормализует их.
        """
        url = f"deficit/{warehouse_id}"
        response = await self.client.request("GET", url)
        response.raise_for_status()

        # Debug logging if detailed logging is enabled
        # Note: Actual debug logging is handled in the service layer where logger is available

        # Используем нормализатор для обработки разных форматов ответов 1С
        normalized_data = normalize_deficit_payload(response.text)


        return normalized_data

    async def get_stock_for_product(self, product_id: str, warehouse_id: str) -> float:
        """
        Получает остаток товара через кастомный эндпоинт.
        Теперь принимает любые форматы ответов от 1С (JSON, XDTO, text) и нормализует их.
        """
        url = f"stock/{warehouse_id}/{product_id}"
        response = await self.client.request("GET", url)
        response.raise_for_status()

        # Debug logging if detailed logging is enabled
        # Note: Actual debug logging is handled in the service layer where logger is available

        # Используем нормализатор для обработки разных форматов ответов 1С
        return normalize_stock(response.text)

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
