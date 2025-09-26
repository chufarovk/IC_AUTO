import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Настройки приложения
    PROJECT_NAME: str = "bisnesmedia Integration Hub"
    DEBUG: bool = False

    # Настройки базы данных
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str

    @property
    def database_url(self) -> str:
        """Асинхронный URL для подключения к базе данных."""
        # Используем DATABASE_URL из env если задан, иначе строим из компонентов
        env_db_url = os.getenv("DATABASE_URL")
        if env_db_url:
            return env_db_url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Настройки API
    API_1C_URL: str
    API_1C_USER: str
    API_1C_PASSWORD: str

    # Debug settings
    DEBUG_ONEC_TOKEN: str | None = Field(default=None)  # задаём в .env, чтобы включить debug
    ONEC_BASE_URL: str = Field(..., env="ONEC_BASE_URL")
    LOG_ONEC_RAW: bool = Field(default=False, env="LOG_ONEC_RAW")

    MOYSKLAD_API_TOKEN: str
    MOYSKLAD_ORG_UUID: str
    MOYSKLAD_AGENT_UUID: str
    RUN_MIGRATIONS_ON_STARTUP: bool = True

    # Настройки Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
