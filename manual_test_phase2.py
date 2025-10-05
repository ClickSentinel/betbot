"""
Manual test script for Phase 2 multi-session betting integration.
This simulates the betting command workflow.
"""

import json
import tempfile
import os
from data_manager import load_data, save_data, is_multi_session_mode, find_session_by_contestant


def setup_multi_session_test():
    """Set up test environment with multi-session data."""
    test_data = {
        "balances": {
            "123456": 1000,
            "789012": 1500,
        },
        "betting": {
            "open": False,
            "locked": False,
            "bets": {},
            "contestants": {}
        },
        "settings": {
            "enable_bet_timer": True,
            "bet_channel_id": None
        },
        # Multi-session fields
        "betting_sessions": {
            "nfl_patriots_cowboys": {
                "status": "open",
                "contestants": {
                    "team1": "New England Patriots",
                    "team2": "Dallas Cowboys"
                },
                "bets": {},
                "timer_config": {
                    "enabled": True,
                    "duration": 300
                }
            },
            "nba_lakers_warriors": {
                "status": "open", 
                "contestants": {
                    "team1": "Los Angeles Lakers",
                    "team2": "Golden State Warriors"
                },
                "bets": {},
                "timer_config": {
                    "enabled": True,
                    "duration": 600
                }
            }
        },
        "active_sessions": ["nfl_patriots_cowboys", "nba_lakers_warriors"],
        "contestant_to_session": {
            "new england patriots": "nfl_patriots_cowboys",
            "dallas cowboys": "nfl_patriots_cowboys",
            "los angeles lakers": "nba_lakers_warriors",
            "golden state warriors": "nba_lakers_warriors"
        },
        "multi_session_mode": True
    }
    
    return test_data


def simulate_bet_command(data, user_id, amount, contestant_choice):
    """Simulate the betting command workflow."""
    print(f"\n🎯 User {user_id} wants to bet {amount} on '{contestant_choice}'")
    
    # Step 1: Check if multi-session mode
    if not is_multi_session_mode(data):
        print("❌ Not in multi-session mode")
        return False
    
    print("✅ Multi-session mode detected")
    
    # Step 2: Check if any sessions are open
    active_sessions = data.get("active_sessions", [])
    has_open_session = False
    
    for session_id in active_sessions:
        session = data["betting_sessions"].get(session_id, {})
        if session.get("status") == "open":
            has_open_session = True
            break
    
    if not has_open_session:
        print("❌ No open betting sessions")
        return False
    
    print(f"✅ Found {len([s for s in active_sessions if data['betting_sessions'][s].get('status') == 'open'])} open sessions")
    
    # Step 3: Find contestant and session
    session_result = find_session_by_contestant(contestant_choice, data)
    if not session_result:
        print(f"❌ Contestant '{contestant_choice}' not found in any session")
        # Show available contestants
        print("Available contestants:")
        for session_id in active_sessions:
            session = data["betting_sessions"].get(session_id, {})
            if session.get("status") == "open":
                contestants = session.get("contestants", {})
                print(f"  Session {session_id}: {', '.join(contestants.values())}")
        return False
    
    session_id, contestant_key, contestant_name = session_result
    print(f"✅ Found '{contestant_name}' in session '{session_id}'")
    
    # Step 4: Check session status
    session = data["betting_sessions"][session_id]
    if session.get("status") != "open":
        print(f"❌ Session {session_id} is not open (status: {session.get('status')})")
        return False
    
    print(f"✅ Session {session_id} is open for betting")
    
    # Step 5: Check user balance
    user_balance = data["balances"].get(user_id, 0)
    existing_bet = session["bets"].get(user_id, {})
    old_amount = existing_bet.get("amount", 0)
    required_additional = amount - old_amount
    
    print(f"💰 User balance: {user_balance}, Old bet: {old_amount}, Additional needed: {required_additional}")
    
    if required_additional > user_balance:
        print(f"❌ Insufficient funds (need {required_additional}, have {user_balance})")
        return False
    
    print("✅ User has sufficient funds")
    
    # Step 6: Place the bet
    data["balances"][user_id] -= required_additional
    session["bets"][user_id] = {
        "amount": amount,
        "choice": contestant_name.lower(),
        "emoji": None
    }
    
    # Update contestant mapping
    data["contestant_to_session"][contestant_name.lower()] = session_id
    
    print(f"✅ Bet placed successfully!")
    print(f"   - Amount: {amount} coins")
    print(f"   - Contestant: {contestant_name}")
    print(f"   - Session: {session_id}")
    print(f"   - New balance: {data['balances'][user_id]}")
    
    return True


def main():
    """Run the manual test."""
    print("🧪 Manual Test: Multi-Session Betting Integration")
    print("=" * 50)
    
    # Setup test data
    data = setup_multi_session_test()
    
    # Show initial state
    print(f"Initial balances: {data['balances']}")
    print(f"Active sessions: {data['active_sessions']}")
    print("Available contestants:")
    for session_id in data['active_sessions']:
        session = data['betting_sessions'][session_id]
        contestants = session['contestants']
        print(f"  {session_id}: {', '.join(contestants.values())}")
    
    # Test 1: Bet on Patriots (NFL session)
    print(f"\n{'=' * 20} TEST 1 {'=' * 20}")
    success = simulate_bet_command(data, "123456", 200, "Patriots")
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")
    
    # Test 2: Bet on Lakers (NBA session) 
    print(f"\n{'=' * 20} TEST 2 {'=' * 20}")
    success = simulate_bet_command(data, "789012", 300, "Lakers")
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")
    
    # Test 3: Same user bets on different session
    print(f"\n{'=' * 20} TEST 3 {'=' * 20}")
    success = simulate_bet_command(data, "123456", 150, "Golden State Warriors")
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")
    
    # Test 4: Partial name matching
    print(f"\n{'=' * 20} TEST 4 {'=' * 20}")
    success = simulate_bet_command(data, "789012", 100, "Cow") # Should match Cowboys
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")
    
    # Test 5: Invalid contestant
    print(f"\n{'=' * 20} TEST 5 {'=' * 20}")
    success = simulate_bet_command(data, "123456", 50, "Nonexistent Team")
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")
    
    # Show final state
    print(f"\n{'=' * 20} FINAL STATE {'=' * 20}")
    print(f"Final balances: {data['balances']}")
    print("Final bets:")
    for session_id in data['active_sessions']:
        session = data['betting_sessions'][session_id]
        if session['bets']:
            print(f"  {session_id}:")
            for user_id, bet in session['bets'].items():
                print(f"    User {user_id}: {bet['amount']} coins on {bet['choice']}")
        else:
            print(f"  {session_id}: No bets")


if __name__ == "__main__":
    main()