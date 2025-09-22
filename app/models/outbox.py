import uuid
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base, TimestampMixin


class OutboxEvent(Base, TimestampMixin):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(100), index=True, comment="Тип события, например CREATE_1C_TRANSFER")
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), default='PENDING', index=True, comment="PENDING, PROCESSED, FAILED")
    related_entity_id: Mapped[str | None] = mapped_column(String, nullable=True, comment="ID связанной сущности, например, ID из pending_transfers")

