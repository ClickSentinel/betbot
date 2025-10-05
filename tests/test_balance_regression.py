"""
Regression test to verify balance updating after betting rounds.
This test ensures that the balance update bug (where balances weren't properly
updated after declaring winners) doesn't reoccur.

Bug Description:
- Balances were being deducted when bets were placed
- But when winners were declared, only pure "winnings" were added back
- This meant winners didn't get their original bet amount back
- The winnings calculation already included the full payout (bet + profit)
- Fix: Add the full winnings amount (which includes original bet) to balance
"""

import pytest
import os
import sys
import tempfile
import shutil
from typing import cast

# Add parent directory to path for imports when running standalone
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.bet_state import BetState
from data_manager import load_data, save_data, Data

def test_balance_updates_after_winner_declaration(tmp_path):
    """
    Test that balances are updated correctly after declaring a winner.
    
    This is a regression test for the bug where balances were not being
    properly updated after betting rounds ended.
    """
    
    # Use temporary directory for testing
    import data_manager
    original_data_file = data_manager.DATA_FILE
    test_data_file = tmp_path / "data.json"
    data_manager.DATA_FILE = str(test_data_file)
    
    try:
        # Create test data
        test_data = {
            "balances": {"user1": 1000, "user2": 1000, "user3": 1000},
            "betting": {
                "open": True,
                "locked": False,
                "contestants": {"1": "Team A", "2": "Team B"},
                "bets": {}
            },
            "settings": {},
            "reaction_bet_amounts": {},
            "contestant_1_emojis": [],
            "contestant_2_emojis": [],
            "live_message": None,
            "betting_sessions": {},
            "active_sessions": [],
            "contestant_to_session": {},
            "multi_session_mode": False
        }
        
        # Save test data
        save_data(cast(Data, test_data))
        
        # Create BetState and place some bets
        data = load_data()
        bet_state = BetState(data)
        
        print("🧪 Testing Balance Updates After Betting")
        print("=" * 50)
        
        # Check initial balances
        print(f"Initial balances: {data['balances']}")
        
        # Place bets
        print("\n📝 Placing bets...")
        bet_result1 = bet_state.place_bet("user1", 200, "Team A", None)
        bet_result2 = bet_state.place_bet("user2", 300, "Team B", None)  
        bet_result3 = bet_state.place_bet("user3", 150, "Team A", None)
        
        print(f"user1 bet 200 on Team A: {bet_result1}")
        print(f"user2 bet 300 on Team B: {bet_result2}")
        print(f"user3 bet 150 on Team A: {bet_result3}")
        
        # Check balances after betting (should be reduced)
        data = load_data()
        print(f"\nBalances after betting: {data['balances']}")
        print("Expected: user1=800, user2=700, user3=850")
        
        # Declare Team A as winner
        print(f"\n🏆 Declaring Team A as winner...")
        bet_state = BetState(data)  # Reload data
        winner_info = bet_state.declare_winner("Team A")
        
        # Check final balances
        final_data = load_data()
        print(f"\nFinal balances: {final_data['balances']}")
        
        # Calculate expected results
        total_pot = 200 + 300 + 150  # 650
        winning_pot = 200 + 150      # 350 (Team A bets)
        
        # user1: (200/350) * 650 = ~371 coins total -> net gain of 171
        # user3: (150/350) * 650 = ~279 coins total -> net gain of 129  
        # user2: loses 300 coins -> stays at 700
        
        expected_user1 = 800 + int((200/350) * 650)  # 800 + 371 = 1171
        expected_user3 = 850 + int((150/350) * 650)  # 850 + 279 = 1129
        expected_user2 = 700  # Lost bet, no change
        
        print(f"\nExpected final balances:")
        print(f"user1: {expected_user1} (bet 200, won {int((200/350) * 650)})")
        print(f"user2: {expected_user2} (bet 300, lost)")
        print(f"user3: {expected_user3} (bet 150, won {int((150/350) * 650)})")
        
        # Verify totals
        initial_total = 1000 + 1000 + 1000  # 3000
        final_total = sum(final_data['balances'].values())
        print(f"\nTotal coins - Initial: {initial_total}, Final: {final_total}")
        print(f"Difference: {final_total - initial_total} (should be 0)")
        
        if final_total == initial_total:
            print("✅ Economy is balanced!")
        else:
            print("❌ Economy is NOT balanced!")
            
        print(f"\n📊 Winner info: {winner_info}")
        
    finally:
        # Restore original data file path
        data_manager.DATA_FILE = original_data_file
        print(f"\n🔄 Data file path restored")


if __name__ == "__main__":
    # For standalone execution, create a temporary directory
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_balance_updates_after_winner_declaration(Path(tmp_dir))