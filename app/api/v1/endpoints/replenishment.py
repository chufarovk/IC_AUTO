from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.services.replenishment_service import ReplenishmentService


router = APIRouter()


@router.post(
    "/trigger/internal-replenishment",
    status_code=202,  # Accepted
    summary="Запустить процесс внутреннего пополнения",
)
async def trigger_internal_replenishment(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Асинхронно запускает процесс внутреннего пополнения запасов.

    Система немедленно вернет ответ `202 Accepted`, а сам процесс будет выполняться в фоне.
    Результаты выполнения будут записаны в журнал операций.
    """
    service = ReplenishmentService(session=db)
    background_tasks.add_task(service.run_internal_replenishment)

    return {"message": "Процесс внутреннего пополнения запущен в фоновом режиме."}

