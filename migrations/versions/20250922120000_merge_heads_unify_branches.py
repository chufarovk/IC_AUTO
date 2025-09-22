"""merge heads: unify 20240911001000 and 20250922000000

Revision ID: 20250922120000
Revises: 20240911001000, 20250922000000
Create Date: 2025-09-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250922120000'
down_revision = ('20240911001000', '20250922000000')
branch_labels = None
depends_on = None


def upgrade():
    """Merge-only migration: no DDL required.

    This migration exists solely to unify two parallel migration branches:
    - 20240911001000: creates pending_transfers and outbox_events tables
    - 20250922000000: adds observability fields to integration_logs

    Both branches depend on 20240911000000, creating a multi-head scenario.
    This merge point allows future migrations to have a single head.
    """
    pass


def downgrade():
    """Technically can't 'unmerge' reliably; keep it a no-op.

    Unmerging parallel branches would require complex logic to determine
    which changes came from which branch, which is not reliably reversible.
    If you need to undo this merge, manually recreate the branch split.
    """
    pass