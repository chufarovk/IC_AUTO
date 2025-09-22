"""Add job_id and complete integration_logs table for Task006

Revision ID: 20250922150000
Revises: 20250922120000
Create Date: 2025-09-22 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250922150000'
down_revision = '20250922120000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add job_id column
    op.add_column('integration_logs', sa.Column('job_id', sa.String(36), nullable=True))
    op.create_index('ix_integration_logs_job_id', 'integration_logs', ['job_id'])

    # Change id column from Integer to BigInteger
    op.alter_column('integration_logs', 'id', type_=sa.BigInteger(), postgresql_using='id::bigint')

    # Create combined time index as specified in DDL
    op.create_index('ix_integration_logs_time', 'integration_logs',
                   [sa.text('COALESCE(ts, created_at)')], postgresql_where=None)


def downgrade() -> None:
    # Drop time index
    op.drop_index('ix_integration_logs_time', table_name='integration_logs')

    # Change id column back to Integer
    op.alter_column('integration_logs', 'id', type_=sa.Integer(), postgresql_using='id::integer')

    # Drop job_id
    op.drop_index('ix_integration_logs_job_id', table_name='integration_logs')
    op.drop_column('integration_logs', 'job_id')