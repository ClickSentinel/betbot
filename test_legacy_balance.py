#!/usr/bin/env python3#!/usr/bin/env python3

""""""

Quick test to verify legacy balance updating works after the fix.Test the legacy balance update fix for the !cb command.

""""""



import sysimport sys

import osimport os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))sys.path.append(os.path.dirname(os.path.abspath(__file__)))



from utils.bet_state import BetStatefrom utils.bet_state import BetState

from data_manager import load_data, save_data, Datafrom data_manager import load_data, save_data, Data

from typing import castfrom typing import cast

import tempfileimport shutil

import shutil

def test_legacy_balance_updates():

def test_legacy_balance_updates():    """Test that balances are updated correctly in legacy mode after !cb command."""

    """Test that balances are updated correctly in legacy mode."""    

        # Backup original data

    # Create a temporary data file for testing    original_data_file = "data.json"

    original_data_file = "data.json"    backup_data_file = "data_backup_legacy_test.json"

    backup_data_file = "data_backup_legacy_test.json"    

        if os.path.exists(original_data_file):

    # Backup original data        shutil.copy(original_data_file, backup_data_file)

    if os.path.exists(original_data_file):    

        shutil.copy(original_data_file, backup_data_file)    try:

            # Create test data in legacy format (multi_session_mode = false)

    try:        test_data = {

        # Create test data with legacy format (no multi-session fields)            "balances": {"user1": 1000, "user2": 1000, "user3": 1000},

        test_data = {            "betting": {

            "balances": {"user1": 1000, "user2": 1000},                "open": True,

            "betting": {                "locked": False,

                "open": False,                "contestants": {"1": "Team A", "2": "Team B"},

                "locked": True,  # Must be locked to declare winner                "bets": {

                "contestants": {"1": "Alice", "2": "Bob"},                    "user1": {"amount": 200, "choice": "team a", "emoji": None},

                "bets": {                    "user2": {"amount": 300, "choice": "team b", "emoji": None},

                    "user1": {"amount": 300, "choice": "alice", "emoji": None},                    "user3": {"amount": 150, "choice": "team a", "emoji": None}

                    "user2": {"amount": 200, "choice": "bob", "emoji": None}                }

                }            },

            },            "settings": {"enable_bet_timer": True},

            "settings": {},            "reaction_bet_amounts": {},

            "reaction_bet_amounts": {},            "contestant_1_emojis": [],

            "contestant_1_emojis": [],            "contestant_2_emojis": [],

            "contestant_2_emojis": [],            "live_message": None,

            "live_message": None            "betting_sessions": {},

        }            "active_sessions": [],

                    "contestant_to_session": {},

        # Save test data            "multi_session_mode": False  # Legacy mode

        save_data(cast(Data, test_data))        }

                

        print("🧪 Testing Legacy Balance Updates")        # Save test data

        print("=" * 40)        save_data(cast(Data, test_data))

                

        # Load data and create BetState        print("🧪 Testing Legacy Balance Updates After !cb Command")

        data = load_data()        print("=" * 55)

        print(f"Initial balances: {data['balances']}")        

        print(f"Bets: {data['betting']['bets']}")        # Simulate what happens when user places bets (balances should be deducted)

                data = load_data()

        # Create fresh BetState and declare Alice as winner        

        bet_state = BetState(data)        # Check initial state - simulate that bets were already placed and balances deducted

        print("\n🏆 Declaring Alice as winner...")        print(f"Initial balances: {data['balances']}")

        winner_info = bet_state.declare_winner("Alice")        print(f"Bets: {data['betting']['bets']}")

                

        # Check final balances        # Simulate the balance deduction that happens when bets are placed

        final_data = load_data()        data["balances"]["user1"] -= 200  # user1 bet 200

        print(f"\nFinal balances: {final_data['balances']}")        data["balances"]["user2"] -= 300  # user2 bet 300  

                data["balances"]["user3"] -= 150  # user3 bet 150

        # Expected results:        save_data(data)

        # Total pot: 300 + 200 = 500        

        # Alice bets: 300 (user1)        data = load_data()

        # user1 should get all 500 coins (their 300 bet was already deducted)        print(f"\nBalances after betting: {data['balances']}")

        # user2 loses their 200 bet (stays at 800)        print("Expected: user1=800, user2=700, user3=850")

                

        expected_user1 = 1000 - 300 + 500  # Initial - bet + total_pot = 1200        # Now simulate the !cb command logic with Team A winning

        expected_user2 = 1000 - 200 + 0    # Initial - bet + nothing = 800        print(f"\n🏆 Simulating !cb Team A (winner declaration)...")

                

        print(f"\nExpected: user1={expected_user1}, user2={expected_user2}")        # This simulates what _process_winner_declaration does

        print(f"Actual:   user1={final_data['balances']['user1']}, user2={final_data['balances']['user2']}")        bet_state = BetState(data)  # Create fresh BetState with current data

                winner_info = bet_state.declare_winner("Team A")

        # Verify totals        

        initial_total = 1000 + 1000  # 2000        # Check final balances

        final_total = sum(final_data['balances'].values())        final_data = load_data()

        print(f"\nTotal coins - Initial: {initial_total}, Final: {final_total}")        print(f"\nFinal balances: {final_data['balances']}")

        print(f"Difference: {final_total - initial_total} (should be 0)")        

                # Calculate expected results

        if final_total == initial_total:        total_pot = 200 + 300 + 150  # 650

            print("✅ Legacy economy is balanced!")        winning_pot = 200 + 150      # 350 (Team A bets)

        else:        

            print("❌ Legacy economy is NOT balanced!")        # user1: (200/350) * 650 = ~371 coins total -> should have 800 + 371 = 1171

                    # user3: (150/350) * 650 = ~279 coins total -> should have 850 + 279 = 1129

        if (final_data['balances']['user1'] == expected_user1 and         # user2: loses 300 coins -> should stay at 700

            final_data['balances']['user2'] == expected_user2):        

            print("✅ Balances updated correctly!")        expected_user1 = 800 + int((200/350) * 650)  # 800 + 371 = 1171

        else:        expected_user3 = 850 + int((150/350) * 650)  # 850 + 279 = 1129

            print("❌ Balances NOT updated correctly!")        expected_user2 = 700  # Lost bet, no change

                    

        print(f"\n📊 Winner info: {winner_info}")        print(f"\nExpected final balances:")

                print(f"user1: {expected_user1} (bet 200, won {int((200/350) * 650)})")

    finally:        print(f"user2: {expected_user2} (bet 300, lost)")

        # Restore original data        print(f"user3: {expected_user3} (bet 150, won {int((150/350) * 650)})")

        if os.path.exists(backup_data_file):        

            shutil.move(backup_data_file, original_data_file)        # Verify totals

        print(f"\n🔄 Original data restored")        initial_total = 1000 + 1000 + 1000  # 3000

        final_total = sum(final_data['balances'].values())

if __name__ == "__main__":        print(f"\nTotal coins - Initial: {initial_total}, Final: {final_total}")

    test_legacy_balance_updates()        print(f"Difference: {final_total - initial_total} (should be 0)")
        
        success = True
        if abs(final_data['balances']['user1'] - expected_user1) <= 1:  # Allow 1 coin rounding
            print("✅ user1 balance correct")
        else:
            print(f"❌ user1 balance wrong: got {final_data['balances']['user1']}, expected {expected_user1}")
            success = False
            
        if final_data['balances']['user2'] == expected_user2:
            print("✅ user2 balance correct")
        else:
            print(f"❌ user2 balance wrong: got {final_data['balances']['user2']}, expected {expected_user2}")
            success = False
            
        if abs(final_data['balances']['user3'] - expected_user3) <= 1:  # Allow 1 coin rounding
            print("✅ user3 balance correct")
        else:
            print(f"❌ user3 balance wrong: got {final_data['balances']['user3']}, expected {expected_user3}")
            success = False
        
        if abs(final_total - initial_total) <= 1:  # Allow 1 coin rounding
            print("✅ Economy is balanced!")
        else:
            print("❌ Economy is NOT balanced!")
            success = False
            
        if success:
            print("\n🎉 ALL TESTS PASSED - Legacy balance update is working!")
        else:
            print("\n💥 TESTS FAILED - Legacy balance update needs more work!")
            
        print(f"\n📊 Winner info: {winner_info}")
        
    finally:
        # Restore original data
        if os.path.exists(backup_data_file):
            shutil.move(backup_data_file, original_data_file)
        print(f"\n🔄 Original data restored")

if __name__ == "__main__":
    test_legacy_balance_updates()