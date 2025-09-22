import uuid
from sqlalchemy import String, DECIMAL
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base, TimestampMixin


class PendingTransfer(Base, TimestampMixin):
    __tablename__ = "pending_transfers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id_1c: Mapped[str] = mapped_column(String, index=True, comment="UUID товара в 1С")
    product_name: Mapped[str] = mapped_column(String)
    quantity_requested: Mapped[float] = mapped_column(DECIMAL)
    source_warehouse_id_1c: Mapped[str] = mapped_column(String, comment="UUID склада-донора в 1С")
    source_warehouse_name: Mapped[str] = mapped_column(String)
    transfer_order_id_1c: Mapped[str | None] = mapped_column(String, nullable=True, comment="ID созданного документа в 1С")
    status: Mapped[str] = mapped_column(String(50), default='INITIATED', index=True, comment="INITIATED, CREATED_IN_1C, COMPLETED, ERROR")

