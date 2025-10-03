#!/usr/bin/env python3
"""
Test runner for reaction betting spam resistance tests.

This script runs comprehensive tests to verify that the reaction betting system
can handle all forms of user spam and edge cases without breaking.
"""

import sys
import os
import subprocess

# Add the betbot directory to Python path
betbot_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, betbot_dir)


def run_tests():
    """Run all reaction betting tests."""
    print("🧪 Running Reaction Betting Spam Resistance Tests")
    print("=" * 60)

    # Test files to run
    test_files = [
        "tests/test_reaction_spam_resistance.py",
        "tests/test_reaction_integration.py",
    ]

    # Check if pytest is available
    try:
        import pytest

        pytest_available = True
    except ImportError:
        pytest_available = False
        print("⚠️  Warning: pytest not installed. Install with: pip install pytest")

    if pytest_available:
        print("🚀 Running tests with pytest...")

        for test_file in test_files:
            if os.path.exists(test_file):
                print(f"\n📝 Running {test_file}:")
                print("-" * 40)

                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        test_file,
                        "-v",
                        "--tb=short",
                        "--no-header",
                    ],
                    capture_output=False,
                )

                if result.returncode == 0:
                    print(f"✅ {test_file} - ALL TESTS PASSED")
                else:
                    print(f"❌ {test_file} - SOME TESTS FAILED")
            else:
                print(f"⚠️  Test file not found: {test_file}")

    else:
        print("📋 Test files available for manual review:")
        for test_file in test_files:
            if os.path.exists(test_file):
                print(f"  ✓ {test_file}")
            else:
                print(f"  ✗ {test_file} (not found)")

    print("\n" + "=" * 60)
    print("🎯 Test Categories Covered:")
    print("  • Rapid fire same emoji spam")
    print("  • Rapid emoji switching")
    print("  • Multiple users concurrent spam")
    print("  • Timer cancellation edge cases")
    print("  • Discord API rate limits")
    print("  • Network delays and timeouts")
    print("  • Permission errors")
    print("  • Message deletion during processing")
    print("  • Memory leak prevention")
    print("  • Large-scale concurrent load")
    print("  • Bot restart state recovery")
    print("  • Logging system stress testing")

    print("\n💡 To run specific tests:")
    print(
        "  python -m pytest tests/test_reaction_spam_resistance.py::TestReactionSpamResistance::test_rapid_fire_same_emoji -v"
    )

    print("\n📊 Test Results Analysis:")
    print("  • All tests passing = System is spam-resistant")
    print("  • Memory tests passing = No memory leaks")
    print("  • Concurrency tests passing = Thread-safe")
    print("  • Integration tests passing = Discord.py compatible")


def check_system_health():
    """Check if the reaction betting system is properly configured."""
    print("\n🔍 System Health Check:")
    print("-" * 30)

    try:
        from cogs.betting import Betting as BettingCog

        print("✅ Betting (BettingCog) import successful")

        # Check key attributes exist
        from unittest.mock import Mock

        mock_bot = Mock()
        cog = BettingCog(mock_bot)
        required_attrs = [
            "_pending_bets",
            "_active_timers",
            "_users_in_cleanup",
            "_deferred_reactions",
            "_last_enforcement",
            "_reaction_sequence",
        ]

        for attr in required_attrs:
            if hasattr(cog, attr):
                print(f"✅ {attr} attribute present")
            else:
                print(f"❌ {attr} attribute missing")

    except ImportError as e:
        print(f"❌ Import error: {e}")
    except Exception as e:
        print(f"⚠️  Unexpected error: {e}")


def simulate_spam_scenario():
    """Simulate a realistic spam scenario for manual testing."""
    print("\n🎮 Manual Spam Test Scenario:")
    print("-" * 35)
    print("To manually test spam resistance:")
    print("1. Start the bot with comprehensive logging:")
    print("   python scripts/watcher.py --logging")
    print("")
    print("2. In Discord, rapidly spam reactions on a betting message:")
    print("   • Click 🔥 → ⚡ → 💪 → 🏆 → 🌟 → 💎 → 🚀 → 👑")
    print("   • Click as fast as possible, multiple times each")
    print("   • Try clicking the same emoji repeatedly")
    print("   • Get multiple users to spam simultaneously")
    print("")
    print("3. Expected behavior:")
    print("   ✅ Only final reaction should remain on message")
    print("   ✅ Bet should be placed for final emoji only")
    print("   ✅ No crashes or errors in logs")
    print("   ✅ System should stay responsive")
    print("")
    print("4. Check logs/reaction_debug.log for:")
    print("   • 🔍 REACTION ADD entries for each click")
    print("   • 🔍 PROCESS BATCH showing final processing")
    print("   • 🔍 REMOVE REACTIONS showing cleanup")
    print("   • No error messages or exceptions")


if __name__ == "__main__":
    print("🤖 Reaction Betting Spam Resistance Test Suite")
    print("=" * 50)

    if len(sys.argv) > 1:
        if sys.argv[1] == "health":
            check_system_health()
        elif sys.argv[1] == "manual":
            simulate_spam_scenario()
        elif sys.argv[1] == "run":
            run_tests()
        else:
            print("Usage: python test_spam_resistance.py [health|manual|run]")
    else:
        # Run everything by default
        check_system_health()
        run_tests()
        simulate_spam_scenario()
