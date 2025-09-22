from pydantic import BaseModel


class DeficitProduct(BaseModel):
    # Модель товара из кастомного IntegrationAPI 1С
    id: str
    name: str
    min_stock: float
    max_stock: float
    current_stock: float


class TransferOrderProduct(BaseModel):
    productID: str
    quantity: float


class TransferOrderPayload(BaseModel):
    """
    Тело запроса для создания "Заказа на перемещение" в кастомном IntegrationAPI 1С.
    Ожидаемая структура:
    {
      "fromWarehouseID": "uuid",
      "toWarehouseID": "uuid",
      "products": [{"productID": "uuid", "quantity": 10.0}]
    }
    """
    fromWarehouseID: str
    toWarehouseID: str
    products: list[TransferOrderProduct]


class TransferOrderResponse(BaseModel):
    """Ответ при создании заказа на перемещение из IntegrationAPI 1С."""
    id: str
    number: str
