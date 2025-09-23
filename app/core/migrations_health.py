"""
Migration health checks and diagnostics for Alembic.

This module provides utilities to detect and handle multi-head scenarios,
ensuring robust migration management across development and production environments.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("migrations")

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))


def _alembic_cmd(*parts: str) -> List[str]:
    """Build an Alembic command that uses the in-project interpreter/module."""
    return [sys.executable, "-m", "alembic", *parts]


def _run_alembic_command(cmd: List[str]) -> Tuple[int, str, str]:
    """Execute an Alembic command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out after 60 seconds"
    except Exception as exc:
        return 1, "", f"Command failed: {exc}"


def get_migration_heads() -> List[str]:
    """Get list of current migration heads."""
    code, out, err = _run_alembic_command(_alembic_cmd("heads"))

    if code != 0:
        logger.error("Failed to get migration heads", extra={"stderr": err})
        return []

    return [line.split(" ")[0] for line in out.splitlines() if line.strip()]


def assert_single_head_or_explain() -> None:
    """Check that there's exactly one migration head."""
    heads = get_migration_heads()

    if len(heads) <= 1:
        if heads:
            logger.info("Migration health: single head detected", extra={"head": heads[0]})
        else:
            logger.warning("Migration health: no heads detected (database may not be initialized)")
        return

    logger.error("Migration health: multiple heads detected", extra={"heads": heads, "count": len(heads)})

    hint = (
        "Multiple Alembic heads detected. This indicates parallel migration branches.\n"
        f"Current heads: {', '.join(heads)}\n\n"
        "To resolve in development:\n"
        f"  alembic merge -m 'merge heads' {' '.join(heads)}\n"
        "  alembic upgrade head\n\n"
        "For more details, see: https://alembic.sqlalchemy.org/en/latest/tutorial.html#merging-branches"
    )

    env = os.getenv("ENV", "dev").lower()

    if env in ("dev", "development", "local"):
        logger.warning(
            "Development mode: continuing despite multi-head. Consider merging ASAP to avoid future issues.",
            extra={"hint": hint},
        )
        return

    logger.critical(
        "Production environment: refusing to start with multiple migration heads",
        extra={"hint": hint},
    )
    raise RuntimeError(f"Multiple migration heads detected: {', '.join(heads)}. {hint}")


def get_current_revision() -> str | None:
    """Return the current database revision."""
    code, out, err = _run_alembic_command(_alembic_cmd("current"))

    if code != 0:
        logger.error("Failed to get current revision", extra={"stderr": err})
        return None

    if not out.strip():
        return None

    for line in out.splitlines():
        if "Current revision" in line:
            parts = line.split()
            if len(parts) >= 3:
                return parts[-1]
    return None


def is_database_up_to_date() -> bool:
    """Check if database is at the latest head revision."""
    heads = get_migration_heads()
    current = get_current_revision()

    if not heads or not current:
        return False

    if len(heads) > 1:
        return False

    return current == heads[0]


def log_migration_status() -> None:
    """Log comprehensive migration status for debugging."""
    logger.info("=== Migration Status Report ===")

    heads = get_migration_heads()
    current = get_current_revision()

    logger.info("Migration heads: %s (count: %s)", heads, len(heads))
    logger.info("Current revision: %s", current)

    if len(heads) > 1:
        logger.warning("⚠️  MULTI-HEAD DETECTED - Manual intervention required")

    if current and len(heads) == 1 and current == heads[0]:
        logger.info("✅ Database is up to date")
    elif current and len(heads) == 1:
        logger.info("ℹ️ Database at %s, latest is %s - upgrade needed", current, heads[0])
    elif not current:
        logger.info("ℹ️ Database not initialized - migration needed")
    else:
        logger.warning("❓ Migration state unclear - manual check recommended")
