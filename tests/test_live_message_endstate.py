import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from cogs.betting import Betting
from utils.live_message import initialize_live_message_scheduler, schedule_live_message_update, live_message_scheduler
from data_manager import Data
from typing import cast


@pytest.mark.asyncio
async def test_live_message_endstate_after_winner_declared():
    """Ensure the live message remains the winner results embed after winner declaration and a batched update."""
    # Prepare bot and mocks
    mock_bot = MagicMock(spec=discord.Client)
    mock_bot.fetch_user = AsyncMock()

    # Mock channel/message to capture edit calls
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.edit = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    mock_bot.get_channel = MagicMock(return_value=mock_channel)

    # Minimal context mock
    mock_ctx = MagicMock()
    mock_ctx.author = MagicMock()
    mock_ctx.author.id = 123456

    # Build test data: locked betting with one bet
    test_data = {
        "betting": {
            "open": False,
            "locked": True,
            "contestants": {"1": "Alice", "2": "Bob"},
            "bets": {str(mock_ctx.author.id): {"amount": 100, "choice": "Alice", "emoji": None}},
        },
        "balances": {str(mock_ctx.author.id): 900},
        "live_message": 999111222,
        "live_channel": 555666777,
        "timer_end_time": None,
    }

    # Ensure global scheduler is clean
    live_message_scheduler.stop()
    live_message_scheduler.pending_updates.clear()
    live_message_scheduler.bot = None
    live_message_scheduler.is_running = False

    # Initialize betting cog (this also initializes scheduler with the bot)
    betting_cog = Betting(mock_bot)

    # Patch load_data and save_data used by betting flow and scheduler
    with patch("cogs.betting.load_data", return_value=test_data), patch(
        "cogs.betting.save_data"
    ), patch("data_manager.load_data", return_value=test_data):
        # patch fetch_user to return name
        mock_user = MagicMock()
        mock_user.display_name = "Tester"
        mock_bot.fetch_user = AsyncMock(return_value=mock_user)

    # Prevent embed sending from trying to await MagicMock ctx.send
    betting_cog._send_embed = AsyncMock()

    # Call the internal winner processing function directly
    await betting_cog._process_winner_declaration(mock_ctx, cast(Data, test_data), "Alice")

    # After declaration, at least one edit should have occurred
    assert mock_message.edit.call_count >= 1

    # Wait for the batched scheduler to run (5s window + small margin)
    await asyncio.sleep(6.2)

    # Inspect the last embed that was used to edit the message
    last_call = mock_message.edit.call_args_list[-1]
    # discord.Embed is passed as a keyword arg 'embed' in code
    embed_obj = last_call.kwargs.get("embed")
    assert embed_obj is not None
    # The final embed title should contain 'Round Complete' or the winner name
    assert ("Round Complete" in (embed_obj.title or "")) or ("Alice" in (embed_obj.title or ""))


@pytest.mark.asyncio
async def test_live_message_endstate_after_lock():
    """Ensure the live message remains the locked results embed after locking and a batched update."""
    mock_bot = MagicMock(spec=discord.Client)
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.edit = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    mock_bot.get_channel = MagicMock(return_value=mock_channel)

    mock_ctx = MagicMock()

    # Test data: open betting that will be locked
    test_data = {
        "betting": {
            "open": True,
            "locked": False,
            "contestants": {"1": "Alice", "2": "Bob"},
            "bets": {},
        },
        "balances": {},
        "live_message": 222333444,
        "live_channel": 777888999,
        "timer_end_time": None,
    }

    # Reset scheduler
    live_message_scheduler.stop()
    live_message_scheduler.pending_updates.clear()
    live_message_scheduler.bot = None
    live_message_scheduler.is_running = False

    betting_cog = Betting(mock_bot)
    betting_cog._send_embed = AsyncMock()

    with patch("cogs.betting.load_data", return_value=test_data), patch(
        "cogs.betting.save_data"
    ), patch("data_manager.load_data", return_value=test_data):
        # Call the internal lock flow
        await betting_cog._lock_bets_internal(mock_ctx)

    # After locking, at least one edit should have occurred
    assert mock_message.edit.call_count >= 1

    # Wait for the batched scheduler to run (longer than suppression window)
    await asyncio.sleep(6.2)

    # Inspect the last embed used to edit the message
    last_call = mock_message.edit.call_args_list[-1]
    embed_obj = last_call.kwargs.get("embed")
    assert embed_obj is not None
    # The final embed should indicate betting is locked
    title = (embed_obj.title or "").lower()
    desc = (embed_obj.description or "").lower()
    assert ("locked" in title) or ("locked" in desc) or ("round complete" in title)
