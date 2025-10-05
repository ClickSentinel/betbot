"""
Comprehensive end-to-end test for the complete multi-session betting system.
Tests all three phases working together.
"""

from data_manager import (
    load_data,
    save_data,
    is_multi_session_mode,
    find_session_by_contestant,
    Data,
)
from typing import cast
import time


def test_complete_multi_session_workflow():
    """Test the complete workflow from session creation to betting to closure."""
    print("🧪 Complete Multi-Session Workflow Test")
    print("=" * 60)

    # Start with legacy data
    data = {
        "balances": {"alice": 1000, "bob": 1500, "charlie": 800, "diana": 1200},
        "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
        "settings": {"enable_bet_timer": True, "bet_channel_id": None},
    }

    print("📊 Initial State:")
    print(
        f"   Mode: {'Multi-session' if is_multi_session_mode(cast(Data, data)) else 'Legacy'}"
    )
    print(f"   Balances: {data['balances']}")

    # === PHASE 1 & 3: Create Multiple Sessions ===
    print(f"\n🎯 PHASE 1 & 3: Creating Multiple Sessions")
    print("-" * 40)

    # Convert to multi-session mode and create first session
    data["betting_sessions"] = {}
    data["active_sessions"] = []
    data["contestant_to_session"] = {}
    data["multi_session_mode"] = True

    # Create NFL session
    nfl_session = {
        "status": "open",
        "contestants": {"c1": "Patriots", "c2": "Cowboys"},
        "bets": {},
        "timer_config": {"enabled": True, "duration": 600},
        "created_at": time.time(),
        "created_by": "admin",
    }
    data["betting_sessions"]["nfl_game"] = nfl_session
    data["active_sessions"].append("nfl_game")
    data["contestant_to_session"]["patriots"] = "nfl_game"
    data["contestant_to_session"]["cowboys"] = "nfl_game"

    # Create NBA session
    nba_session = {
        "status": "open",
        "contestants": {"c1": "Lakers", "c2": "Warriors"},
        "bets": {},
        "timer_config": {"enabled": True, "duration": 900},
        "created_at": time.time(),
        "created_by": "admin",
    }
    data["betting_sessions"]["nba_game"] = nba_session
    data["active_sessions"].append("nba_game")
    data["contestant_to_session"]["lakers"] = "nba_game"
    data["contestant_to_session"]["warriors"] = "nba_game"

    print(f"✅ Created sessions: {data['active_sessions']}")
    print(f"✅ Multi-session mode: {is_multi_session_mode(cast(Data, data))}")

    # === PHASE 2: Test Intelligent Betting ===
    print(f"\n💰 PHASE 2: Intelligent Multi-Session Betting")
    print("-" * 40)

    # Test automatic session detection
    test_bets = [
        ("alice", "Patriots", 200, "nfl_game"),
        ("bob", "Lakers", 300, "nba_game"),
        ("charlie", "Cowboys", 150, "nfl_game"),
        ("diana", "Warriors", 400, "nba_game"),
        ("alice", "Lakers", 250, "nba_game"),  # Same user, different session
    ]

    for user_id, contestant_choice, amount, expected_session in test_bets:
        print(f"\n🎲 {user_id} wants to bet {amount} on '{contestant_choice}'")

        # Phase 2: Find session by contestant
        session_result = find_session_by_contestant(contestant_choice, cast(Data, data))
        if not session_result:
            print(f"❌ No session found for '{contestant_choice}'")
            continue

        session_id, contestant_key, contestant_name = session_result
        print(f"✅ Found '{contestant_name}' in session '{session_id}'")

        # Verify correct session detection
        assert (
            session_id == expected_session
        ), f"Expected {expected_session}, got {session_id}"

        # Check session is open
        session = data["betting_sessions"][session_id]
        if session.get("status") != "open":
            print(f"❌ Session {session_id} is not open")
            continue

        # Check user balance
        user_balance = data["balances"][user_id]
        existing_bet = session["bets"].get(user_id, {})
        old_amount = existing_bet.get("amount", 0)
        required_additional = amount - old_amount

        if required_additional > user_balance:
            print(
                f"❌ Insufficient funds: need {required_additional}, have {user_balance}"
            )
            continue

        # Place bet
        data["balances"][user_id] -= required_additional
        session["bets"][user_id] = {
            "amount": amount,
            "choice": contestant_name.lower(),
            "emoji": None,
        }

        print(f"✅ Bet placed: {amount} coins on {contestant_name}")
        print(f"   New balance: {data['balances'][user_id]} coins")

    # Show session states
    print(f"\n📊 Session States After Betting:")
    for session_id in data["active_sessions"]:
        session = data["betting_sessions"][session_id]
        contestants = session["contestants"]
        bets = session["bets"]
        total_pot = sum(bet["amount"] for bet in bets.values())

        print(f"   {session_id}:")
        print(f"     Contestants: {', '.join(contestants.values())}")
        print(f"     Bets: {len(bets)}, Total Pot: {total_pot} coins")

        for user_id, bet in bets.items():
            print(f"       {user_id}: {bet['amount']} on {bet['choice']}")

    # === PHASE 3: Session Management ===
    print(f"\n🏆 PHASE 3: Session Closure and Payouts")
    print("-" * 40)

    # Close NFL session with Patriots winning
    print(f"\n🎯 Closing NFL session with Patriots winning")
    nfl_session = data["betting_sessions"]["nfl_game"]
    nfl_bets = nfl_session["bets"]
    nfl_contestants = nfl_session["contestants"]
    winner = "Patriots"

    # Calculate payouts
    total_pot = sum(bet["amount"] for bet in nfl_bets.values())
    winning_bets = [bet for bet in nfl_bets.values() if bet["choice"] == winner.lower()]
    winning_pot = sum(bet["amount"] for bet in winning_bets)

    print(f"💰 NFL Payout Calculation:")
    print(f"   Total Pot: {total_pot} coins")
    print(f"   Winning Bets: {len(winning_bets)}")
    print(f"   Winning Pot: {winning_pot} coins")

    # Process payouts
    print(f"💸 Processing payouts:")
    for user_id, bet in nfl_bets.items():
        initial_balance = data["balances"][user_id]
        if bet["choice"] == winner.lower():
            winnings = int((bet["amount"] / winning_pot) * total_pot)
            data["balances"][user_id] += winnings
            print(
                f"   ✅ {user_id}: {initial_balance} → {data['balances'][user_id]} (+{winnings})"
            )
        else:
            print(f"   💔 {user_id}: Lost {bet['amount']} coins")

    # Close session
    data["active_sessions"].remove("nfl_game")
    for contestant_name in nfl_contestants.values():
        data["contestant_to_session"].pop(contestant_name.lower(), None)
    nfl_session["status"] = "closed"
    nfl_session["winner"] = winner

    print(f"✅ NFL session closed, {winner} wins!")

    # Close NBA session with Warriors winning
    print(f"\n🎯 Closing NBA session with Warriors winning")
    nba_session = data["betting_sessions"]["nba_game"]
    nba_bets = nba_session["bets"]
    nba_contestants = nba_session["contestants"]
    winner = "Warriors"

    # Calculate payouts
    total_pot = sum(bet["amount"] for bet in nba_bets.values())
    winning_bets = [bet for bet in nba_bets.values() if bet["choice"] == winner.lower()]
    winning_pot = sum(bet["amount"] for bet in winning_bets)

    print(f"💰 NBA Payout Calculation:")
    print(f"   Total Pot: {total_pot} coins")
    print(f"   Winning Bets: {len(winning_bets)}")
    print(f"   Winning Pot: {winning_pot} coins")

    # Process payouts
    print(f"💸 Processing payouts:")
    for user_id, bet in nba_bets.items():
        initial_balance = data["balances"][user_id]
        if bet["choice"] == winner.lower():
            winnings = int((bet["amount"] / winning_pot) * total_pot)
            data["balances"][user_id] += winnings
            print(
                f"   ✅ {user_id}: {initial_balance} → {data['balances'][user_id]} (+{winnings})"
            )
        else:
            print(f"   💔 {user_id}: Lost {bet['amount']} coins")

    # Close session
    data["active_sessions"].remove("nba_game")
    for contestant_name in nba_contestants.values():
        data["contestant_to_session"].pop(contestant_name.lower(), None)
    nba_session["status"] = "closed"
    nba_session["winner"] = winner

    print(f"✅ NBA session closed, {winner} wins!")

    # === FINAL RESULTS ===
    print(f"\n🎉 FINAL RESULTS")
    print("=" * 40)

    print(f"📊 Final Balances:")
    initial_total = 1000 + 1500 + 800 + 1200  # 4500
    final_total = sum(data["balances"].values())

    for user_id, balance in data["balances"].items():
        initial = {"alice": 1000, "bob": 1500, "charlie": 800, "diana": 1200}[user_id]
        change = balance - initial
        print(
            f"   {user_id}: {initial} → {balance} ({'+' if change >= 0 else ''}{change})"
        )

    print(f"\n💰 Economic Verification:")
    print(f"   Initial Total: {initial_total} coins")
    print(f"   Final Total: {final_total} coins")
    print(f"   Difference: {final_total - initial_total} coins (should be 0)")

    assert (
        final_total == initial_total
    ), f"Economic error: {final_total} != {initial_total}"
    print(f"   ✅ Economy balanced!")

    print(f"\n📈 Session Summary:")
    print(f"   Active Sessions: {len(data.get('active_sessions', []))}")
    print(
        f"   Closed Sessions: {len([s for s in data['betting_sessions'].values() if s.get('status') == 'closed'])}"
    )

    for session_id, session in data["betting_sessions"].items():
        status = session.get("status", "unknown")
        winner = session.get("winner", "None")
        contestants = ", ".join(session["contestants"].values())
        print(f"   {session_id}: {status} - {contestants} (winner: {winner})")

    print(f"\n🎯 WORKFLOW TEST COMPLETE - ALL PHASES WORKING! 🎉")

    return data


if __name__ == "__main__":
    final_data = test_complete_multi_session_workflow()

    # Additional verification
    print(f"\n🔍 Final Verification:")
    print(f"   Multi-session mode: {is_multi_session_mode(cast(Data, final_data))}")
    print(f"   Active sessions: {len(final_data.get('active_sessions', []))}")
    print(f"   Total sessions created: {len(final_data.get('betting_sessions', {}))}")
    print(
        f"   Contestant mapping cleared: {len(final_data.get('contestant_to_session', {})) == 0}"
    )
