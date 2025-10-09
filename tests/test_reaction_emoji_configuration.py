"""
Test to ensure reaction emojis are correctly configured and added to messages.
This test validates that the emoji configuration matches expectations and that
reactions are added properly to live messages.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from config import (
    C1_EMOJIS,
    C2_EMOJIS,
    SEPARATOR_EMOJI,
    CONTESTANT_EMOJIS,
    REACTION_BET_AMOUNTS
)
from data_manager import Data


class TestReactionEmojiConfiguration:
    """Test suite for reaction emoji configuration and validation."""

    def test_contestant_emoji_constants_are_correct(self):
        """Test that the emoji constants are properly defined."""
        # Contestant 1 emojis (Power/Victory theme)
        expected_c1 = ["🔥", "⚡", "💪", "🏆"]
        assert C1_EMOJIS == expected_c1, f"C1_EMOJIS should be {expected_c1}, got {C1_EMOJIS}"

        # Contestant 2 emojis (Excellence/Royalty theme)
        expected_c2 = ["🌟", "💎", "🚀", "👑"]
        assert C2_EMOJIS == expected_c2, f"C2_EMOJIS should be {expected_c2}, got {C2_EMOJIS}"

        # Main contestant display emojis
        expected_main = ["🔴", "🔵"]
        assert CONTESTANT_EMOJIS == expected_main, f"CONTESTANT_EMOJIS should be {expected_main}, got {CONTESTANT_EMOJIS}"

        # Separator emoji
        assert SEPARATOR_EMOJI == "➖", f"SEPARATOR_EMOJI should be '➖', got '{SEPARATOR_EMOJI}'"

    def test_reaction_bet_amounts_mapping(self):
        """Test that reaction bet amounts are correctly mapped to emojis."""
        expected_amounts = {
            "🔥": 100,   # C1 - 100 coins
            "⚡": 250,   # C1 - 250 coins
            "💪": 500,   # C1 - 500 coins
            "🏆": 1000,  # C1 - 1000 coins
            "🌟": 100,   # C2 - 100 coins
            "💎": 250,   # C2 - 250 coins
            "🚀": 500,   # C2 - 500 coins
            "👑": 1000,  # C2 - 1000 coins
        }

        assert REACTION_BET_AMOUNTS == expected_amounts, f"REACTION_BET_AMOUNTS mismatch: {REACTION_BET_AMOUNTS}"

        # Ensure all betting emojis have amounts
        all_betting_emojis = C1_EMOJIS + C2_EMOJIS
        for emoji in all_betting_emojis:
            assert emoji in REACTION_BET_AMOUNTS, f"Emoji {emoji} missing from REACTION_BET_AMOUNTS"
            assert REACTION_BET_AMOUNTS[emoji] > 0, f"Emoji {emoji} has invalid amount: {REACTION_BET_AMOUNTS[emoji]}"

    def test_emoji_configuration_consistency(self):
        """Test that emoji configuration is internally consistent."""
        # All betting emojis should be unique
        all_betting_emojis = C1_EMOJIS + C2_EMOJIS
        assert len(all_betting_emojis) == len(set(all_betting_emojis)), "Betting emojis are not unique"

        # No overlap between contestant emoji sets
        assert set(C1_EMOJIS).isdisjoint(set(C2_EMOJIS)), "Contestant emoji sets overlap"

        # Separator should not be in betting emojis
        assert SEPARATOR_EMOJI not in all_betting_emojis, "Separator emoji conflicts with betting emojis"

        # Main contestant emojis should not be in betting emojis
        assert set(CONTESTANT_EMOJIS).isdisjoint(set(all_betting_emojis)), "Main contestant emojis conflict with betting emojis"

    @pytest.mark.asyncio
    async def test_reaction_adding_order(self):
        """Test that reactions are added in the correct order with separator."""
        from cogs.reaction_handler import ReactionHandler

        # Mock bot and cog
        mock_bot = MagicMock()
        cog = ReactionHandler(mock_bot)

        # Mock message
        mock_message = AsyncMock()
        mock_message.add_reaction = AsyncMock()

        # Test data with proper emoji configuration
        test_data: Data = {
            "contestant_1_emojis": C1_EMOJIS,
            "contestant_2_emojis": C2_EMOJIS,
            "reaction_bet_amounts": REACTION_BET_AMOUNTS,
            "balances": {},
            "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
            "settings": {"enable_bet_timer": False},
            "live_message": None,
            "live_channel": None,
            "live_secondary_message": None,
            "live_secondary_channel": None,
            "timer_end_time": None,
            "betting_sessions": {},
            "active_sessions": [],
            "contestant_to_session": {},
            "multi_session_mode": False,
        }

        # Call the method
        cog._add_reactions_background(mock_message, test_data)

        # Give it a moment to execute
        await asyncio.sleep(0.1)

        # Verify the call order
        expected_calls = []
        for emoji in C1_EMOJIS:
            expected_calls.append(((emoji,), {}))
        expected_calls.append(((SEPARATOR_EMOJI,), {}))
        for emoji in C2_EMOJIS:
            expected_calls.append(((emoji,), {}))

        assert mock_message.add_reaction.call_count == len(expected_calls)

        # Verify each call in order
        for i, (args, kwargs) in enumerate(expected_calls):
            call = mock_message.add_reaction.call_args_list[i]
            assert call[0] == args, f"Call {i}: expected {args}, got {call[0]}"
            assert call[1] == kwargs, f"Call {i}: expected kwargs {kwargs}, got {call[1]}"

    def test_data_initialization_includes_emojis(self):
        """Test that data initialization properly sets up emoji configuration."""
        from data_manager import load_data

        # Load current data
        data = load_data()

        # Check that emoji arrays exist and are correct
        assert "contestant_1_emojis" in data, "contestant_1_emojis missing from data"
        assert "contestant_2_emojis" in data, "contestant_2_emojis missing from data"
        assert "reaction_bet_amounts" in data, "reaction_bet_amounts missing from data"

        assert data["contestant_1_emojis"] == C1_EMOJIS, "contestant_1_emojis not initialized correctly"
        assert data["contestant_2_emojis"] == C2_EMOJIS, "contestant_2_emojis not initialized correctly"
        assert data["reaction_bet_amounts"] == REACTION_BET_AMOUNTS, "reaction_bet_amounts not initialized correctly"

    def test_emoji_validation_utility(self):
        """Test utility functions for emoji validation."""
        from utils.live_message import _get_contestant_from_emoji

        test_data = {
            "contestant_1_emojis": C1_EMOJIS,
            "contestant_2_emojis": C2_EMOJIS,
        }

        # Test C1 emojis
        for emoji in C1_EMOJIS:
            result = _get_contestant_from_emoji(test_data, emoji)  # type: ignore
            assert result == "1", f"Emoji {emoji} should map to contestant 1, got {result}"

        # Test C2 emojis
        for emoji in C2_EMOJIS:
            result = _get_contestant_from_emoji(test_data, emoji)  # type: ignore
            assert result == "2", f"Emoji {emoji} should map to contestant 2, got {result}"

        # Test invalid emoji
        result = _get_contestant_from_emoji(test_data, "🤔")  # type: ignore
        assert result is None, f"Invalid emoji should return None, got {result}"

        # Test separator emoji
        result = _get_contestant_from_emoji(test_data, SEPARATOR_EMOJI)  # type: ignore
        assert result is None, f"Separator emoji should return None, got {result}"