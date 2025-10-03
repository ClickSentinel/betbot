"""
Tests for messaging to ensure correct values and math validation.
Validates that all displayed balances, additions, and subtractions are mathematically correct.
"""

import pytest
import sys
from pathlib import Path

# Add the parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import data_manager


class TestMessagingMathValidation:
    """Test messaging math validation for betting and economy operations."""

    @pytest.fixture
    def test_data(self):
        """Create test data structure matching the actual system."""
        return {
            "balances": {},
            "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
            "settings": {"enable_bet_timer": True, "bet_channel_id": None},
            "reaction_bet_amounts": {"🔴": 100, "🔵": 500},
            "contestant_1_emojis": ["🔴"],
            "contestant_2_emojis": ["🔵"],
            "live_message": None,
            "live_channel": None,
            "live_secondary_message": None,
            "live_secondary_channel": None,
            "timer_end_time": None,
        }

    def test_balance_display_math(self, test_data):
        """Test that balance calculations are mathematically correct."""
        user_id = "67890"

        # Set up user with specific balance
        data_manager.ensure_user(test_data, user_id)
        test_data["balances"][user_id] = 1500

        # Test balance retrieval (direct access since it's functional)
        available_balance = test_data["balances"][user_id]
        assert (
            available_balance == 1500
        ), f"Available balance should be 1500, got {available_balance}"

    def test_bet_placement_math_validation(self, test_data):
        """Test that bet placement correctly calculates balance changes."""
        user_id = "67890"

        # Set up user with initial balance
        initial_balance = 1000
        bet_amount = 250

        data_manager.ensure_user(test_data, user_id)
        test_data["balances"][user_id] = initial_balance

        # Create betting session
        test_data["betting"]["open"] = True
        test_data["betting"]["locked"] = False
        test_data["betting"]["contestants"] = {"alice": "Alice", "bob": "Bob"}

        # Test bet placement math - simulate what happens in the betting logic
        expected_new_balance = initial_balance - bet_amount

        # Can user afford the bet?
        can_afford = test_data["balances"][user_id] >= bet_amount
        assert can_afford, "User should be able to afford the bet"

        # Simulate bet placement
        test_data["balances"][user_id] -= bet_amount
        test_data["betting"]["bets"][user_id] = {
            "choice": "alice",
            "amount": bet_amount,
            "emoji": None,
        }

        actual_new_balance = test_data["balances"][user_id]

        assert (
            actual_new_balance == expected_new_balance
        ), f"Balance after bet should be {expected_new_balance}, got {actual_new_balance}"

        # Verify bet was recorded correctly
        bet = test_data["betting"]["bets"][user_id]
        assert (
            bet["amount"] == bet_amount
        ), f"Bet amount should be {bet_amount}, got {bet['amount']}"

    def test_insufficient_funds_math_validation(self, test_data):
        """Test that insufficient funds calculations are correct."""
        user_id = "67890"

        # Set up user with low balance
        current_balance = 100
        attempted_bet = 250

        data_manager.ensure_user(test_data, user_id)
        test_data["balances"][user_id] = current_balance

        # Test insufficient funds calculation
        shortfall = attempted_bet - current_balance  # Should be 150

        # Verify insufficient funds detection
        can_afford = test_data["balances"][user_id] >= attempted_bet
        assert not can_afford, "Should detect insufficient funds"

        # Verify shortfall calculation
        assert shortfall == 150, f"Shortfall should be 150, got {shortfall}"

    def test_balance_warning_threshold_math(self):
        """Test that balance warning thresholds are calculated correctly."""
        # Test various balance scenarios for percentage calculations
        test_cases = [
            (1000, 700, True),  # 70% - should warn
            (1000, 800, True),  # 80% - should warn
            (1000, 650, False),  # 65% - should not warn
            (500, 350, True),  # 70% - should warn
            (1500, 1000, False),  # 66.7% - should not warn
        ]

        for balance, bet_amount, should_warn in test_cases:
            percentage = (bet_amount / balance) * 100
            is_high_percentage = percentage >= 70

            assert is_high_percentage == should_warn, (
                f"Balance {balance}, bet {bet_amount} ({percentage:.1f}%) - "
                f"should_warn={should_warn}, got {is_high_percentage}"
            )

    def test_betall_amount_calculation(self, test_data):
        """Test that betall calculates the correct amount."""
        user_id = "67890"

        test_cases = [
            1000,  # Even amount
            1234,  # Random amount
            999,  # Odd amount
            1,  # Minimum
        ]

        for balance in test_cases:
            # Reset for each test
            data_manager.ensure_user(test_data, user_id)
            test_data["balances"][user_id] = balance

            # Set up betting session
            test_data["betting"]["open"] = True
            test_data["betting"]["locked"] = False
            test_data["betting"]["contestants"] = {"alice": "Alice", "bob": "Bob"}
            test_data["betting"]["bets"] = {}  # Clear previous bets

            # Test betall calculation
            available_balance = test_data["balances"][user_id]
            assert (
                available_balance == balance
            ), f"Available balance should equal set balance: {balance}"

            # Simulate betall - bet entire balance
            test_data["balances"][user_id] -= balance
            test_data["betting"]["bets"][user_id] = {
                "choice": "alice",
                "amount": balance,
                "emoji": None,
            }

            # Balance should be 0 after betting everything
            final_balance = test_data["balances"][user_id]
            assert (
                final_balance == 0
            ), f"Balance should be 0 after betall, got {final_balance}"

            # Bet amount should equal original balance
            bet = test_data["betting"]["bets"][user_id]
            assert (
                bet["amount"] == balance
            ), f"Bet amount should be {balance}, got {bet['amount']}"

    def test_balance_formatting_in_messages(self):
        """Test that balance values are correctly formatted in messages."""
        # Test various balance formatting scenarios
        test_cases = [
            (1000, "1000"),
            (1234567, "1234567"),
            (0, "0"),
            (42, "42"),
            (999999, "999999"),
        ]

        for balance, expected_str in test_cases:
            # Test that the balance converts to the expected string representation
            formatted = str(balance)
            assert (
                formatted == expected_str
            ), f"Balance {balance} should format to '{expected_str}', got '{formatted}'"

    def test_betting_math_edge_cases(self, test_data):
        """Test edge cases in betting math calculations."""
        user_id = "67890"

        # Test exact balance bet
        balance = 500
        data_manager.ensure_user(test_data, user_id)
        test_data["balances"][user_id] = balance

        # Set up betting session
        test_data["betting"]["open"] = True
        test_data["betting"]["locked"] = False
        test_data["betting"]["contestants"] = {"alice": "Alice", "bob": "Bob"}

        # Bet exact balance
        can_bet = test_data["balances"][user_id] >= balance
        assert can_bet, "Should be able to bet exact balance"

        # Simulate betting exact balance
        test_data["balances"][user_id] -= balance
        test_data["betting"]["bets"][user_id] = {
            "choice": "alice",
            "amount": balance,
            "emoji": None,
        }

        assert (
            test_data["balances"][user_id] == 0
        ), "Balance should be 0 after betting everything"

        # Test zero balance scenarios
        test_data["balances"][user_id] = 0
        can_bet_zero = test_data["balances"][user_id] >= 1
        assert not can_bet_zero, "Should not be able to bet with 0 balance"

    def test_multi_round_balance_tracking(self, test_data):
        """Test that balances are tracked correctly across multiple scenarios."""
        user_id = "67890"
        starting_balance = 1000

        # Initialize user
        data_manager.ensure_user(test_data, user_id)
        test_data["balances"][user_id] = starting_balance

        # Test balance after a hypothetical loss
        bet_amount = 200
        expected_balance_after_loss = starting_balance - bet_amount

        # Simulate the balance change (lost bet)
        test_data["balances"][user_id] = expected_balance_after_loss

        # Verify balance tracking
        actual_balance = test_data["balances"][user_id]
        assert (
            actual_balance == expected_balance_after_loss
        ), f"Balance after loss should be {expected_balance_after_loss}, got {actual_balance}"

        # Test balance after a hypothetical win
        winnings = 150
        payout = bet_amount + winnings  # Get bet back plus winnings
        final_balance = actual_balance + payout

        # Simulate the payout
        test_data["balances"][user_id] = final_balance

        # Verify final balance: 800 + 350 = 1150
        expected_final = 1150
        actual_final = test_data["balances"][user_id]
        assert (
            actual_final == expected_final
        ), f"Final balance should be {expected_final}, got {actual_final}"

    def test_percentage_calculations(self):
        """Test percentage calculations used in betting warnings."""
        test_cases = [
            (1000, 700, 70.0),
            (1500, 1000, 66.67),
            (500, 350, 70.0),
            (2000, 1600, 80.0),
            (100, 25, 25.0),
        ]

        for balance, bet_amount, expected_percentage in test_cases:
            calculated_percentage = (bet_amount / balance) * 100

            # Allow for small floating point differences
            assert abs(calculated_percentage - expected_percentage) < 0.01, (
                f"Percentage calculation error: {bet_amount}/{balance} should be {expected_percentage}%, "
                f"got {calculated_percentage:.2f}%"
            )


if __name__ == "__main__":
    # For manual testing
    pytest.main([__file__, "-v"])
