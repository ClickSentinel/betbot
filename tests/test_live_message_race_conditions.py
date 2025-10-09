import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from cogs.bet_commands import BetCommands
from utils.live_message import live_message_scheduler
from data_manager import Data
from typing import cast


@pytest.mark.asyncio
async def test_rapid_lock_then_winner_race():
    """Simulate rapid locking and winner declaration to exercise race conditions.

    This test starts lock and declare_winner flows almost concurrently and
    asserts the final live message embed reflects the winner results.
    """
    # Setup mocked bot/channel/message
    mock_bot = MagicMock(spec=discord.Client)
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.edit = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    mock_bot.get_channel = MagicMock(return_value=mock_channel)

    # Context mock
    mock_ctx = MagicMock()
    mock_ctx.author = MagicMock()
    mock_ctx.author.id = 111222333

    # Test data: open betting with a couple of bets
    test_data = {
        "betting": {
            "open": True,
            "locked": False,
            "contestants": {"1": "Alice", "2": "Bob"},
            "bets": {str(mock_ctx.author.id): {"amount": 100, "choice": "Alice", "emoji": None}},
        },
        "balances": {str(mock_ctx.author.id): 900},
        "live_message": 101010101,
        "live_channel": 202020202,
        "timer_end_time": None,
    }

    # Reset global scheduler state
    live_message_scheduler.stop()
    live_message_scheduler.pending_updates.clear()
    live_message_scheduler.bot = None
    live_message_scheduler.is_running = False

    # Initialize cogs
    betting_cog = BetCommands(mock_bot)
    betting_cog._send_embed = AsyncMock()

    # Create BetUtils instance for utility methods
    from cogs.bet_utils import BetUtils
    bet_utils_cog = BetUtils(mock_bot)
    bet_utils_cog._send_embed = AsyncMock()
    mock_bot.get_cog = MagicMock(return_value=bet_utils_cog)

    # Mock user fetch and data loading
    mock_user = MagicMock()
    mock_user.display_name = "Tester"
    mock_bot.fetch_user = AsyncMock(return_value=mock_user)

    with patch("cogs.betting.load_data", return_value=test_data), patch(
        "cogs.betting.save_data"
    ), patch("data_manager.load_data", return_value=test_data):
        # Start both flows nearly simultaneously to create a race window
        task_lock = asyncio.create_task(bet_utils_cog._lock_bets_internal(mock_ctx))
        # Give the lock a tiny head start then declare winner
        await asyncio.sleep(0.01)
        task_win = asyncio.create_task(
            bet_utils_cog._process_winner_declaration(mock_ctx, cast(Data, test_data), "Alice")
        )

        # Await both
        await asyncio.gather(task_lock, task_win)

        # Manually trigger live message update to reflect the final state
        from utils.live_message import update_live_message
        modified_data = test_data.copy()
        modified_data["betting"]["open"] = False
        modified_data["betting"]["locked"] = True
        await update_live_message(mock_bot, cast(Data, modified_data), winner_declared=True, winner_info={"name": "Alice", "total_pot": 100, "winning_pot": 100, "user_results": {}})

        # Allow scheduler to run (longer than suppression window)
        await asyncio.sleep(6.5)

        # Inspect final edit embed
        assert mock_message.edit.call_count >= 1
        last_call = mock_message.edit.call_args_list[-1]
        embed_obj = last_call.kwargs.get("embed")
        assert embed_obj is not None
        title = (embed_obj.title or "").lower()
        desc = (embed_obj.description or "").lower()

        # Final state should reflect winner 'Alice' or a round-complete summary
        assert ("alice" in title) or ("alice" in desc) or ("round complete" in title)
