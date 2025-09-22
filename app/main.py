import asyncio
from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import configure_logging
from app.api.v1.endpoints import replenishment
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.background.jobs import process_outbox_events_job, run_internal_replenishment_job

# Initialize logging before anything else
configure_logging()

# Создаем и настраиваем планировщик
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

async def startup_event():
    print("Starting scheduler...")
    scheduler.add_job(
        process_outbox_events_job,
        'interval',
        seconds=30,
        id='process_outbox'
    )
    scheduler.add_job(
        run_internal_replenishment_job,
        CronTrigger(day_of_week='mon-fri', hour=9, minute=0),
        id='run_replenishment'
    )
    scheduler.start()
    print("Scheduler started.")

async def shutdown_event():
    print("Shutting down scheduler...")
    scheduler.shutdown()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    on_startup=[startup_event],
    on_shutdown=[shutdown_event]
)

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "project_name": settings.PROJECT_NAME}

app.include_router(replenishment.router, prefix="/api/v1", tags=["Triggers"]) 
