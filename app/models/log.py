from sqlalchemy import Integer, BigInteger, String, Text, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.db.base_class import Base, TimestampMixin


class IntegrationLog(Base, TimestampMixin):
    __tablename__ = "integration_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    ts: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    step: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)  # INFO|WARN|ERROR|SUCCESS|START|END
    external_system: Mapped[str] = mapped_column(String(20), index=True, default="INTERNAL")  # ONEC|MOYSKLAD|INTERNAL
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Legacy fields for backward compatibility
    process_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    log_level: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # INFO, ERROR, WARN
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

