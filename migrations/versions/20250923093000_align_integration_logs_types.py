"""Align integration_logs UUID and JSONB types

Revision ID: 20250923093000
Revises: 20250922150000
Create Date: 2025-09-23 09:30:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20250923093000"
down_revision = "20250922150000"
branch_labels = None
depends_on = None

_UUID_REGEX = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def _bind():
    return op.get_bind()


def _column_type(column: str) -> str | None:
    result = _bind().execute(
        sa.text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'integration_logs' AND column_name = :column
            """
        ),
        {"column": column},
    ).scalar()
    return result.lower() if result else None


def _index_exists(name: str) -> bool:
    qualified = name if "." in name else f"public.{name}"
    return _bind().execute(sa.text("SELECT to_regclass(:name)"), {"name": qualified}).scalar() is not None


def _log(message: str) -> None:
    ctx = op.get_context()
    if hasattr(ctx.impl, "static_output"):
        ctx.impl.static_output(message)
    else:
        print(message)


def _sanitize_uuid_columns() -> None:
    for column in ("run_id", "request_id", "job_id"):
        result = _bind().execute(
            sa.text(
                """
                UPDATE integration_logs
                SET {column} = NULL
                WHERE {column} IS NOT NULL AND {column} !~* :uuid_regex
                """.format(column=column)
            ),
            {"uuid_regex": _UUID_REGEX},
        )
        if result.rowcount:
            _log(f"Sanitized {result.rowcount} rows in integration_logs.{column}")


def upgrade() -> None:
    connection = _bind()
    inspector = sa.inspect(connection)

    if inspector.has_table("integration_logs"):
        _sanitize_uuid_columns()
        columns = {col["name"] for col in inspector.get_columns("integration_logs")}
    else:
        _log("integration_logs table does not exist yet; skipping sanitation step")
        columns = set()

    for index_name in (
        "ix_integration_logs_run_id",
        "ix_integration_logs_request_id",
        "ix_integration_logs_job_id",
        "ix_integration_logs_job_name",
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name="integration_logs")

    uuid_type = postgresql.UUID(as_uuid=True)
    jsonb_type = postgresql.JSONB(astext_type=sa.Text())

    if _column_type("run_id") != "uuid":
        op.alter_column(
            "integration_logs",
            "run_id",
            existing_type=sa.String(length=36),
            type_=uuid_type,
            existing_nullable=True,
            postgresql_using="run_id::uuid",
        )

    if _column_type("request_id") != "uuid":
        op.alter_column(
            "integration_logs",
            "request_id",
            existing_type=sa.String(length=36),
            type_=uuid_type,
            existing_nullable=True,
            postgresql_using="request_id::uuid",
        )

    if _column_type("job_id") != "uuid":
        op.alter_column(
            "integration_logs",
            "job_id",
            existing_type=sa.String(length=36),
            type_=uuid_type,
            existing_nullable=True,
            postgresql_using="job_id::uuid",
        )

    if _column_type("details") != "jsonb":
        op.alter_column(
            "integration_logs",
            "details",
            existing_type=sa.JSON(),
            type_=jsonb_type,
            existing_nullable=True,
            postgresql_using="details::jsonb",
        )

    if _column_type("payload") != "jsonb":
        op.alter_column(
            "integration_logs",
            "payload",
            existing_type=sa.JSON(),
            type_=jsonb_type,
            existing_nullable=True,
            postgresql_using="payload::jsonb",
        )

    if "job_name" not in columns:
        op.add_column("integration_logs", sa.Column("job_name", sa.Text(), nullable=True))

    for index_name, column in (
        ("ix_integration_logs_run_id", "run_id"),
        ("ix_integration_logs_request_id", "request_id"),
        ("ix_integration_logs_job_id", "job_id"),
        ("ix_integration_logs_job_name", "job_name"),
    ):
        if not _index_exists(index_name):
            op.create_index(index_name, "integration_logs", [column], unique=False)


def downgrade() -> None:
    for index_name in (
        "ix_integration_logs_job_name",
        "ix_integration_logs_job_id",
        "ix_integration_logs_request_id",
        "ix_integration_logs_run_id",
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name="integration_logs")

    op.drop_column("integration_logs", "job_name")

    op.alter_column(
        "integration_logs",
        "payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="payload::json",
    )
    op.alter_column(
        "integration_logs",
        "details",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="details::json",
    )

    string_type = sa.String(length=36)
    op.alter_column(
        "integration_logs",
        "job_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=string_type,
        existing_nullable=True,
        postgresql_using="job_id::text",
    )
    op.alter_column(
        "integration_logs",
        "request_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=string_type,
        existing_nullable=True,
        postgresql_using="request_id::text",
    )
    op.alter_column(
        "integration_logs",
        "run_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=string_type,
        existing_nullable=True,
        postgresql_using="run_id::text",
    )

    op.create_index("ix_integration_logs_run_id", "integration_logs", ["run_id"])
    op.create_index("ix_integration_logs_request_id", "integration_logs", ["request_id"])
    op.create_index("ix_integration_logs_job_id", "integration_logs", ["job_id"])
