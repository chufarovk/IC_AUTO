from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Создаем асинхронный "движок" для взаимодействия с БД
async_engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,  # Проверяет соединение перед использованием
    echo=False,  # Установите в True для отладки SQL-запросов
)

# Создаем фабрику асинхронных сессий
AsyncSessionFactory = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Важно для FastAPI
)


async def get_db_session() -> AsyncSession:
    """
    FastAPI зависимость для получения сессии базы данных.
    """
    async with AsyncSessionFactory() as session:
        yield session

