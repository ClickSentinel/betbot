import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

# Import the classes we're testing
from betbot.utils.live_message import (
    LiveMessageScheduler,
    schedule_live_message_update,
    initialize_live_message_scheduler,
    stop_live_message_scheduler,
    live_message_scheduler,
)


class TestLiveMessageScheduler:
    """Test the LiveMessageScheduler class for batched updates."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock Discord bot."""
        bot = MagicMock(spec=discord.Client)
        bot.fetch_user = AsyncMock()
        bot.get_channel = MagicMock()
        return bot

    @pytest.fixture
    def scheduler(self):
        """Create a fresh LiveMessageScheduler instance."""
        return LiveMessageScheduler()

    @pytest.fixture
    def test_data(self):
        """Create test data for live message updates."""
        return {
            "betting": {
                "open": True,
                "locked": False,
                "bets": {
                    "123": {"amount": 100, "choice": "alice", "emoji": "🔥"},
                    "456": {"amount": 250, "choice": "bob", "emoji": "💎"},
                },
                "contestants": {"1": "Alice", "2": "Bob"},
            },
            "balances": {"123": 900, "456": 750},
            "live_message": 789,
            "live_channel": 101112,
            "timer_end_time": None,
        }

    @pytest.mark.asyncio
    async def test_scheduler_initialization(self, scheduler, mock_bot):
        """Test scheduler initialization and bot assignment."""
        # Initially no bot assigned
        assert scheduler.bot is None
        assert not scheduler.is_running
        assert len(scheduler.pending_updates) == 0

        # Set bot
        scheduler.set_bot(mock_bot)
        assert scheduler.bot == mock_bot

    @pytest.mark.asyncio
    async def test_schedule_single_update(self, scheduler, mock_bot):
        """Test scheduling a single update."""
        scheduler.set_bot(mock_bot)

        # Schedule an update
        scheduler.schedule_update("test_id")

        # Should be marked as pending
        assert "test_id" in scheduler.pending_updates
        assert scheduler.is_running

    @pytest.mark.asyncio
    async def test_schedule_multiple_updates_batched(self, scheduler, mock_bot):
        """Test that multiple updates within 5 seconds are batched together."""
        scheduler.set_bot(mock_bot)

        # Schedule multiple updates rapidly
        scheduler.schedule_update("update1")
        scheduler.schedule_update("update2")
        scheduler.schedule_update("update3")

        # All should be pending
        assert len(scheduler.pending_updates) == 3
        assert scheduler.is_running

    @pytest.mark.asyncio
    async def test_schedule_duplicate_updates(self, scheduler, mock_bot):
        """Test that duplicate update IDs are deduplicated."""
        scheduler.set_bot(mock_bot)

        # Schedule same ID multiple times
        scheduler.schedule_update("same_id")
        scheduler.schedule_update("same_id")
        scheduler.schedule_update("same_id")

        # Should only have one entry
        assert len(scheduler.pending_updates) == 1
        assert "same_id" in scheduler.pending_updates

    @pytest.mark.asyncio
    async def test_update_loop_processes_batches(self, scheduler, mock_bot):
        """Test that the update loop processes batched updates."""
        with patch(
            "betbot.utils.live_message.update_live_message", new_callable=AsyncMock
        ) as mock_update, patch("data_manager.load_data") as mock_load_data:

            mock_load_data.return_value = {"test": "data"}
            scheduler.set_bot(mock_bot)

            # Schedule updates
            scheduler.schedule_update("batch1")
            scheduler.schedule_update("batch2")

            # Wait for batch processing (slightly more than 5 seconds)
            await asyncio.sleep(5.1)

            # Should have processed the batch
            mock_update.assert_called_once_with(mock_bot, {"test": "data"})
            assert len(scheduler.pending_updates) == 0

    @pytest.mark.asyncio
    async def test_scheduler_without_bot(self, scheduler):
        """Test scheduler behavior when no bot is set."""
        # Schedule update without bot - should be ignored
        scheduler.schedule_update("no_bot")

        assert len(scheduler.pending_updates) == 0
        assert not scheduler.is_running

    @pytest.mark.asyncio
    async def test_scheduler_stop(self, scheduler, mock_bot):
        """Test stopping the scheduler."""
        scheduler.set_bot(mock_bot)
        scheduler.schedule_update("test")

        # Stop the scheduler
        scheduler.stop()

        assert not scheduler.is_running
        if scheduler.update_task:
            assert scheduler.update_task.cancelled()

    @pytest.mark.asyncio
    async def test_update_loop_error_handling(self, scheduler, mock_bot):
        """Test that update loop handles errors gracefully."""
        with patch(
            "betbot.utils.live_message.update_live_message", new_callable=AsyncMock
        ) as mock_update, patch("data_manager.load_data") as mock_load_data, patch(
            "builtins.print"
        ) as mock_print:

            # Make update_live_message raise an exception
            mock_update.side_effect = Exception("Test error")
            mock_load_data.return_value = {"test": "data"}

            scheduler.set_bot(mock_bot)
            scheduler.schedule_update("error_test")

            # Wait for processing
            await asyncio.sleep(5.1)

            # Should have handled the error and printed it
            mock_print.assert_called()
            # Scheduler should have cleaned up after error
            assert not scheduler.is_running


class TestGlobalSchedulerFunctions:
    """Test the global scheduler functions."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        # Setup: Reset global scheduler
        live_message_scheduler.stop()
        live_message_scheduler.pending_updates.clear()
        live_message_scheduler.bot = None
        live_message_scheduler.is_running = False

        yield

        # Teardown: Clean up
        live_message_scheduler.stop()
        live_message_scheduler.pending_updates.clear()

    @pytest.mark.asyncio
    async def test_initialize_live_message_scheduler(self):
        """Test the global scheduler initialization function."""
        mock_bot = MagicMock(spec=discord.Client)

        initialize_live_message_scheduler(mock_bot)

        assert live_message_scheduler.bot == mock_bot

    @pytest.mark.asyncio
    async def test_schedule_live_message_update(self):
        """Test the global schedule function."""
        mock_bot = MagicMock(spec=discord.Client)
        initialize_live_message_scheduler(mock_bot)

        schedule_live_message_update()

        assert "default" in live_message_scheduler.pending_updates
        assert live_message_scheduler.is_running

    @pytest.mark.asyncio
    async def test_stop_live_message_scheduler(self):
        """Test the global stop function."""
        mock_bot = MagicMock(spec=discord.Client)
        initialize_live_message_scheduler(mock_bot)
        schedule_live_message_update()

        stop_live_message_scheduler()

        assert not live_message_scheduler.is_running

    @pytest.mark.asyncio
    async def test_multiple_rapid_schedules_batched(self):
        """Test that multiple rapid schedule calls are properly batched."""
        mock_bot = MagicMock(spec=discord.Client)
        initialize_live_message_scheduler(mock_bot)

        # Rapidly schedule multiple updates
        for i in range(5):
            schedule_live_message_update()

        # Should only have one pending update (default ID)
        assert len(live_message_scheduler.pending_updates) == 1
        assert "default" in live_message_scheduler.pending_updates

    @pytest.mark.asyncio
    async def test_integration_with_betting_flow(self):
        """Test integration with typical betting workflow."""
        with patch(
            "betbot.utils.live_message.update_live_message", new_callable=AsyncMock
        ) as mock_update, patch("data_manager.load_data") as mock_load_data:

            mock_bot = MagicMock(spec=discord.Client)
            mock_load_data.return_value = {
                "betting": {"open": True, "bets": {}},
                "balances": {},
            }

            initialize_live_message_scheduler(mock_bot)

            # Simulate multiple users placing bets rapidly
            schedule_live_message_update()  # User 1 bets
            schedule_live_message_update()  # User 2 bets
            schedule_live_message_update()  # User 1 changes bet
            schedule_live_message_update()  # User 3 bets

            # Wait for batch processing
            await asyncio.sleep(5.1)

            # Should have made exactly one update call
            assert mock_update.call_count == 1
            mock_update.assert_called_with(mock_bot, mock_load_data.return_value)


class TestSchedulerEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def scheduler(self):
        """Create a fresh scheduler."""
        return LiveMessageScheduler()

    @pytest.mark.asyncio
    async def test_scheduler_task_cancellation(self, scheduler):
        """Test proper task cancellation when stopping scheduler."""
        mock_bot = MagicMock(spec=discord.Client)
        scheduler.set_bot(mock_bot)

        # Schedule update to start task
        scheduler.schedule_update("test")
        original_task = scheduler.update_task

        # Stop the scheduler - should cancel the task
        scheduler.stop()

        # Give cancellation a moment to take effect
        await asyncio.sleep(0.1)

        # Original task should be cancelled
        if original_task:
            assert original_task.cancelled()

        # Scheduler should be stopped
        assert not scheduler.is_running

    @pytest.mark.asyncio
    async def test_concurrent_schedule_calls(self, scheduler):
        """Test concurrent schedule calls don't cause issues."""
        mock_bot = MagicMock(spec=discord.Client)
        scheduler.set_bot(mock_bot)

        # Simulate concurrent schedule calls using direct calls
        # (scheduler.schedule_update is synchronous, so this tests thread safety)
        for i in range(10):
            scheduler.schedule_update(f"concurrent_{i}")

        # Should have all updates scheduled
        assert len(scheduler.pending_updates) == 10

    @pytest.mark.asyncio
    async def test_scheduler_persistence_across_calls(self, scheduler):
        """Test that scheduler maintains state across multiple calls."""
        mock_bot = MagicMock(spec=discord.Client)
        scheduler.set_bot(mock_bot)

        # Schedule first batch
        scheduler.schedule_update("batch1")
        assert scheduler.is_running
        assert len(scheduler.pending_updates) == 1

        # Schedule second batch while first is still running
        scheduler.schedule_update("batch2")

        # Should accumulate pending updates
        assert len(scheduler.pending_updates) == 2
        assert scheduler.is_running

        # Clean up
        scheduler.stop()
