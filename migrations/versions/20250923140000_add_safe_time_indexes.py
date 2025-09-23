"""add safe time indexes

Revision ID: 20250923140000
Revises: 20250923130000
Create Date: 2025-09-23 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250923140000"
down_revision = "20250923130000"
branch_labels = None
depends_on = None


def upgrade():
    # Create safe indexes on time fields
    op.execute("CREATE INDEX IF NOT EXISTS ix_integration_logs_ts ON integration_logs (ts);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_integration_logs_created_at ON integration_logs (created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_integration_logs_ts_notnull ON integration_logs (ts) WHERE ts IS NOT NULL;")


def downgrade():
    # Drop the indexes
    op.drop_index("ix_integration_logs_ts_notnull", table_name="integration_logs")
    op.drop_index("ix_integration_logs_created_at", table_name="integration_logs")
    op.drop_index("ix_integration_logs_ts", table_name="integration_logs")