from pydantic import BaseModel


# --- Вспомогательные модели для метаданных ---
class Meta(BaseModel):
    href: str
    type: str


# --- Модели для создания "Заказа покупателя" ---
class Agent(BaseModel):
    meta: Meta


class Organization(BaseModel):
    meta: Meta


class ProductPosition(BaseModel):
    quantity: float
    price: float = 0  # Цена может быть 0, если это внутренний заказ
    assortment: dict  # {"meta": {"href": "url_товара", "type": "product"}}


class CustomerOrderPayload(BaseModel):
    """Тело запроса для создания "Заказа покупателя" в МойСклад."""

    agent: Agent
    organization: Organization
    positions: list[ProductPosition]


class CustomerOrderResponse(BaseModel):
    """Ответ от МойСклад после создания "Заказа покупателя"."""

    id: str
    name: str

