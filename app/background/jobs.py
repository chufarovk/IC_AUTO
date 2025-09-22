from app.services.outbox_processor_service import OutboxProcessorService
from app.services.replenishment_service import ReplenishmentService
from app.db.session import AsyncSessionFactory


async def process_outbox_events_job():
    """
    Job-функция для APScheduler, которая обрабатывает очередь outbox.
    """
    async with AsyncSessionFactory() as session:
        service = OutboxProcessorService(session=session)
        await service.process_pending_events()

# Здесь в будущем будут другие фоновые задачи, например, опрос статусов 1С

async def run_internal_replenishment_job():
    """
    Job-функция для APScheduler, которая запускает процесс внутреннего пополнения.
    """
    async with AsyncSessionFactory() as session:
        service = ReplenishmentService(session=session)
        await service.run_internal_replenishment()

