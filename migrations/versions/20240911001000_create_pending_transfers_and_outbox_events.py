"""Create pending_transfers and outbox_events tables

Revision ID: 20240911001000
Revises: 20240911000000
Create Date: 2025-09-11 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20240911001000'
down_revision = '20240911000000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'pending_transfers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('product_id_1c', sa.String(), nullable=False, comment='UUID товара в 1С'),
        sa.Column('product_name', sa.String(), nullable=False),
        sa.Column('quantity_requested', sa.DECIMAL(), nullable=False),
        sa.Column('source_warehouse_id_1c', sa.String(), nullable=False, comment='UUID склада-донора в 1С'),
        sa.Column('source_warehouse_name', sa.String(), nullable=False),
        sa.Column('transfer_order_id_1c', sa.String(), nullable=True, comment='ID созданного документа в 1С'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default=sa.text("'INITIATED'")),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('INITIATED','CREATED_IN_1C','COMPLETED','ERROR')", name='ck_pending_transfers_status'),
    )
    op.create_index('ix_pending_transfers_product_id_1c', 'pending_transfers', ['product_id_1c'])
    op.create_index('ix_pending_transfers_status', 'pending_transfers', ['status'])

    op.create_table(
        'outbox_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column('related_entity_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('PENDING','PROCESSED','FAILED')", name='ck_outbox_events_status'),
    )
    op.create_index('ix_outbox_events_event_type', 'outbox_events', ['event_type'])
    op.create_index('ix_outbox_events_status', 'outbox_events', ['status'])


def downgrade() -> None:
    op.drop_index('ix_outbox_events_status', table_name='outbox_events')
    op.drop_index('ix_outbox_events_event_type', table_name='outbox_events')
    op.drop_table('outbox_events')

    op.drop_index('ix_pending_transfers_status', table_name='pending_transfers')
    op.drop_index('ix_pending_transfers_product_id_1c', table_name='pending_transfers')
    op.drop_table('pending_transfers')
