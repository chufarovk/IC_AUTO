from .base_client import BaseApiClient
from app.core.config import settings
from app.schemas.moy_sklad import CustomerOrderPayload, CustomerOrderResponse


class MoySkladApiClient(BaseApiClient):
    BASE_API_URL = "https://api.moysklad.ru/api/remap/1.2/"

    def __init__(self):
        super().__init__(base_url=self.BASE_API_URL)
        # Устанавливаем заголовок авторизации для всех запросов
        self.client.headers["Authorization"] = f"Bearer {settings.MOYSKLAD_API_TOKEN}"
        self.client.headers["Accept-Encoding"] = "gzip"

    async def get_stock_by_product_id(self, product_id_ms: str) -> float:
        """
        Получает остаток товара на всех складах.
        ПРИМЕЧАНИЕ: Это упрощенная версия. В реальности может потребоваться
        более сложный запрос для фильтрации по конкретному складу.
        """
        url = "report/stock/all"
        params = {
            "filter": f"product=https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id_ms}",
        }

        try:
            response = await self._request("GET", url, params=params)
            rows = response.get("rows", [])
            # Суммируем остатки по всем складам
            total_stock = sum(row.get("stock", 0) for row in rows)
            return total_stock
        except Exception:
            # В случае ошибки или отсутствия товара, возвращаем 0
            return 0.0

    async def create_customer_order(
        self, payload: CustomerOrderPayload
    ) -> CustomerOrderResponse:
        """
        Создает документ "Заказ покупателя" в МойСклад.
        """
        url = "entity/customerorder"
        response_data = await self._request(
            "POST", url, json=payload.model_dump()
        )
        return CustomerOrderResponse.model_validate(response_data)

