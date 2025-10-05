import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from cogs.betting import Betting
from utils.live_message import live_message_scheduler
from data_manager import Data
from typing import cast
import copy


@pytest.mark.skip("Stress test - run manually when needed")
@pytest.mark.asyncio
async def test_stress_rapid_lock_and_winner_cycles():
    """Stress test: run many near-concurrent lock+winner flows to exercise race conditions.

    This test is skipped by default. To run it manually (locally), remove or
    comment out the @pytest.mark.skip decorator above. You can also reduce the
    iteration count for quicker local runs.
    """
    ITERATIONS = 200  # Reduce when running locally if needed

    # Basic mocks reused across iterations
    mock_bot = MagicMock(spec=discord.Client)
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.edit = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    mock_bot.get_channel = MagicMock(return_value=mock_channel)

    betting_cog = Betting(mock_bot)
    betting_cog._send_embed = AsyncMock()

    base_data = {
        "betting": {
            "open": True,
            "locked": False,
            "contestants": {"1": "Alice", "2": "Bob"},
            "bets": {},
        },
        "balances": {},
        "live_message": 555666777,
        "live_channel": 888999000,
        "timer_end_time": None,
    }

    mock_user = MagicMock()
    mock_user.display_name = "StressUser"
    mock_bot.fetch_user = AsyncMock(return_value=mock_user)

    for i in range(ITERATIONS):
        # fresh copy of data per iteration to avoid cross-iteration mutation
        iteration_data = copy.deepcopy(base_data)
        # add a bet from a unique user to vary data a bit
        uid = str(100000 + i)
        iteration_data["betting"]["bets"][uid] = {"amount": 100, "choice": "Alice", "emoji": None}

        # reset scheduler state
        live_message_scheduler.stop()
        live_message_scheduler.pending_updates.clear()
        live_message_scheduler.bot = None
        live_message_scheduler.is_running = False

        with patch("cogs.betting.load_data", return_value=iteration_data), patch(
            "cogs.betting.save_data"
        ), patch("data_manager.load_data", return_value=iteration_data):
            # start lock then quickly declare winner
            task_lock = asyncio.create_task(betting_cog._lock_bets_internal(MagicMock()))
            await asyncio.sleep(0.005)  # tiny jitter
            task_win = asyncio.create_task(betting_cog._process_winner_declaration(MagicMock(), cast(Data, iteration_data), "Alice"))

            await asyncio.gather(task_lock, task_win)

            # allow scheduler to settle; we choose 7s > suppression window
            await asyncio.sleep(7.0)

            # final embed must mention winner/round complete or locked
            assert mock_message.edit.call_count >= 1
            last_call = mock_message.edit.call_args_list[-1]
            embed_obj = last_call.kwargs.get("embed")
            assert embed_obj is not None
            title = (embed_obj.title or "").lower()
            desc = (embed_obj.description or "").lower()
            assert ("alice" in title) or ("alice" in desc) or ("round complete" in title)

    # If we reached here, the stress loop completed without assertion failures
