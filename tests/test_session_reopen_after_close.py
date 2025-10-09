import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.bet_commands import BetCommands
from tests.conftest import setup_member_with_role, MockRole


@pytest.mark.asyncio
async def test_reopen_after_close(mock_bot, mock_ctx, mock_message):
    """Regression: create -> close -> re-open a session using the same contestant names.

    Ensures that closed sessions do not prevent reusing contestant names for
    new active sessions (the closed sessions should be skipped when checking
    for name conflicts).
    """

    # Prepare test data with one previously closed session using Alice/Bob
    now = time.time()
    closed_session_id = "1"
    test_data = {
    "balances": {str(mock_ctx.author.id): 1000},
        "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
        "settings": {"enable_bet_timer": True},
        "reaction_bet_amounts": {},
        "contestant_1_emojis": [],
        "contestant_2_emojis": [],
        "live_message": None,
        "live_channel": None,
        "live_secondary_message": None,
        "live_secondary_channel": None,
        "timer_end_time": None,
        "betting_sessions": {
            closed_session_id: {
                "id": closed_session_id,
                "title": "Alice vs Bob",
                "created_at": now,
                "creator_id": mock_ctx.author.id,
                "channel_id": mock_ctx.channel.id if hasattr(mock_ctx.channel, "id") else 1111,
                "timer_config": {"enabled": False, "duration": 0},
                "lock_time": None,
                "close_time": None,
                "status": "closed",
                "contestants": {"c1": "Alice", "c2": "Bob"},
                "bets": {},
                "live_message_id": None,
                "last_update": now,
                "total_pot": 0,
                "total_bettors": 0,
                "winner": None,
                "closed_at": now,
                "closed_by": "tester",
            }
        },
        # No active sessions - closed session should not block new opens
        "active_sessions": [],
        "contestant_to_session": {},
        "multi_session_mode": True,
    }

    # Prepare a realistic mock context: ensure author has an id and roles
    mock_ctx.author = MagicMock(spec=discord.Member)
    mock_ctx.author.id = 424242
    mock_ctx.author.display_name = "Tester"
    mock_ctx.author.roles = [MockRole("betboy")]
    # Ensure channel is a TextChannel-like mock with an id and send
    mock_ctx.channel = MagicMock(spec=discord.TextChannel)
    mock_ctx.channel.id = 1111
    mock_ctx.channel.send = AsyncMock(return_value=mock_message)

    # Patch load/save/live-message helpers used by openbet and run the flow
    # inside the patched context so `load_data` returns our `test_data`.
    with patch("cogs.betting.load_data", return_value=test_data), patch(
        "cogs.betting.save_data"
    ), patch("cogs.betting.clear_live_message_info"), patch(
        "cogs.betting.set_live_message_info"
    ), patch("cogs.betting.update_live_message"), patch(
        "discord.utils.get"
    ) as mock_get, patch("cogs.betting.get_saved_bet_channel_id", return_value=None):

        # Ensure permission check passes by returning a betboy role
        mock_get.return_value = MockRole("betboy")

        # Make isinstance checks against discord.TextChannel succeed in the
        # test environment by pointing the module symbol to MagicMock.
        import cogs.betting as cb
        cb.discord.TextChannel = MagicMock

        # Instantiate the cog under the patched load_data so it uses our test_data
        betting_cog = BetCommands(mock_bot)

        # Bypass permission checking for the command to focus on the
        # session-name conflict behavior (other tests validate permissions).
        betting_cog._check_permission = AsyncMock(return_value=True)

        # Call openbet to create a new session with the same contestant names
        await betting_cog.openbet.callback(betting_cog, mock_ctx, "Alice", "Bob")

    # After calling openbet a new session should exist and be active
    assert len(test_data["betting_sessions"]) == 2

    # Find the newly created session id (not the closed one)
    new_session_id = next(sid for sid in test_data["betting_sessions"] if sid != closed_session_id)
    new_session = test_data["betting_sessions"][new_session_id]

    assert new_session["status"] == "open"
    assert new_session["contestants"]["c1"] == "Alice"
    assert new_session["contestants"]["c2"] == "Bob"
    # contestant_to_session should map the lowercase name to the new session id
    assert test_data["contestant_to_session"]["alice"] == new_session_id
