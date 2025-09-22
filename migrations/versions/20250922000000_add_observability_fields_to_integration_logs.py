"""Add observability fields to integration_logs

Revision ID: 20250922000000
Revises: 20240911000000
Create Date: 2025-09-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250922000000'
down_revision = '20240911000000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new observability columns
    op.add_column('integration_logs', sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
    op.add_column('integration_logs', sa.Column('run_id', sa.String(36), nullable=True))
    op.add_column('integration_logs', sa.Column('request_id', sa.String(36), nullable=True))
    op.add_column('integration_logs', sa.Column('step', sa.String(100), nullable=True))
    op.add_column('integration_logs', sa.Column('status', sa.String(20), nullable=True))
    op.add_column('integration_logs', sa.Column('external_system', sa.String(20), nullable=True, default='INTERNAL'))
    op.add_column('integration_logs', sa.Column('elapsed_ms', sa.Integer(), nullable=True))
    op.add_column('integration_logs', sa.Column('retry_count', sa.Integer(), nullable=True))
    op.add_column('integration_logs', sa.Column('payload_hash', sa.String(64), nullable=True))
    op.add_column('integration_logs', sa.Column('details', sa.JSON(), nullable=True))

    # Make legacy columns nullable for backward compatibility
    op.alter_column('integration_logs', 'process_name', nullable=True)
    op.alter_column('integration_logs', 'log_level', nullable=True)
    op.alter_column('integration_logs', 'message', nullable=True)

    # Create indexes for new fields
    op.create_index('ix_integration_logs_ts', 'integration_logs', ['ts'])
    op.create_index('ix_integration_logs_run_id', 'integration_logs', ['run_id'])
    op.create_index('ix_integration_logs_request_id', 'integration_logs', ['request_id'])
    op.create_index('ix_integration_logs_step', 'integration_logs', ['step'])
    op.create_index('ix_integration_logs_status', 'integration_logs', ['status'])
    op.create_index('ix_integration_logs_external_system', 'integration_logs', ['external_system'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_integration_logs_external_system', table_name='integration_logs')
    op.drop_index('ix_integration_logs_status', table_name='integration_logs')
    op.drop_index('ix_integration_logs_step', table_name='integration_logs')
    op.drop_index('ix_integration_logs_request_id', table_name='integration_logs')
    op.drop_index('ix_integration_logs_run_id', table_name='integration_logs')
    op.drop_index('ix_integration_logs_ts', table_name='integration_logs')

    # Make legacy columns non-nullable again
    op.alter_column('integration_logs', 'message', nullable=False)
    op.alter_column('integration_logs', 'log_level', nullable=False)
    op.alter_column('integration_logs', 'process_name', nullable=False)

    # Drop new columns
    op.drop_column('integration_logs', 'details')
    op.drop_column('integration_logs', 'payload_hash')
    op.drop_column('integration_logs', 'retry_count')
    op.drop_column('integration_logs', 'elapsed_ms')
    op.drop_column('integration_logs', 'external_system')
    op.drop_column('integration_logs', 'status')
    op.drop_column('integration_logs', 'step')
    op.drop_column('integration_logs', 'request_id')
    op.drop_column('integration_logs', 'run_id')
    op.drop_column('integration_logs', 'ts')