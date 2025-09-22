from sqlalchemy import Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base, TimestampMixin


class IntegrationLog(Base, TimestampMixin):
    __tablename__ = "integration_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    process_name: Mapped[str] = mapped_column(String(100), index=True)
    log_level: Mapped[str] = mapped_column(String(20), index=True)  # INFO, ERROR, WARN
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

