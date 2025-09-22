"""Create integration_logs table

Revision ID: 20240911000000
Revises: 
Create Date: 2025-09-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240911000000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'integration_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('process_name', sa.String(length=100), nullable=False),
        sa.Column('log_level', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_integration_logs_process_name', 'integration_logs', ['process_name'])
    op.create_index('ix_integration_logs_log_level', 'integration_logs', ['log_level'])


def downgrade() -> None:
    op.drop_index('ix_integration_logs_log_level', table_name='integration_logs')
    op.drop_index('ix_integration_logs_process_name', table_name='integration_logs')
    op.drop_table('integration_logs')
