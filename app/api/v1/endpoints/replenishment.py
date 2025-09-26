from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.db.session import get_db_session
from app.services.replenishment_service import ReplenishmentService
from app.core.logging import set_request_id


router = APIRouter()


@router.post(
    "/trigger/internal-replenishment",
    status_code=202,  # Accepted
    summary="Запустить процесс внутреннего пополнения",
)
async def trigger_internal_replenishment(
    background_tasks: BackgroundTasks,
    warehouse_id: str = Query(default=None, description="UUID склада (опционально)"),
    bypass_filter: bool = Query(default=False, description="Обойти фильтр дефицита"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Асинхронно запускает процесс внутреннего пополнения запасов.

    Система немедленно вернет ответ `202 Accepted`, а сам процесс будет выполняться в фоне.
    Результаты выполнения будут записаны в журнал операций.

    Args:
        warehouse_id: UUID склада (по умолчанию Юрловский)
        bypass_filter: Если True, пропускает фильтр дефицита для диагностики
    """
    # Set request correlation ID
    request_id = set_request_id(str(uuid4()))

    service = ReplenishmentService(session=db)
    background_tasks.add_task(service.run_internal_replenishment, warehouse_id, bypass_filter)

    return {
        "message": "Процесс внутреннего пополнения запущен в фоновом режиме.",
        "request_id": request_id,
        "parameters": {
            "warehouse_id": warehouse_id,
            "bypass_filter": bypass_filter
        }
    }

