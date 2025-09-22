#!/usr/bin/env python3
"""
Script to diagnose Alembic migration state
"""
import os
import sys
import subprocess
from pathlib import Path

def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def main():
    """Main diagnostic function"""
    print("=== Alembic Migration Diagnostics ===")

    # Check if we're in the right directory
    if not Path("alembic.ini").exists():
        print("❌ alembic.ini not found. Are you in the project root?")
        sys.exit(1)

    # Check heads
    print("\n1. Checking migration heads...")
    code, out, err = run_command(["alembic", "heads"])
    if code != 0:
        print(f"❌ alembic heads failed: {err}")
        return

    heads = [line.split(" ")[0] for line in out.splitlines() if line.strip()]
    print(f"📋 Found {len(heads)} head(s): {heads}")

    if len(heads) <= 1:
        print("✅ Single head detected - no merge needed")
        return

    print("⚠️  Multiple heads detected - merge required")

    # Show history
    print("\n2. Migration history (last 20 entries)...")
    code, out, err = run_command(["alembic", "history", "--verbose"])
    if code != 0:
        print(f"❌ alembic history failed: {err}")
        return

    lines = out.splitlines()
    for line in lines[-20:]:  # Show last 20 lines
        if line.strip():
            print(f"  {line}")

    # Show current revision
    print("\n3. Current database revision...")
    code, out, err = run_command(["alembic", "current"])
    if code != 0:
        print(f"❌ alembic current failed: {err}")
        return

    if out.strip():
        print(f"📍 Current: {out.strip()}")
    else:
        print("📍 Current: None (database not initialized)")

    print("\n=== Recommendations ===")
    if len(heads) > 1:
        print("To merge heads, run:")
        print(f"  alembic merge -m 'merge heads' {' '.join(heads)}")
        print("  alembic upgrade head")

if __name__ == "__main__":
    main()