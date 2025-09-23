"""create integration_logs

Revision ID: 20240922_create_integration_logs
Revises:
Create Date: 2025-09-22 21:05:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "20240922_create_integration_logs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now() AT TIME ZONE 'utc')")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now() AT TIME ZONE 'utc')")),
        sa.Column("process_name", sa.Text(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("log_level", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("external_system", sa.String(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("payload_hash", sa.String(), nullable=True),
        sa.Column("details", JSONB, nullable=True),
    )
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_integration_logs_time
        ON integration_logs (COALESCE(ts, created_at));
    """)


def downgrade():
    op.drop_index("ix_integration_logs_time", table_name="integration_logs")
    op.drop_table("integration_logs")