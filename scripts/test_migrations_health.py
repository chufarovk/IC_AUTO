#!/usr/bin/env python3
"""
Test script to verify migration health checks work correctly in dev and prod modes.
"""
import os
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.migrations_health import assert_single_head_or_explain, get_migration_heads


def test_dev_mode_behavior():
    """Test that dev mode allows continuing with multi-head."""
    print("🧪 Testing DEV mode behavior...")

    # Mock multiple heads
    with patch('app.core.migrations_health.get_migration_heads', return_value=['head1', 'head2']), \
         patch('app.core.migrations_health._run_alembic_command') as mock_run, \
         patch.dict(os.environ, {'ENV': 'dev'}):

        mock_run.return_value = (0, 'head1\nhead2', '')

        try:
            assert_single_head_or_explain()
            print("✅ DEV mode: Multi-head allowed with warning")
        except RuntimeError:
            print("❌ DEV mode: Should not raise RuntimeError")
            return False

    return True


def test_prod_mode_behavior():
    """Test that prod mode fails fast on multi-head."""
    print("🧪 Testing PROD mode behavior...")

    with patch('app.core.migrations_health.get_migration_heads', return_value=['head1', 'head2']), \
         patch('app.core.migrations_health._run_alembic_command') as mock_run, \
         patch.dict(os.environ, {'ENV': 'prod'}):

        mock_run.return_value = (0, 'head1\nhead2', '')

        try:
            assert_single_head_or_explain()
            print("❌ PROD mode: Should have raised RuntimeError")
            return False
        except RuntimeError as e:
            if "Multiple migration heads detected" in str(e):
                print("✅ PROD mode: Correctly failed with RuntimeError")
                return True
            else:
                print(f"❌ PROD mode: Wrong error message: {e}")
                return False


def test_single_head_behavior():
    """Test that single head works in both modes."""
    print("🧪 Testing single head behavior...")

    for env in ['dev', 'prod']:
        with patch('app.core.migrations_health.get_migration_heads', return_value=['single_head']), \
             patch('app.core.migrations_health._run_alembic_command') as mock_run, \
             patch.dict(os.environ, {'ENV': env}):

            mock_run.return_value = (0, 'single_head', '')

            try:
                assert_single_head_or_explain()
                print(f"✅ {env.upper()} mode: Single head works correctly")
            except Exception as e:
                print(f"❌ {env.upper()} mode: Single head should not raise: {e}")
                return False

    return True


def test_alembic_command_failure():
    """Test behavior when alembic command fails."""
    print("🧪 Testing alembic command failure...")

    with patch('app.core.migrations_health._run_alembic_command', return_value=(1, '', 'Command failed')), \
         patch.dict(os.environ, {'ENV': 'dev'}):

        try:
            assert_single_head_or_explain()
            print("✅ Command failure handled gracefully")
            return True
        except Exception as e:
            print(f"❌ Command failure should not raise: {e}")
            return False


def main():
    """Run all tests."""
    print("=== Migration Health Test Suite ===\n")

    tests = [
        test_dev_mode_behavior,
        test_prod_mode_behavior,
        test_single_head_behavior,
        test_alembic_command_failure,
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()

    print(f"=== Results: {passed}/{len(tests)} tests passed ===")

    if passed == len(tests):
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())