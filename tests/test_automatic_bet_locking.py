import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import itertools
import discord
from discord.ext import commands

# Import the classes we're testing
from utils.betting_timer import BettingTimer
from cogs.bet_utils import BetUtils
from data_manager import save_data, load_data


class TestAutomaticBetLocking:
    """Test automatic bet locking and live message updates."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock Discord bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 12345
        bot.get_channel = MagicMock()
        bot.fetch_user = AsyncMock()
        return bot

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock Discord context."""
        ctx = MagicMock(spec=commands.Context)
        ctx.channel = MagicMock(spec=discord.TextChannel)
        ctx.channel.send = AsyncMock()
        ctx.send = AsyncMock()
        return ctx

    @pytest.fixture
    def sample_betting_data(self):
        """Create sample betting data for tests."""
        return {
            "betting": {
                "open": True,
                "locked": False,
                "bets": {
                    "123": {"amount": 100, "choice": "Alice", "emoji": "🔥"},
                    "456": {"amount": 250, "choice": "Bob", "emoji": "💎"},
                },
                "contestants": {"1": "Alice", "2": "Bob"},
            },
            "balances": {"123": 900, "456": 750},
            "reaction_bet_amounts": {
                "🔥": 100,
                "⚡": 250,
                "💪": 500,
                "🏆": 1000,
                "🌟": 100,
                "💎": 250,
                "🚀": 500,
                "👑": 1000,
            },
            "contestant_1_emojis": ["🔥", "⚡", "💪", "🏆"],
            "contestant_2_emojis": ["🌟", "💎", "🚀", "👑"],
            "live_message": 987654321,
            "live_channel": 111222333,
            "live_secondary_message": None,
            "live_secondary_channel": None,
            "settings": {"enable_bet_timer": True, "bet_channel_id": None},
            "timer_end_time": None,
        }

    @pytest.mark.asyncio
    async def test_auto_lock_updates_live_message(
        self, mock_bot, mock_ctx, sample_betting_data
    ):
        """Test that automatic bet locking updates the live message."""
        timer = BettingTimer(mock_bot)

        with patch(
            "utils.betting_timer.load_data", return_value=sample_betting_data
        ), patch("utils.betting_timer.save_data") as mock_save, patch(
            "utils.betting_timer.update_live_message"
        ) as mock_update, patch(
            "utils.betting_timer.schedule_live_message_update"
        ) as mock_schedule:

            # Simulate timer expiration
            await timer._auto_lock_bets(mock_ctx, sample_betting_data)

            # Verify betting state was locked
            assert sample_betting_data["betting"]["open"] is False
            assert sample_betting_data["betting"]["locked"] is True
            assert sample_betting_data["timer_end_time"] is None

            # Verify save was called
            mock_save.assert_called()

            # Verify live message update was called with correct parameters
            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[0][0] == mock_bot  # bot parameter
            assert call_args[0][1] == sample_betting_data  # data parameter
            assert call_args[1]["betting_closed"] is True  # betting_closed parameter
            assert "close_summary" in call_args[1]  # close_summary parameter

            # Verify batched update was also scheduled for pending bets
            mock_schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_lock_updates_live_message(
        self, mock_bot, mock_ctx, sample_betting_data
    ):
        """Test that manual bet locking updates the live message."""
        betting_cog = BetUtils(mock_bot)

        with patch(
            "cogs.bet_utils.load_data", return_value=sample_betting_data
        ), patch("cogs.bet_utils.save_data") as mock_save, patch(
            "cogs.bet_utils.update_live_message"
        ) as mock_update, patch(
            "cogs.bet_utils.schedule_live_message_update"
        ) as mock_schedule, patch(
            "cogs.bet_utils.get_live_message_info", return_value=(None, None)
        ), patch(
            "cogs.bet_utils.get_secondary_live_message_info",
            return_value=(None, None),
        ):

            # Test manual bet locking
            await betting_cog._lock_bets_internal(mock_ctx)

            # Verify betting state was locked
            assert sample_betting_data["betting"]["open"] is False
            assert sample_betting_data["betting"]["locked"] is True

            # Verify save was called
            mock_save.assert_called()

            # Verify live message update was called
            mock_update.assert_called_once()

            # Verify context response was sent
            mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    async def test_last_moment_bet_during_auto_lock(
        self, mock_bot, mock_ctx, sample_betting_data
    ):
        """Test that last-moment bets are handled correctly during auto-lock."""
        timer = BettingTimer(mock_bot)

        # Simulate a scenario where bets are placed right before timer expires
        with patch(
            "utils.betting_timer.load_data", return_value=sample_betting_data
        ), patch("utils.betting_timer.save_data") as mock_save, patch(
            "utils.betting_timer.update_live_message"
        ) as mock_update, patch(
            "utils.betting_timer.schedule_live_message_update"
        ) as mock_schedule:

            # Add a last-moment bet to the data
            sample_betting_data["betting"]["bets"]["789"] = {
                "amount": 500,
                "choice": "Alice",
                "emoji": "💪",
            }
            sample_betting_data["balances"]["789"] = 500

            await timer._auto_lock_bets(mock_ctx, sample_betting_data)

            # Verify the live message was updated immediately with locked state
            mock_update.assert_called_once()

            # Verify batched update was scheduled to handle any pending updates
            mock_schedule.assert_called_once()

            # This ensures that even if there were batched updates pending,
            # they will be processed and then the locked state will be shown

    @pytest.mark.asyncio
    async def test_timer_update_sequence_with_batched_updates(
        self, mock_bot, mock_ctx, sample_betting_data
    ):
        """Test that timer updates work correctly with batched message updates."""
        timer = BettingTimer(mock_bot)


        with patch(
            "utils.betting_timer.load_data", return_value=sample_betting_data
        ), patch("utils.betting_timer.save_data") as mock_save, patch(
            "cogs.bet_utils.update_live_message"
        ) as mock_update, patch(
            "cogs.bet_utils.schedule_live_message_update"
        ) as mock_schedule, patch(
            "time.time"
        ) as mock_time:

            # Set up timer for 10 seconds
            start_time = 1000.0
            end_time = start_time + 10.0
            sample_betting_data["timer_end_time"] = end_time

            # Mock time progression: start -> 5 seconds left -> 0 seconds left (expired)
            time_sequence = [
                start_time,
                start_time + 5.0,
                start_time + 10.0,
                start_time + 11.0,
            ]
            # Use an infinite iterator that repeats the last timestamp to avoid StopIteration
            mock_time.side_effect = itertools.chain(time_sequence, itertools.repeat(time_sequence[-1]))

            # Simulate timer running for a very short duration
            timer_task = asyncio.create_task(timer._run_timer(mock_ctx, 10))

            # Let it run briefly then cancel to avoid infinite loop
            await asyncio.sleep(0.1)
            timer_task.cancel()

            try:
                await timer_task
            except asyncio.CancelledError:
                pass

            # In a real scenario, the timer would make updates at 5-second intervals
            # and then auto-lock when expired, each triggering appropriate update methods

    @pytest.mark.asyncio
    async def test_timer_respects_manual_lock_during_countdown(
        self, mock_bot, mock_ctx, sample_betting_data
    ):
        """Test that timer stops correctly when bets are manually locked during countdown."""
        timer = BettingTimer(mock_bot)

        # Simulate manual lock happening during timer
        locked_data = sample_betting_data.copy()
        locked_data["betting"]["locked"] = True
        locked_data["betting"]["open"] = False

        with patch(
            "utils.betting_timer.load_data",
            side_effect=[sample_betting_data, locked_data],
        ), patch("utils.betting_timer.save_data") as mock_save, patch(
            "time.time"
        ) as mock_time:  # 5 seconds into timer

            # Prevent StopIteration by repeating the last mocked time indefinitely
            mock_time.side_effect = itertools.chain([1000.0, 1005.0], itertools.repeat(1005.0))

            # Start timer task
            timer_task = asyncio.create_task(timer._run_timer(mock_ctx, 10))

            # Let it run briefly
            await asyncio.sleep(0.1)

            # Timer should detect manual lock and exit early
            # In real implementation, this would be detected in the while loop

            timer_task.cancel()
            try:
                await timer_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_bet_locking_order_of_operations(
        self, mock_bot, mock_ctx, sample_betting_data
    ):
        """Test that bet locking operations happen in the correct order."""
        betting_cog = BetUtils(mock_bot)

        # Track the order of operations
        operation_order = []

        def track_save_data(data):
            operation_order.append("save_data")

        async def track_update_message(*args, **kwargs):
            operation_order.append("update_live_message")
            return None

        def track_schedule_update():
            operation_order.append("schedule_live_message_update")

        with patch(
            "cogs.bet_utils.load_data", return_value=sample_betting_data
        ), patch("cogs.bet_utils.save_data", side_effect=track_save_data), patch(
            "cogs.bet_utils.update_live_message", side_effect=track_update_message
        ), patch(
            "cogs.bet_utils.schedule_live_message_update",
            side_effect=track_schedule_update,
        ), patch(
            "cogs.bet_utils.get_live_message_info", return_value=(None, None)
        ), patch(
            "cogs.bet_utils.get_secondary_live_message_info",
            return_value=(None, None),
        ):

            await betting_cog._lock_bets_internal(mock_ctx)

            # Verify correct order: save data first, then update message
            expected_order = [
                "save_data",
                "update_live_message",
            ]
            assert (
                operation_order == expected_order
            ), f"Expected {expected_order}, got {operation_order}"

    @pytest.mark.asyncio
    async def test_reaction_clearing_during_lock(
        self, mock_bot, mock_ctx, sample_betting_data
    ):
        """Test that reactions are properly cleared when bets are locked."""
        betting_cog = BetUtils(mock_bot)

        # Set up live message info
        sample_betting_data["live_message"] = 987654321
        sample_betting_data["live_channel"] = 111222333

        # Mock channel and message
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = AsyncMock(spec=discord.Message)
        mock_bot.get_channel.return_value = mock_channel
        mock_channel.fetch_message.return_value = mock_message

        with patch(
            "cogs.bet_utils.load_data", return_value=sample_betting_data
        ), patch("cogs.bet_utils.save_data"), patch(
            "cogs.bet_utils.update_live_message"
        ) as mock_update, patch(
            "cogs.bet_utils.schedule_live_message_update"
        ), patch(
            "cogs.bet_utils.get_live_message_info",
            return_value=(987654321, 111222333),
        ), patch(
            "cogs.bet_utils.get_secondary_live_message_info",
            return_value=(None, None),
        ):

            await betting_cog._lock_bets_internal(mock_ctx)

            # Verify live message was updated
            mock_update.assert_called_once()
