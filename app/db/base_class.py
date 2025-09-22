from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import func
from datetime import datetime


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""


class TimestampMixin:
    """Миксин для добавления полей created_at и updated_at."""
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

