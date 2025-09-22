from sqlalchemy.ext.asyncio import AsyncSession
from app.models.log import IntegrationLog
import json


class LoggerService:
    def __init__(self, session: AsyncSession, process_name: str):
        self.session = session
        self.process_name = process_name

    async def _log(self, level: str, message: str, payload: dict | None = None):
        log_entry = IntegrationLog(
            process_name=self.process_name,
            log_level=level,
            message=message,
            payload=payload,
        )
        self.session.add(log_entry)
        await self.session.commit()

    async def info(self, message: str, payload: dict | None = None):
        await self._log("INFO", message, payload)

    async def error(self, message: str, payload: dict | None = None):
        await self._log("ERROR", message, payload)

    async def warning(self, message: str, payload: dict | None = None):
        await self._log("WARNING", message, payload)
