"""
Manual test script for Phase 3 session management commands.
This simulates the session management workflow.
"""

from data_manager import (
    load_data,
    save_data,
    is_multi_session_mode,
    find_session_by_contestant,
)
import time


def simulate_opensession_command(
    data, session_id, contestant1, contestant2, timer_duration=300
):
    """Simulate the !opensession command logic."""
    print(f"\n🎯 Creating session '{session_id}' with {contestant1} vs {contestant2}")

    # Initialize multi-session mode if not already enabled
    if not is_multi_session_mode(data):
        print("✅ Converting to multi-session mode")
        data["betting_sessions"] = {}
        data["active_sessions"] = []
        data["contestant_to_session"] = {}
        data["multi_session_mode"] = True

    # Check if session already exists
    if session_id in data.get("betting_sessions", {}):
        print(f"❌ Session '{session_id}' already exists")
        return False

    # Validate contestant names
    contestant1 = contestant1.strip()
    contestant2 = contestant2.strip()

    if not contestant1 or not contestant2:
        print("❌ Contestant names cannot be empty")
        return False

    if contestant1.lower() == contestant2.lower():
        print("❌ Contestant names must be different")
        return False

    # Check for contestant name conflicts across sessions
    existing_contestants = set()
    for existing_session in data.get("betting_sessions", {}).values():
        for contestant_name in existing_session.get("contestants", {}).values():
            existing_contestants.add(contestant_name.lower())

    if contestant1.lower() in existing_contestants:
        print(f"❌ Contestant '{contestant1}' already exists in another session")
        return False

    if contestant2.lower() in existing_contestants:
        print(f"❌ Contestant '{contestant2}' already exists in another session")
        return False

    # Create the new session
    new_session = {
        "status": "open",
        "contestants": {"c1": contestant1, "c2": contestant2},
        "bets": {},
        "timer_config": {"enabled": True, "duration": timer_duration},
        "created_at": time.time(),
        "created_by": "test_user",
    }

    # Add session to data
    data["betting_sessions"][session_id] = new_session
    data["active_sessions"].append(session_id)

    # Update contestant mapping
    data["contestant_to_session"][contestant1.lower()] = session_id
    data["contestant_to_session"][contestant2.lower()] = session_id

    print(f"✅ Session '{session_id}' created successfully")
    print(f"   - Contestants: {contestant1} vs {contestant2}")
    print(f"   - Timer: {timer_duration} seconds")
    print(f"   - Status: Open for betting")

    return True


def simulate_listsessions_command(data):
    """Simulate the !listsessions command logic."""
    print(f"\n📋 Listing active sessions...")

    if not is_multi_session_mode(data):
        print("❌ Multi-session mode is not active")
        return

    active_sessions = data.get("active_sessions", [])

    if not active_sessions:
        print("📋 No active sessions")
        return

    session_list = []
    total_bets = 0
    open_sessions = 0

    for session_id in active_sessions:
        session = data["betting_sessions"].get(session_id, {})
        contestants = session.get("contestants", {})
        bets = session.get("bets", {})
        status = session.get("status", "unknown")

        status_emoji = (
            "🟢" if status == "open" else "🔒" if status == "locked" else "❓"
        )

        session_info = f"{status_emoji} {session_id}: {', '.join(contestants.values())} ({len(bets)} bets)"
        session_list.append(session_info)

        total_bets += len(bets)
        if status == "open":
            open_sessions += 1

    print(f"📊 Summary:")
    print(f"   - Active Sessions: {len(active_sessions)}")
    print(f"   - Open for Betting: {open_sessions}")
    print(f"   - Total Bets: {total_bets}")
    print(f"📋 Sessions:")
    for session_info in session_list:
        print(f"   {session_info}")


def simulate_sessioninfo_command(data, session_id):
    """Simulate the !sessioninfo command logic."""
    print(f"\n📊 Getting info for session '{session_id}'...")

    if not is_multi_session_mode(data):
        print("❌ Multi-session mode is not active")
        return

    session = data.get("betting_sessions", {}).get(session_id)
    if not session:
        print(f"❌ Session '{session_id}' not found")
        return

    # Gather session details
    contestants = session.get("contestants", {})
    bets = session.get("bets", {})
    status = session.get("status", "unknown")
    timer_config = session.get("timer_config", {})
    created_at = session.get("created_at", 0)

    # Calculate betting statistics
    total_pot = sum(bet["amount"] for bet in bets.values())

    contestant_stats = {}
    for contestant_key, contestant_name in contestants.items():
        contestant_bets = [
            bet for bet in bets.values() if bet["choice"] == contestant_name.lower()
        ]
        contestant_stats[contestant_name] = {
            "bets": len(contestant_bets),
            "pot": sum(bet["amount"] for bet in contestant_bets),
        }

    # Status display
    status_emoji = "🟢" if status == "open" else "🔒" if status == "locked" else "❌"

    # Timer info
    timer_info = "Disabled"
    if timer_config.get("enabled"):
        duration = timer_config.get("duration", 300)
        timer_info = f"{duration} seconds"

    print(f"✅ Session Info:")
    print(f"   - Status: {status_emoji} {status.title()}")
    print(f"   - Contestants: {', '.join(contestants.values())}")
    print(f"   - Total Bets: {len(bets)}")
    print(f"   - Total Pot: {total_pot} coins")
    print(f"   - Timer: {timer_info}")

    # Add betting breakdown if there are bets
    if bets:
        print(f"📊 Betting Breakdown:")
        for contestant_name, stats in contestant_stats.items():
            percentage = (stats["pot"] / total_pot * 100) if total_pot > 0 else 0
            print(
                f"   - {contestant_name}: {stats['bets']} bets, {stats['pot']} coins ({percentage:.1f}%)"
            )


def simulate_closesession_command(data, session_id, winner=None):
    """Simulate the !closesession command logic."""
    print(
        f"\n🔒 Closing session '{session_id}'"
        + (f" with winner '{winner}'" if winner else "")
    )

    if not is_multi_session_mode(data):
        print("❌ Multi-session mode is not active")
        return False

    session = data.get("betting_sessions", {}).get(session_id)
    if not session:
        print(f"❌ Session '{session_id}' not found")
        return False

    contestants = session.get("contestants", {})
    bets = session.get("bets", {})

    # If winner is specified, validate it
    if winner:
        winner_found = False
        for contestant_name in contestants.values():
            if contestant_name.lower() == winner.lower():
                winner = contestant_name  # Use exact case from session
                winner_found = True
                break

        if not winner_found:
            contestants_list = ", ".join(contestants.values())
            print(
                f"❌ Winner '{winner}' not found. Valid contestants: {contestants_list}"
            )
            return False

    # Calculate payouts if there's a winner and bets exist
    if winner and bets:
        total_pot = sum(bet["amount"] for bet in bets.values())
        winning_bets = [bet for bet in bets.values() if bet["choice"] == winner.lower()]
        winning_pot = sum(bet["amount"] for bet in winning_bets)

        print(f"💰 Processing payouts:")
        print(f"   - Total Pot: {total_pot} coins")
        print(f"   - Winning Bets: {len(winning_bets)}")
        print(f"   - Winning Pot: {winning_pot} coins")

        # Process payouts
        if winning_bets:
            for user_id, bet in bets.items():
                initial_balance = data["balances"][user_id]
                if bet["choice"] == winner.lower():
                    # Winner gets their share of the total pot
                    winnings = int((bet["amount"] / winning_pot) * total_pot)
                    data["balances"][user_id] += winnings
                    print(
                        f"   - {user_id}: {initial_balance} → {data['balances'][user_id]} (+{winnings})"
                    )

    # Remove session from active list and update mappings
    if session_id in data.get("active_sessions", []):
        data["active_sessions"].remove(session_id)

    # Remove contestants from mapping
    for contestant_name in contestants.values():
        data.get("contestant_to_session", {}).pop(contestant_name.lower(), None)

    # Mark session as closed
    session["status"] = "closed"
    if winner:
        session["winner"] = winner

    print(f"✅ Session '{session_id}' closed successfully")
    if winner:
        print(f"   - Winner: {winner}")
    return True


def main():
    """Run the manual test for Phase 3."""
    print("🧪 Manual Test: Phase 3 Session Management")
    print("=" * 50)

    # Start with empty data
    data = {
        "balances": {"user1": 1000, "user2": 1500, "user3": 500},
        "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
        "settings": {"enable_bet_timer": True, "bet_channel_id": None},
    }

    print(f"Initial data: Legacy mode, no sessions")

    # Test 1: Create first session
    print(f"\n{'=' * 20} TEST 1: Create First Session {'=' * 20}")
    success = simulate_opensession_command(
        data, "nfl_patriots_cowboys", "New England Patriots", "Dallas Cowboys", 600
    )
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")

    # Test 2: Create second session
    print(f"\n{'=' * 20} TEST 2: Create Second Session {'=' * 20}")
    success = simulate_opensession_command(
        data, "nba_lakers_warriors", "Los Angeles Lakers", "Golden State Warriors", 900
    )
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")

    # Test 3: Try to create session with duplicate contestant
    print(f"\n{'=' * 20} TEST 3: Duplicate Contestant Test {'=' * 20}")
    success = simulate_opensession_command(
        data, "nfl_duplicate", "New England Patriots", "Buffalo Bills", 300
    )
    print(f"Result: {'SUCCESS' if success else 'FAILED'} (Should fail)")

    # Add some bets manually for testing
    print(f"\n{'=' * 20} Adding Test Bets {'=' * 20}")
    data["betting_sessions"]["nfl_patriots_cowboys"]["bets"]["user1"] = {
        "amount": 300,
        "choice": "new england patriots",
        "emoji": None,
    }
    data["betting_sessions"]["nfl_patriots_cowboys"]["bets"]["user2"] = {
        "amount": 200,
        "choice": "dallas cowboys",
        "emoji": None,
    }
    data["betting_sessions"]["nba_lakers_warriors"]["bets"]["user3"] = {
        "amount": 500,
        "choice": "los angeles lakers",
        "emoji": None,
    }
    # Update balances
    data["balances"]["user1"] -= 300
    data["balances"]["user2"] -= 200
    data["balances"]["user3"] -= 500
    print("✅ Added test bets")

    # Test 4: List sessions
    print(f"\n{'=' * 20} TEST 4: List Sessions {'=' * 20}")
    simulate_listsessions_command(data)

    # Test 5: Get session info
    print(f"\n{'=' * 20} TEST 5: Session Info {'=' * 20}")
    simulate_sessioninfo_command(data, "nfl_patriots_cowboys")

    # Test 6: Close session with winner
    print(f"\n{'=' * 20} TEST 6: Close Session with Winner {'=' * 20}")
    success = simulate_closesession_command(
        data, "nfl_patriots_cowboys", "New England Patriots"
    )
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")

    # Test 7: List sessions after closure
    print(f"\n{'=' * 20} TEST 7: List Sessions After Closure {'=' * 20}")
    simulate_listsessions_command(data)

    # Test 8: Try to get info on closed session
    print(f"\n{'=' * 20} TEST 8: Info on Closed Session {'=' * 20}")
    simulate_sessioninfo_command(data, "nfl_patriots_cowboys")

    # Show final state
    print(f"\n{'=' * 20} FINAL STATE {'=' * 20}")
    print(f"Final balances: {data['balances']}")
    print(f"Active sessions: {data.get('active_sessions', [])}")

    closed_sessions = []
    for session_id, session in data.get("betting_sessions", {}).items():
        if session.get("status") == "closed":
            winner = session.get("winner", "None")
            closed_sessions.append(f"{session_id} (winner: {winner})")

    print(f"Closed sessions: {closed_sessions}")


if __name__ == "__main__":
    main()
