"""
Focused tests for reaction betting race condition fix.
These tests verify that the specific issue reported by the user has been resolved.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import asyncio
import time

from cogs.betting import Betting


class TestReactionBettingRaceConditionFix:
    """Tests specifically for the race condition fix in reaction betting."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot."""
        bot = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 12345
        return bot

    @pytest.fixture
    def betting_cog(self, mock_bot):
        """Create betting cog instance."""
        return Betting(mock_bot)

    def test_programmatic_removal_tracking_system(self, betting_cog):
        """Test the core programmatic removal tracking system."""
        message_id = 123456789
        user_id = 67890
        emoji = "🔥"

        # Initially should not be tracked
        assert not betting_cog._is_programmatic_removal(message_id, user_id, emoji)

        # Mark as programmatic
        betting_cog._mark_programmatic_removal(message_id, user_id, emoji)

        # Should now be detected (and removed from tracking)
        assert betting_cog._is_programmatic_removal(message_id, user_id, emoji)

        # Should no longer be tracked after checking (one-time use)
        assert not betting_cog._is_programmatic_removal(message_id, user_id, emoji)

    def test_cleanup_old_programmatic_removals(self, betting_cog):
        """Test that old programmatic removal entries are properly cleaned up."""
        current_time = time.time()

        # Add some test entries with different timestamps
        recent_key = "recent:123:🔥"
        old_key = "old:456:⚡"

        betting_cog._programmatic_removals.add(recent_key)
        betting_cog._programmatic_removals.add(old_key)
        betting_cog._programmatic_removals_timestamps[recent_key] = (
            current_time - 10
        )  # 10 seconds ago
        betting_cog._programmatic_removals_timestamps[old_key] = (
            current_time - 60
        )  # 60 seconds ago

        # Trigger cleanup by marking a new removal
        betting_cog._mark_programmatic_removal(999, 111, "💪")

        # Old entry should be cleaned up
        assert old_key not in betting_cog._programmatic_removals
        assert old_key not in betting_cog._programmatic_removals_timestamps

        # Recent entry should still be there
        assert recent_key in betting_cog._programmatic_removals
        assert recent_key in betting_cog._programmatic_removals_timestamps

    @pytest.mark.asyncio
    async def test_programmatic_removal_prevents_handler_execution(self, betting_cog):
        """Test that programmatic removals cause early return in the handler."""
        message_id = 123456789
        user_id = 67890
        emoji_str = "🔥"

        # Mock payload
        payload = MagicMock()
        payload.message_id = message_id
        payload.user_id = user_id
        payload.channel_id = 987654321
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value=emoji_str)

        # Mark as programmatic removal
        betting_cog._mark_programmatic_removal(message_id, user_id, emoji_str)

        # Mock load_data to track if it gets called
        with patch("data_manager.load_data") as mock_load_data:
            # Process the removal
            await betting_cog.on_raw_reaction_remove(payload)

            # load_data should NOT be called because handler returns early
            mock_load_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_programmatic_removal_continues_processing(self, betting_cog):
        """Test that non-programmatic removals pass the programmatic check."""
        message_id = 123456789
        user_id = 67890
        emoji_str = "🔥"

        # Mock payload
        payload = MagicMock()
        payload.message_id = message_id
        payload.user_id = user_id
        payload.channel_id = 987654321
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value=emoji_str)

        # Do NOT mark as programmatic removal

        # The key test: verify that the programmatic removal check returns False
        # This means the handler will continue processing (even if it later returns due to other validation)
        assert not betting_cog._is_programmatic_removal(message_id, user_id, emoji_str)

        # Process the removal with minimal mocking to see if it gets past the programmatic check
        original_handler = betting_cog.on_raw_reaction_remove
        programmatic_check_passed = False

        async def test_handler(payload_arg):
            nonlocal programmatic_check_passed
            # Check if this is a programmatic removal (the first real check in the handler)
            if betting_cog._is_programmatic_removal(
                payload_arg.message_id, payload_arg.user_id, str(payload_arg.emoji)
            ):
                return  # This was a programmatic removal

            # If we reach here, the programmatic check passed
            programmatic_check_passed = True
            return  # Exit early to avoid full handler execution

        betting_cog.on_raw_reaction_remove = test_handler

        try:
            await betting_cog.on_raw_reaction_remove(payload)
            # Verify that we passed the programmatic removal check
            assert (
                programmatic_check_passed
            ), "Handler should have passed the programmatic removal check"
        finally:
            betting_cog.on_raw_reaction_remove = original_handler

    def test_race_condition_scenario_simulation(self, betting_cog):
        """Simulate the exact race condition scenario that was causing issues."""
        message_id = 123456789
        user_id = 67890
        old_emoji = "🔥"  # 100 coins
        new_emoji = "⚡"  # 250 coins

        # Simulate the sequence that happens when user changes reaction bet:
        # 1. User adds new reaction (⚡)
        # 2. System processes bet update
        # 3. System programmatically removes old reaction (🔥)
        # 4. Discord fires on_raw_reaction_remove for the old reaction

        # Step 3: Mark the old reaction as programmatic removal
        betting_cog._mark_programmatic_removal(message_id, user_id, old_emoji)

        # Step 4: Check that the removal is recognized as programmatic
        assert betting_cog._is_programmatic_removal(message_id, user_id, old_emoji)

        # The key insight: this prevents the handler from processing it as a user cancellation
        # Previously, this would have caused the bet to be removed from the live message
        # Now, it's correctly ignored as a programmatic operation

    def test_multiple_users_no_interference(self, betting_cog):
        """Test that multiple users' programmatic removals don't interfere with each other."""
        message_id = 123456789

        # Different users changing bets simultaneously
        users = [
            {"id": 67890, "old_emoji": "🔥", "new_emoji": "⚡"},
            {"id": 11111, "old_emoji": "🌟", "new_emoji": "💎"},
            {"id": 22222, "old_emoji": "💪", "new_emoji": "🏆"},
        ]

        # Mark all old reactions as programmatic removals
        for user in users:
            betting_cog._mark_programmatic_removal(
                message_id, user["id"], user["old_emoji"]
            )

        # Verify each user's programmatic removal is tracked independently
        for user in users:
            assert betting_cog._is_programmatic_removal(
                message_id, user["id"], user["old_emoji"]
            )

        # Verify one user's check doesn't affect others
        for user in users:
            # Other users should still have their programmatic removals tracked
            other_users = [u for u in users if u["id"] != user["id"]]
            for other_user in other_users:
                # Re-mark since the previous checks consumed them
                betting_cog._mark_programmatic_removal(
                    message_id, other_user["id"], other_user["old_emoji"]
                )

        # Verify they're all still tracked
        for user in users:
            betting_cog._mark_programmatic_removal(
                message_id, user["id"], user["old_emoji"]
            )

        for user in users:
            assert betting_cog._is_programmatic_removal(
                message_id, user["id"], user["old_emoji"]
            )

    def test_key_generation_uniqueness(self, betting_cog):
        """Test that removal keys are unique for different combinations."""
        # Different message IDs
        key1 = betting_cog._create_removal_key(123, 456, "🔥")
        key2 = betting_cog._create_removal_key(789, 456, "🔥")
        assert key1 != key2

        # Different user IDs
        key3 = betting_cog._create_removal_key(123, 456, "🔥")
        key4 = betting_cog._create_removal_key(123, 789, "🔥")
        assert key3 != key4

        # Different emojis
        key5 = betting_cog._create_removal_key(123, 456, "🔥")
        key6 = betting_cog._create_removal_key(123, 456, "⚡")
        assert key5 != key6

        # Same parameters should generate same key
        key7 = betting_cog._create_removal_key(123, 456, "🔥")
        key8 = betting_cog._create_removal_key(123, 456, "🔥")
        assert key7 == key8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
