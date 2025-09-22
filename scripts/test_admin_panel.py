#!/usr/bin/env python3
"""
Test script to verify the new admin panel functionality
"""
import os
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

def test_database_connection():
    """Test database connection using admin panel settings"""
    print("🧪 Testing database connection...")

    db_url = os.getenv("ADMIN_DB_URL", "postgresql+psycopg2://user:password@db:5432/bisnesmedia")

    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            # Test basic connection
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful")

            # Test integration_logs table exists
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'integration_logs'
            """))
            if result.fetchone():
                print("✅ integration_logs table exists")

                # Test query similar to admin panel
                result = conn.execute(text("""
                    SELECT
                      COALESCE(ts, created_at) AS created_at,
                      COALESCE(process_name, step) AS process_name,
                      COALESCE(log_level, status) AS log_level,
                      COALESCE(message, details->>'message') AS message,
                      run_id,
                      request_id,
                      job_id,
                      step,
                      status,
                      external_system,
                      elapsed_ms,
                      retry_count,
                      payload_hash,
                      details,
                      payload
                    FROM integration_logs
                    ORDER BY COALESCE(ts, created_at) DESC
                    LIMIT 5
                """))

                rows = result.fetchall()
                print(f"✅ Query successful, found {len(rows)} sample records")

                if rows:
                    print("📋 Sample record structure:")
                    for key in rows[0]._fields:
                        print(f"  - {key}")

                return True
            else:
                print("⚠️  integration_logs table not found")
                return False

    except SQLAlchemyError as e:
        print(f"❌ Database connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_environment_variables():
    """Test that environment variables are set correctly"""
    print("\n🧪 Testing environment variables...")

    required_vars = [
        "ADMIN_DB_URL",
        "ADMIN_POLL_SECONDS",
        "ADMIN_PAGE_SIZE"
    ]

    all_set = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var} = {value}")
        else:
            print(f"❌ {var} is not set")
            all_set = False

    return all_set

def test_imports():
    """Test that all required imports work"""
    print("\n🧪 Testing imports...")

    try:
        import asyncio
        import json
        import pandas as pd
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import SQLAlchemyError

        try:
            from sqlalchemy.ext.asyncio import create_async_engine
            print("✅ Async SQLAlchemy available")
        except ImportError:
            print("⚠️  Async SQLAlchemy not available (using sync mode)")

        print("✅ All imports successful")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def main():
    """Run all tests"""
    print("=== Admin Panel Test Suite ===\n")

    tests = [
        test_environment_variables,
        test_imports,
        test_database_connection,
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()

    print(f"=== Results: {passed}/{len(tests)} tests passed ===")

    if passed == len(tests):
        print("🎉 All tests passed! Admin panel should work correctly.")
        print("\n🚀 To start the admin panel:")
        print("  docker compose -f docker-compose.dev.yml up -d --build admin_panel")
        print("  Then visit: http://localhost:8501")
        return 0
    else:
        print("❌ Some tests failed. Please check the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())