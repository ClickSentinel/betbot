import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from betbot.utils.bet_state import BetState, Economy
from betbot.utils.bet_state import BetInfo, WinnerInfo

class TestBetState:
    @pytest.fixture
    def bet_state(self, test_data):
        """Creates a BetState instance with test data."""
        return BetState(test_data)

    def test_place_bet_success(self, bet_state, test_data):
        """Test successful bet placement."""
        # Setup
        user_id = "123456789"
        amount = 100
        choice = "Alice"
        test_data["betting"]["open"] = True
        test_data["betting"]["contestants"] = {"1": "Alice", "2": "Bob"}
        test_data["balances"][user_id] = 1000

        # Execute
        result = bet_state.place_bet(user_id, amount, choice)

        # Assert
        assert result is True
        assert test_data["betting"]["bets"][user_id]["amount"] == amount
        assert test_data["betting"]["bets"][user_id]["choice"] == choice.lower()
        assert test_data["balances"][user_id] == 900

    def test_place_bet_insufficient_funds(self, bet_state, test_data):
        """Test bet placement with insufficient funds."""
        # Setup
        user_id = "123456789"
        amount = 100
        choice = "Alice"
        test_data["betting"]["open"] = True
        test_data["betting"]["contestants"] = {"1": "Alice", "2": "Bob"}
        test_data["balances"][user_id] = 50  # Less than bet amount

        # Execute
        result = bet_state.place_bet(user_id, amount, choice)

        # Assert
        assert result is False
        assert user_id not in test_data["betting"]["bets"]  # Changed assertion here
        assert test_data["balances"][user_id] == 50  # Balance shouldn't change

    def test_declare_winner_single_winner(self, bet_state, test_data):
        """Test winner declaration with a single winner."""
        # Setup
        user_id = "123456789"
        test_data["betting"]["open"] = False
        test_data["betting"]["locked"] = True
        test_data["betting"]["contestants"] = {"1": "Alice", "2": "Bob"}
        test_data["betting"]["bets"] = {
            user_id: {"amount": 100, "choice": "alice", "emoji": None}
        }
        test_data["balances"][user_id] = 900

        # Execute
        winner_info = bet_state.declare_winner("Alice")

        # Assert
        assert winner_info["name"] == "Alice"
        assert winner_info["total_pot"] == 100
        assert winner_info["user_results"][user_id]["winnings"] == 100
        assert test_data["balances"][user_id] == 1000

    def test_declare_winner_multiple_winners(self, bet_state, test_data):
        """Test winner declaration with multiple winners."""
        # Setup
        users = ["123", "456"]
        test_data["betting"]["open"] = False
        test_data["betting"]["locked"] = True
        test_data["betting"]["contestants"] = {"1": "Alice", "2": "Bob"}
        test_data["betting"]["bets"] = {
            users[0]: {"amount": 100, "choice": "alice", "emoji": None},
            users[1]: {"amount": 100, "choice": "alice", "emoji": None}
        }
        test_data["balances"].update({users[0]: 900, users[1]: 900})

        # Execute
        winner_info = bet_state.declare_winner("Alice")

        # Assert
        assert winner_info["name"] == "Alice"
        assert winner_info["total_pot"] == 200
        for user_id in users:
            assert winner_info["user_results"][user_id]["winnings"] == 100
            assert test_data["balances"][user_id] == 1000

    def test_timer_management(self, bet_state, test_data):
        """Test timer start and clear operations."""
        # Setup
        test_data["settings"]["enable_bet_timer"] = True

        # Execute
        bet_state.start_timer()

        # Assert
        assert test_data["timer_end_time"] is not None

        # Execute clear
        bet_state.clear_timer()

        # Assert
        assert test_data["timer_end_time"] is None

class TestEconomy:
    @pytest.fixture
    def economy(self, test_data):
        """Creates an Economy instance with test data."""
        return Economy(test_data)

    def test_add_balance(self, economy, test_data):
        """Test adding balance to a user."""
        # Setup
        user_id = "123456789"
        test_data["balances"][user_id] = 1000

        # Execute
        result = economy.add_balance(user_id, 500)

        # Assert
        assert result is True
        assert test_data["balances"][user_id] == 1500

    def test_remove_balance_success(self, economy, test_data):
        """Test removing balance from a user."""
        # Setup
        user_id = "123456789"
        test_data["balances"][user_id] = 1000

        # Execute
        result = economy.remove_balance(user_id, 500)

        # Assert
        assert result is True
        assert test_data["balances"][user_id] == 500

    def test_remove_balance_insufficient(self, economy, test_data):
        """Test removing more balance than available."""
        # Setup
        user_id = "123456789"
        test_data["balances"][user_id] = 100

        # Execute
        result = economy.remove_balance(user_id, 500)

        # Assert
        assert result is False
        assert test_data["balances"][user_id] == 100