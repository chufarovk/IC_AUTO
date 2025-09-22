import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.outbox import OutboxEvent
from app.models.transfer import PendingTransfer
from app.integrations.one_s_client import OneSApiClient
from app.integrations.moysklad_client import MoySkladApiClient
from app.schemas.one_s import TransferOrderPayload, TransferOrderResponse
from app.schemas.moy_sklad import CustomerOrderPayload
from .logger_service import LoggerService


class OutboxProcessorService:
    PROCESS_NAME = "OutboxProcessor"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = LoggerService(session, self.PROCESS_NAME)

    async def process_pending_events(self):
        """Обрабатывает все ожидающие события из таблицы outbox."""
        await self.logger.info("Запуск обработки очереди исходящих событий.")

        # Выбираем все события в статусе PENDING
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == 'PENDING')
            .order_by(OutboxEvent.created_at)
        )
        result = await self.session.execute(stmt)
        events_to_process = result.scalars().all()

        if not events_to_process:
            await self.logger.info("Нет новых событий для обработки.")
            return

        await self.logger.info(f"Найдено {len(events_to_process)} событий для обработки.")

        one_s_client = OneSApiClient()
        ms_client = MoySkladApiClient()
        for event in events_to_process:
            try:
                # Роутинг по типам событий
                if event.event_type == "CREATE_1C_TRANSFER":
                    await self.handle_create_1c_transfer(event, one_s_client)
                elif event.event_type == "CREATE_MS_CUSTOMER_ORDER":
                    await self.handle_create_ms_customer_order(event, ms_client)
                else:
                    await self.logger.warning(
                        f"Неизвестный тип события: {event.event_type}",
                        payload={"event_id": str(event.id)},
                    )
                    await self.mark_event_as_failed(event.id)

            except Exception as e:
                # В случае ошибки, помечаем событие как FAILED и логируем
                await self.mark_event_as_failed(event.id)
                await self.logger.error(
                    f"Ошибка при обработке события {event.id}: {e}",
                    payload={"event_id": str(event.id)},
                )

        await one_s_client.close()
        await ms_client.close()
        await self.logger.info("Обработка очереди завершена.")

    async def handle_create_1c_transfer(self, event: OutboxEvent, client: OneSApiClient):
        """Обработчик для события создания заказа на перемещение в 1С."""
        payload = TransferOrderPayload.model_validate(event.payload)

        # Выполняем запрос к API 1С
        response_dict = await client.create_transfer_order(payload.model_dump())
        response = TransferOrderResponse.model_validate(response_dict)

        # Атомарно обновляем статусы в БД
        async with self.session.begin():
            # Обновляем статус самого события на PROCESSED
            event_update_stmt = (
                update(OutboxEvent)
                .where(OutboxEvent.id == event.id)
                .values(status='PROCESSED')
            )
            await self.session.execute(event_update_stmt)

            # Обновляем статус связанного перемещения и сохраняем ID из 1С
            transfer_update_stmt = (
                update(PendingTransfer)
                .where(PendingTransfer.id == uuid.UUID(event.related_entity_id))
                .values(status='CREATED_IN_1C', transfer_order_id_1c=response.id)
            )
            await self.session.execute(transfer_update_stmt)

        await self.logger.info(
            f"Событие {event.id} успешно обработано. Создан заказ в 1С с ID: {response.id}",
            payload={"event_id": str(event.id), "transfer_order_id": response.id},
        )

    async def mark_event_as_failed(self, event_id: uuid.UUID):
        """Помечает событие как невыполненное."""
        async with self.session.begin():
            stmt = update(OutboxEvent).where(OutboxEvent.id == event_id).values(status='FAILED')
            await self.session.execute(stmt)

    async def handle_create_ms_customer_order(self, event: OutboxEvent, client: MoySkladApiClient):
        """Обработчик для события создания заказа покупателя в МойСклад."""
        payload = CustomerOrderPayload.model_validate(event.payload)

        # Выполняем запрос к API МойСклад
        response = await client.create_customer_order(payload)

        # Атомарно обновляем статус события
        async with self.session.begin():
            event_update_stmt = (
                update(OutboxEvent).where(OutboxEvent.id == event.id).values(status='PROCESSED')
            )
            await self.session.execute(event_update_stmt)
            # В будущем: обновление статуса в pending_supplier_orders

        await self.logger.info(
            f"Событие {event.id} успешно обработано. Создан 'Заказ покупателя' в МойСклад с ID: {response.id}",
            payload={"event_id": str(event.id), "customer_order_id": response.id},
        )
