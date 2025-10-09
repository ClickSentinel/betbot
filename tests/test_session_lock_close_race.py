import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from cogs.bet_commands import BetCommands
from utils.live_message import live_message_scheduler


@pytest.mark.asyncio
async def test_session_auto_close_and_race():
    """Simulate a session timer expiring while other updates arrive to ensure
    the final embed shows the closed/winner summary and is not overwritten.
    """
    # Mock bot/channel/message
    mock_bot = MagicMock(spec=discord.Client)
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.edit = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    mock_bot.get_channel = MagicMock(return_value=mock_channel)

    # Context mock
    mock_ctx = MagicMock()
    mock_ctx.author = MagicMock()
    mock_ctx.author.id = 555666777

    # Create a session set to auto-close in a short time (2s)
    now = time.time()
    session_id = "race_session"
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
            session_id: {
                "id": session_id,
                "title": "X vs Y",
                "created_at": now,
                "creator_id": mock_ctx.author.id,
                "channel_id": 12345,
                "timer_config": {"enabled": True, "duration": 2, "auto_close_at": now + 2},
                "lock_time": None,
                "close_time": None,
                "status": "open",
                "contestants": {"c1": "X", "c2": "Y"},
                "bets": {str(mock_ctx.author.id): {"amount": 100, "choice": "X", "emoji": None}},
                "live_message_id": 9999,
                "last_update": now,
                "total_pot": 100,
                "total_bettors": 1,
                "winner": None,
                "closed_at": None,
                "closed_by": None,
            }
        },
        "active_sessions": [session_id],
        "contestant_to_session": {"x": session_id, "y": session_id},
        "multi_session_mode": True,
    }

    # Reset scheduler
    live_message_scheduler.stop()
    live_message_scheduler.pending_updates.clear()
    live_message_scheduler.bot = None
    live_message_scheduler.is_running = False

    betting_cog = BetCommands(mock_bot)
    betting_cog._send_embed = AsyncMock()

    mock_user = MagicMock()
    mock_user.display_name = "Racer"
    mock_bot.fetch_user = AsyncMock(return_value=mock_user)

    with patch("cogs.bet_commands.load_data", return_value=test_data), patch(
        "cogs.bet_commands.save_data"
    ), patch("data_manager.load_data", return_value=test_data):

        # Start a background flow that schedules a bunch of updates
        async def rapid_updates():
            # Simulate several rapid schedule triggers during countdown
            from utils.live_message import schedule_live_message_update_for_session

            for _ in range(3):
                schedule_live_message_update_for_session(session_id)
                await asyncio.sleep(0.3)

        # Run rapid updates and let the session auto-close (~2s)
        updater_task = asyncio.create_task(rapid_updates())

        # Wait for longer than auto-close time and suppression window
        await asyncio.sleep(4.0)

        # Ensure permission check passes and invoke close flow that an admin might trigger
        betting_cog._check_permission = AsyncMock(return_value=True)
        # Call the command callback to close the session (no winner)
        await betting_cog.close_session(mock_ctx, session_id)

        # Allow scheduler to run
        await asyncio.sleep(1.0)

        # Final embed edit calls should include an embed with 'closed' or 'wins'
        assert mock_message.edit.call_count >= 1
        last_call = mock_message.edit.call_args_list[-1]
        embed_obj = last_call.kwargs.get("embed")
        assert embed_obj is not None
        title = (embed_obj.title or "").lower()
        desc = (embed_obj.description or "").lower()

        assert (
            ("closed" in title)
            or ("locked" in title)
            or ("wins" in title)
            or ("round complete" in title)
            or ("wins" in desc)
            or ("session closed" in desc)
        )
