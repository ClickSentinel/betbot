import pytest
import asyncio
from unittest.mock import MagicMock
import discord
from cogs.bet_utils import BetUtils
from data_manager import save_data


@pytest.mark.asyncio
async def test_process_bet_writes_session_bet(test_data, mock_bot, mock_message, mock_ctx):
    # Arrange: create a session and a channel
    test_data["betting_sessions"] = {
        "s1": {
            "id": "s1",
            "title": "Test Session",
            "created_at": 0.0,
            "creator_id": 1,
            "channel_id": 111,
            "timer_config": {"enabled": False, "duration": 0},
            "lock_time": None,
            "close_time": None,
            "status": "open",
            "contestants": {"1": "Alice", "2": "Bob"},
            "bets": {},
            "live_message_id": None,
            "last_update": 0.0,
            "total_pot": 0,
            "total_bettors": 0,
            "winner": None,
            "closed_at": None,
            "closed_by": None,
        }
    }
    test_data["active_sessions"] = ["s1"]
    test_data["multi_session_mode"] = True
    test_data["contestant_to_session"] = {}
    test_data["balances"][str(mock_ctx.author.id)] = 1000

    # Create a Betting cog with a mock bot
    betting_cog = BetUtils(mock_bot)

    # Act: place a bet via the internal _process_bet
    result = await betting_cog._process_bet(mock_ctx.channel, test_data, str(mock_ctx.author.id), 200, "Alice", emoji=None, notify_user=False)

    # Assert
    assert result is True
    assert str(mock_ctx.author.id) in test_data["betting_sessions"]["s1"]["bets"]
    bet_info = test_data["betting_sessions"]["s1"]["bets"][str(mock_ctx.author.id)]
    assert bet_info["amount"] == 200
    assert test_data["balances"][str(mock_ctx.author.id)] == 800
