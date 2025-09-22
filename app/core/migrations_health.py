"""
Migration health checks and diagnostics for Alembic.

This module provides utilities to detect and handle multi-head scenarios,
ensuring robust migration management across development and production environments.
"""
import logging
import os
import subprocess
from typing import List, Tuple

logger = logging.getLogger("migrations")


def _run_alembic_command(cmd: List[str]) -> Tuple[int, str, str]:
    """
    Execute an Alembic command and return (returncode, stdout, stderr).

    Args:
        cmd: Command list to execute

    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out after 60 seconds"
    except Exception as e:
        return 1, "", f"Command failed: {e}"


def get_migration_heads() -> List[str]:
    """
    Get list of current migration heads.

    Returns:
        List of revision IDs that are current heads
    """
    code, out, err = _run_alembic_command(["alembic", "heads"])

    if code != 0:
        logger.error("Failed to get migration heads", extra={"stderr": err})
        return []

    heads = [line.split(" ")[0] for line in out.splitlines() if line.strip()]
    return heads


def assert_single_head_or_explain() -> None:
    """
    Check that there's exactly one migration head.

    In production: raises RuntimeError if multiple heads detected.
    In development: logs warning but continues execution.

    Raises:
        RuntimeError: If multiple heads detected in production environment
    """
    heads = get_migration_heads()

    if len(heads) <= 1:
        if heads:
            logger.info("Migration health: single head detected",
                       extra={"head": heads[0]})
        else:
            logger.warning("Migration health: no heads detected (database may not be initialized)")
        return

    # Multiple heads detected
    logger.error("Migration health: multiple heads detected",
                extra={"heads": heads, "count": len(heads)})

    hint = (
        "Multiple Alembic heads detected. This indicates parallel migration branches.\n"
        f"Current heads: {', '.join(heads)}\n\n"
        "To resolve in development:\n"
        f"  alembic merge -m 'merge heads' {' '.join(heads)}\n"
        "  alembic upgrade head\n\n"
        "For more details, see: https://alembic.sqlalchemy.org/en/latest/tutorial.html#merging-branches"
    )

    # Environment-based behavior
    env = os.getenv("ENV", "dev").lower()

    if env in ("dev", "development", "local"):
        logger.warning("Development mode: continuing despite multi-head. "
                      "Consider merging ASAP to avoid future issues.",
                      extra={"hint": hint})
        return

    # Production-like environments: fail fast
    logger.critical("Production environment: refusing to start with multiple migration heads",
                   extra={"hint": hint})
    raise RuntimeError(f"Multiple migration heads detected: {', '.join(heads)}. {hint}")


def get_current_revision() -> str:
    """
    Get the current database revision.

    Returns:
        Current revision ID or None if not initialized
    """
    code, out, err = _run_alembic_command(["alembic", "current"])

    if code != 0:
        logger.error("Failed to get current revision", extra={"stderr": err})
        return None

    if not out.strip():
        return None

    # Parse revision from output like "Current revision(s): 20240911001000"
    lines = out.splitlines()
    for line in lines:
        if "Current revision" in line:
            # Extract revision ID from the line
            parts = line.split()
            if len(parts) >= 3:
                return parts[-1]

    return None


def is_database_up_to_date() -> bool:
    """
    Check if database is up to date with latest migrations.

    Returns:
        True if database is at the latest head revision
    """
    heads = get_migration_heads()
    current = get_current_revision()

    if not heads or not current:
        return False

    # If we have multiple heads, database can't be "up to date"
    if len(heads) > 1:
        return False

    return current == heads[0]


def log_migration_status() -> None:
    """
    Log comprehensive migration status for debugging.
    """
    logger.info("=== Migration Status Report ===")

    heads = get_migration_heads()
    current = get_current_revision()

    logger.info(f"Migration heads: {heads} (count: {len(heads)})")
    logger.info(f"Current revision: {current}")

    if len(heads) > 1:
        logger.warning("⚠️  MULTI-HEAD DETECTED - Manual intervention required")

    if current and len(heads) == 1 and current == heads[0]:
        logger.info("✅ Database is up to date")
    elif current and len(heads) == 1:
        logger.info(f"📈 Database at {current}, latest is {heads[0]} - upgrade needed")
    elif not current:
        logger.info("🆕 Database not initialized - migration needed")
    else:
        logger.warning("❌ Migration state unclear - manual check recommended")