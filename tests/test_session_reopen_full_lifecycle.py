import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.bet_commands import BetCommands
from tests.conftest import MockRole


@pytest.mark.asyncio
async def test_open_close_reopen_same_names(mock_bot, mock_ctx, mock_message):
    """Open a session, close it, then re-open with the same contestant names.

    Ensures the closed session is ignored for name-conflict checks and a new
    active session is created and mapped correctly.
    """

    # Build minimal initial data (legacy fields + multi-session placeholders)
    mock_ctx.author = MagicMock(spec=discord.Member)
    mock_ctx.author.id = 999999
    mock_ctx.channel = MagicMock(spec=discord.TextChannel)
    mock_ctx.channel.id = 2222
    mock_ctx.channel.send = AsyncMock(return_value=mock_message)

    data = {
        "balances": {str(mock_ctx.author.id): 1000},
        "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
        "settings": {"enable_bet_timer": False},
        "reaction_bet_amounts": {},
        "contestant_1_emojis": [],
        "contestant_2_emojis": [],
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

    with patch("cogs.betting.load_data", return_value=data), patch(
        "cogs.betting.save_data"
    ), patch("cogs.betting.clear_live_message_info"), patch(
        "cogs.betting.set_live_message_info"
    ), patch("cogs.betting.update_live_message"), patch(
        "cogs.betting.get_saved_bet_channel_id", return_value=None
    ):

        # Instantiate the cog and bypass permission checks
        betting_cog = BetCommands(mock_bot)
        betting_cog._check_permission = AsyncMock(return_value=True)

        # Open a session
        await betting_cog.openbet.callback(betting_cog, mock_ctx, "Alice", "Bob")

        # Verify an open session exists
        open_sessions = [sid for sid, s in data["betting_sessions"].items() if s.get("status") == "open"]
        assert len(open_sessions) == 1
        first_session_id = open_sessions[0]

        # Close the session via compatibility wrapper
        await betting_cog.close_session.callback(betting_cog, mock_ctx, first_session_id)

        # Closed session should be marked closed and removed from active_sessions
        assert data["betting_sessions"][first_session_id]["status"] == "closed"
        assert first_session_id not in data.get("active_sessions", [])

        # Re-open with the same names
        await betting_cog.openbet.callback(betting_cog, mock_ctx, "Alice", "Bob")

        # Ensure a new open session exists and is not the same id as the closed one
        open_sessions = [sid for sid, s in data["betting_sessions"].items() if s.get("status") == "open"]
        assert len(open_sessions) == 1
        new_session_id = open_sessions[0]
        assert new_session_id != first_session_id

        # Mapping should point to the new session
        assert data["contestant_to_session"]["alice"] == new_session_id
