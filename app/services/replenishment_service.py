import httpx
import logging
import os
import uuid
from tenacity import RetryError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.one_s_client import OneSApiClient
from app.integrations.moysklad_client import MoySkladApiClient
from app.integrations.onec_json_normalizer import IntegrationError
from .logger_service import LoggerService, log_event
from app.models.transfer import PendingTransfer
from app.models.outbox import OutboxEvent
from app.core.config import settings
from app.core.logging import set_run_id
from app.core.observability import log_step


logger = logging.getLogger(__name__)

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

    @log_step("replenishment.run")
    async def run_internal_replenishment(self, warehouse_id: str = None):
        run_id = set_run_id(str(uuid.uuid4()))
        warehouse_id = warehouse_id or self.YURLOVSKIY_WAREHOUSE_ID
        logger.info("START replenishment", extra={"extra": {"warehouse_id": warehouse_id}})

        try:
            # 1) Получаем дефицит
            items = await self._fetch_and_filter_deficit(warehouse_id)
            if not items:
                logger.info("No items to process", extra={"extra": {"warehouse_id": warehouse_id}})
                await log_event(step="replenishment", status="END", details={"reason": "no_deficit", "warehouse_id": warehouse_id})
                return {"status": "success", "message": "No deficit found."}

            # 2) Ищем доноров и формируем outbox/events
            await self._plan_transfers_or_orders(warehouse_id, items)
            logger.info("END replenishment", extra={"extra": {"warehouse_id": warehouse_id}})
            await log_event(step="replenishment", status="END", details={"warehouse_id": warehouse_id, "processed_items": len(items)})
            return {"status": "success", "message": "Replenishment process finished."}

        except Exception as e:
            logger.error("Replenishment failed", extra={"extra": {"error": str(e), "warehouse_id": warehouse_id}}, exc_info=True)
            await log_event(step="replenishment", status="ERROR", details={"error": str(e), "warehouse_id": warehouse_id})
            return {"status": "error", "message": str(e)}
        finally:
            await self.one_s_client.close()
            await self.ms_client.close()

    @log_step("replenishment.fetch_deficit")
    async def _fetch_and_filter_deficit(self, warehouse_id: str):
        try:
            raw_items = await self.one_s_client.get_deficit_products(warehouse_id)
        except IntegrationError as e:
            logger.error("1C API error", extra={"extra": {"error": str(e)}})
            await log_event(step="replenishment.fetch_deficit", status="ERROR",
                           external_system="ONEC", details={"error": str(e)})
            raise

        total = len(raw_items)
        logger.info("Fetched items", extra={"extra": {"total": total, "sample": (raw_items[0] if total else None)}})

        # Поддерживаем явно пустой массив (дефицита нет) - это не ошибка
        if total == 0:
            logger.info("No deficit found - empty result", extra={"extra": {"warehouse_id": warehouse_id}})
            await log_event(step="replenishment.fetch_deficit", status="INFO",
                           external_system="ONEC", details={"message": "No deficit items", "warehouse_id": warehouse_id})
            return []

        kept, dropped_no_id, dropped_no_deficit, dropped_invalid = [], 0, 0, 0
        for it in raw_items:
            # Валидация обязательных полей согласно Task006.md: id, name, min_stock, current_stock
            validation_errors = []

            if not it.get("id"):
                validation_errors.append("missing id")
            if not it.get("name"):
                validation_errors.append("missing name")
            if "min_stock" not in it:
                validation_errors.append("missing min_stock")
            if "current_stock" not in it:
                validation_errors.append("missing current_stock")

            if validation_errors:
                dropped_invalid += 1
                logger.debug("drop:validation_failed", extra={"extra": {"item": it, "errors": validation_errors}})
                continue

            iid = it.get("id")
            deficit = float(it.get("deficit") or 0)

            if deficit <= 0:
                dropped_no_deficit += 1
                logger.debug("drop:no_deficit", extra={"extra": {"item": it}})
                continue

            kept.append(it)

        logger.info("Filter summary", extra={"extra": {
            "total": total, "kept": len(kept), "dropped_no_id": dropped_no_id,
            "dropped_no_deficit": dropped_no_deficit, "dropped_invalid": dropped_invalid}})
        await log_event(step="replenishment.filter", status="INFO",
                       details={"total": total, "kept": len(kept), "dropped_no_id": dropped_no_id,
                               "dropped_no_deficit": dropped_no_deficit, "dropped_invalid": dropped_invalid})
        return kept

    @log_step("replenishment.plan")
    async def _plan_transfers_or_orders(self, warehouse_id: str, items: list[dict]):
        for it in items:
            pid, need = it["id"], float(it["deficit"])
            logger.debug("plan:item", extra={"extra": {"product_id": pid, "need": need}})

            # 2.1 Проверка внутренних складов-доноров
            donors = await self._check_internal_donors(pid, need)
            if donors:
                logger.info("plan:internal_transfer", extra={"extra": {"product_id": pid, "donors": donors}})
                await self._enqueue_transfer_order(warehouse_id, pid, donors, need)
                continue

            # 2.2 Если нет — внешний заказ МойСклад
            logger.info("plan:external_order", extra={"extra": {"product_id": pid, "quantity": need}})
            await self._enqueue_moysklad_order(pid, need)

    @log_step("replenishment.check_donors")
    async def _check_internal_donors(self, product_id: str, needed_qty: float):
        # Проверка internal stockov
        for warehouse_name, warehouse_id in self.DONOR_WAREHOUSES.items():
            try:
                available_stock = await self.one_s_client.get_stock_for_product(product_id, warehouse_id)
                if available_stock >= needed_qty:
                    await log_event(step="replenishment.donor_found", status="INFO", external_system="ONEC",
                                   details={"product_id": product_id, "warehouse": warehouse_name, "available": available_stock})
                    return [(warehouse_name, warehouse_id)]
            except IntegrationError as e:
                logger.error("Failed to check stock in donor warehouse",
                           extra={"extra": {"product_id": product_id, "warehouse": warehouse_name, "error": str(e)}})
                await log_event(step="replenishment.donor_check_failed", status="ERROR", external_system="ONEC",
                               details={"product_id": product_id, "warehouse": warehouse_name, "error": str(e)})
                # Продолжаем проверку следующих складов
                continue
        return []

    @log_step("replenishment.enqueue_transfer")
    async def _enqueue_transfer_order(self, target_warehouse_id: str, product_id: str, donors: list, quantity: float):
        # Existing create_transfer_and_outbox_event logic but with enhanced logging
        warehouse_name, warehouse_id = donors[0]
        await log_event(step="replenishment.transfer_queued", status="INFO", external_system="ONEC",
                       details={"product_id": product_id, "source_warehouse": warehouse_name, "quantity": quantity})

        # Call existing method
        product = {"id": product_id, "name": f"Product-{product_id}"}  # Simplified for this step
        await self.create_transfer_and_outbox_event(
            product=product, quantity=quantity,
            source_warehouse_id=warehouse_id, source_warehouse_name=warehouse_name
        )

    @log_step("replenishment.enqueue_moysklad_order")
    async def _enqueue_moysklad_order(self, product_id: str, quantity: float):
        await log_event(step="replenishment.external_order_queued", status="INFO", external_system="MOYSKLAD",
                       details={"product_id": product_id, "quantity": quantity})

        # Call existing method
        product = {"id": product_id, "name": f"Product-{product_id}"}  # Simplified for this step
        await self.initiate_external_order(product=product, quantity_to_order=quantity)

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
