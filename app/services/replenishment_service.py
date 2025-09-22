import httpx
import os
from tenacity import RetryError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.integrations.one_s_client import OneSApiClient
from app.integrations.moysklad_client import MoySkladApiClient
from .logger_service import LoggerService
from app.models.transfer import PendingTransfer
from app.models.outbox import OutboxEvent
from app.core.config import settings


class ReplenishmentService:
    PROCESS_NAME = "InternalReplenishment"

    # UUID склада "Юрловский" - это заглушка, нужно будет взять из .env
    YURLOVSKIY_WAREHOUSE_ID = "c7e8e58f-49b7-11e6-8a7c-0025903e6d16"

    # UUID складов-доноров - это заглушки
    DONOR_WAREHOUSES = {
        "Бестужевых": "a4d3a777-49b7-11e6-8a7c-0025903e6d16",
        "СВАО Контейнер": "b8c4c555-49b7-11e6-8a7c-0025903e6d16",
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = LoggerService(session, self.PROCESS_NAME)
        self.one_s_client = OneSApiClient()
        self.ms_client = MoySkladApiClient()

    async def check_is_pending(self, product_id: str) -> bool:
        """Проверяет, есть ли для товара активное, незавершенное перемещение."""
        stmt = select(PendingTransfer).where(
            PendingTransfer.product_id_1c == product_id,
            PendingTransfer.status.in_(["INITIATED", "CREATED_IN_1C"]),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def run_internal_replenishment(self):
        await self.logger.info("Запуск процесса внутреннего пополнения.")

        try:
            deficit_products = await self.one_s_client.get_deficit_products(
                self.YURLOVSKIY_WAREHOUSE_ID
            )

            # Debug logging if feature flag is enabled
            enable_debug = os.getenv("ONEC_LOSSY_NORMALIZE", "true").lower() in ("1", "true", "yes")
            if enable_debug and deficit_products:
                await self.logger.debug(
                    "1C response normalized successfully for deficit products",
                    payload={"first_product_sample": deficit_products[0]}
                )

            if not deficit_products:
                await self.logger.info(
                    "Дефицит товаров не обнаружен. Процесс завершен."
                )
                return {"status": "success", "message": "No deficit found."}

            await self.logger.info(
                f"Обнаружено {len(deficit_products)} дефицитных позиций."
            )

            for product in deficit_products:
                # Проверить наличие ожидающих перемещений
                is_pending = await self.check_is_pending(product["id"])
                if is_pending:
                    await self.logger.info(
                        f"Пропуск товара '{product['name']}', перемещение уже в процессе."
                    )
                    continue

                quantity_to_order = product["max_stock"] - product["current_stock"]

                source_found = False
                for warehouse_name, warehouse_id in self.DONOR_WAREHOUSES.items():
                    available_stock = await self.one_s_client.get_stock_for_product(
                        product["id"], warehouse_id
                    )

                    if available_stock >= quantity_to_order:
                        # Атомарно создать запись о перемещении и событие в outbox
                        await self.create_transfer_and_outbox_event(
                            product=product,
                            quantity=quantity_to_order,
                            source_warehouse_id=warehouse_id,
                            source_warehouse_name=warehouse_name,
                        )
                        await self.logger.info(
                            f"Товар '{product['name']}' найден на складе '{warehouse_name}'. Заявка на перемещение инициирована."
                        )
                        source_found = True
                        break

                if not source_found:
                    await self.logger.warning(
                        f"Недостаточно товара '{product['name']}' на всех складах-источниках.",
                        payload={"product_id": product["id"]},
                    )
                    # Инициируем внешний заказ через МойСклад
                    await self.initiate_external_order(
                        product=product,
                        quantity_to_order=quantity_to_order,
                    )

            await self.logger.info("Процесс внутреннего пополнения завершен.")
            return {"status": "success", "message": "Replenishment process finished."}

        except RetryError as e:
            # Распаковываем исходную ошибку из Tenacity
            last_attempt = getattr(e, "last_attempt", None)
            original_exception = None
            if last_attempt is not None:
                try:
                    # В tenacity у last_attempt есть .exception() для извлечения ошибки
                    if hasattr(last_attempt, "exception"):
                        original_exception = last_attempt.exception()
                    # Fallback на .result() если почему-то exception отсутствует
                    elif hasattr(last_attempt, "result"):
                        original_exception = last_attempt.result()
                except Exception:
                    original_exception = None

            error_payload = {
                "error": str(e),
                "original_exception_type": type(original_exception).__name__ if original_exception else None,
                "original_exception": str(original_exception) if original_exception else None,
            }

            # Если исходная ошибка была HTTPStatusError — логируем максимум деталей
            if isinstance(original_exception, httpx.HTTPStatusError):
                error_payload.update({
                    "request_url": str(original_exception.request.url) if original_exception.request else None,
                    "response_status_code": original_exception.response.status_code if original_exception.response else None,
                    "response_text": original_exception.response.text if original_exception.response else None,
                })
                error_message = (
                    f"Ошибка API 1С: Статус {error_payload['response_status_code']} после нескольких попыток."
                )
            else:
                error_message = (
                    f"Критическая ошибка после нескольких попыток: {error_payload['original_exception_type']}"
                )

            await self.logger.error(error_message, payload=error_payload)
            return {"status": "error", "message": error_message}

        except httpx.HTTPStatusError as e:
            # Логируем подробности HTTP-ошибки от 1С/внешнего API
            error_details = {
                "error": str(e),
                "request_url": str(e.request.url) if e.request else None,
                "response_status_code": e.response.status_code if e.response else None,
                "response_text": e.response.text if e.response else None,
            }
            await self.logger.error(
                f"Ошибка API 1С: Статус {error_details['response_status_code']}",
                payload=error_details,
            )
            return {"status": "error", "message": f"API Error: {error_details['response_status_code']}"}

        except Exception as e:
            await self.logger.error(
                f"Критическая ошибка в процессе пополнения: {e}",
                payload={"error": str(e)},
            )
            return {"status": "error", "message": str(e)}
        finally:
            await self.one_s_client.close()
            await self.ms_client.close()

    async def create_transfer_and_outbox_event(
        self, product, quantity, source_warehouse_id, source_warehouse_name
    ):
        """
        В одной транзакции создает запись в pending_transfers и событие в outbox_events.
        """
        async with self.session.begin():  # Начинаем транзакцию
            # 1. Создаем запись о будущем перемещении
            new_transfer = PendingTransfer(
                product_id_1c=product["id"],
                product_name=product["name"],
                quantity_requested=quantity,
                source_warehouse_id_1c=source_warehouse_id,
                source_warehouse_name=source_warehouse_name,
                status="INITIATED",
            )
            self.session.add(new_transfer)
            await self.session.flush()  # Получаем ID для new_transfer

            # 2. Создаем событие для отправки в 1С
            outbox_payload = {
                "fromWarehouseID": source_warehouse_id,
                "toWarehouseID": self.YURLOVSKIY_WAREHOUSE_ID,
                "products": [
                    {"productID": product["id"], "quantity": float(quantity)}
                ],
            }

            new_event = OutboxEvent(
                event_type="CREATE_1C_TRANSFER",
                payload=outbox_payload,
                related_entity_id=str(new_transfer.id),
            )
            self.session.add(new_event)
        # Транзакция коммитится автоматически при выходе из `async with`

    async def initiate_external_order(self, product, quantity_to_order):
        """
        Инициирует процесс внешнего заказа через МойСклад.
        Создает событие в outbox для последующей обработки.
        """
        # Шаг 1: Получаем ID товара в МойСклад
        product_id_ms = await self.one_s_client.get_moysklad_id_for_product(product["id"])
        if not product_id_ms:
            await self.logger.error(
                f"Для товара '{product['name']}' (1C ID: {product['id']}) не найден ID в МойСклад. Внешний заказ невозможен."
            )
            return

        # Шаг 3: Формируем payload для "Заказа покупателя"
        product_meta_href = f"{self.ms_client.BASE_API_URL}entity/product/{product_id_ms}"
        org_meta_href = f"{self.ms_client.BASE_API_URL}entity/organization/{settings.MOYSKLAD_ORG_UUID}"
        agent_meta_href = f"{self.ms_client.BASE_API_URL}entity/counterparty/{settings.MOYSKLAD_AGENT_UUID}"

        outbox_payload = {
            "organization": {"meta": {"href": org_meta_href, "type": "organization"}},
            "agent": {"meta": {"href": agent_meta_href, "type": "counterparty"}},
            "positions": [
                {
                    "quantity": quantity_to_order,
                    "price": 0,
                    "assortment": {"meta": {"href": product_meta_href, "type": "product"}},
                }
            ],
        }

        # Шаг 4: Атомарно создаем событие в outbox
        async with self.session.begin():
            new_event = OutboxEvent(
                event_type="CREATE_MS_CUSTOMER_ORDER",
                payload=outbox_payload,
                related_entity_id=product["id"],  # В будущем заменим на ID из pending_supplier_orders
            )
            self.session.add(new_event)

        await self.logger.info(
            f"Инициирован внешний заказ для товара '{product['name']}'. Событие создано в outbox.",
            payload={"product_1c_id": product["id"], "product_ms_id": product_id_ms},
        )
