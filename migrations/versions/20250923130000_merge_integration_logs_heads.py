"""merge integration_logs heads

Revision ID: 20250923130000
Revises: 20240922_create_integration_logs, 20250923113000
Create Date: 2025-09-23 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250923130000"
down_revision = ("20240922_create_integration_logs", "20250923113000")
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge migration - no changes needed
    # Both branches should have converged to the same schema
    pass


def downgrade():
    # This is a merge migration - no changes needed
    pass