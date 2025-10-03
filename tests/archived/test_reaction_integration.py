"""
Integration tests for reaction betting that simulate real Discord.py behavior patterns.

These tests focus on realistic scenarios that could occur in production,
including Discord API rate limits, network delays, and edge cases.
"""

import pytest
import asyncio
import time
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, call

# Add the parent directory to Python path to import betbot modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from cogs.betting import Betting as BettingCog
    import discord
except ImportError:
    # For when running tests independently
    BettingCog = MagicMock
    discord = MagicMock


class TestReactionBettingIntegration:
    """Integration tests simulating real Discord.py scenarios."""

    @pytest.fixture
    def mock_bot(self):
        """Create a realistic mock bot."""
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 123456789
        return bot

    @pytest.fixture
    def betting_cog(self, mock_bot):
        """Create betting cog with realistic setup."""
        cog = BettingCog(mock_bot)
        # Initialize tracking structures
        cog._pending_bets = {}
        cog._active_timers = {}
        cog._users_in_cleanup = set()
        cog._deferred_reactions = {}
        cog._last_enforcement = {}
        cog._reaction_sequence = 0
        return cog

    @pytest.fixture
    def realistic_data(self):
        """Create realistic betting data matching production structure."""
        return {
            "balances": {
                "223872195036839936": 10000,  # Real user ID format
                "445566778899001122": 8500,
                "998877665544332211": 15000,
            },
            "betting": {
                "open": True,
                "locked": False,
                "bets": {},
                "contestants": {"1": "Alice", "2": "Bob"},
            },
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
            "live_message": 1423632708654989457,  # Real message ID format
            "live_channel": 1421853887706562661,  # Real channel ID format
        }

    def create_realistic_payload(
        self, user_id, emoji_str, message_id=1423632708654989457
    ):
        """Create a realistic Discord reaction payload."""
        payload = MagicMock()
        payload.user_id = int(user_id)
        payload.message_id = message_id

        # Create realistic emoji object
        emoji = MagicMock()
        emoji.__str__ = MagicMock(return_value=emoji_str)
        emoji.name = emoji_str
        payload.emoji = emoji

        return payload

    @pytest.mark.asyncio
    async def test_discord_rate_limit_simulation(self, betting_cog, realistic_data):
        """Test behavior when Discord API hits rate limits during reaction removal."""
        user_id = "223872195036839936"

        # Mock message with rate limit on remove_reaction
        mock_message = AsyncMock()
        mock_message.id = 1423632708654989457

        # Simulate rate limit error on first few attempts
        rate_limit_error = discord.HTTPException(
            response=MagicMock(status=429), message="Too Many Requests"
        )

        remove_calls = []

        async def mock_remove_reaction(emoji, user):
            remove_calls.append((str(emoji), user.id))
            if len(remove_calls) <= 2:  # First 2 calls hit rate limit
                raise rate_limit_error
            # Subsequent calls succeed
            return

        mock_message.remove_reaction = mock_remove_reaction

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ), patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel, patch(
            "cogs.betting._get_contestant_from_emoji", return_value="1"
        ):

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Mock user object
            mock_user = MagicMock()
            mock_user.id = int(user_id)
            mock_user.name = "TestUser"

            # Test reaction removal with rate limits
            await betting_cog._remove_user_betting_reactions(
                mock_message, mock_user, realistic_data, exclude_emoji="🏆"
            )

            # Should have attempted to remove reactions despite rate limits
            assert len(remove_calls) >= 2  # At least the rate-limited attempts

    @pytest.mark.asyncio
    async def test_message_deletion_during_processing(
        self, betting_cog, realistic_data
    ):
        """Test handling when the live message gets deleted during reaction processing."""
        user_id = "223872195036839936"

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ), patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel, patch(
            "cogs.betting._get_contestant_from_emoji", return_value="1"
        ):

            # Mock channel that raises NotFound when fetching message
            mock_channel = AsyncMock()
            mock_channel.fetch_message.side_effect = discord.NotFound(
                response=MagicMock(status=404), message="Message not found"
            )
            mock_get_channel.return_value = mock_channel

            # Create reaction payload
            payload = self.create_realistic_payload(user_id, "🔥")

            # Should handle gracefully without crashing
            await betting_cog.on_raw_reaction_add(payload)

            # Should not have created pending bet due to message not found
            assert len(betting_cog._pending_bets) == 0

    @pytest.mark.asyncio
    async def test_network_delays_and_timeouts(self, betting_cog, realistic_data):
        """Test system resilience with network delays and timeouts."""
        user_id = "223872195036839936"

        # Mock slow network responses
        mock_message = AsyncMock()
        mock_message.id = 1423632708654989457

        async def slow_remove_reaction(emoji, user):
            await asyncio.sleep(0.5)  # Simulate network delay
            return

        mock_message.remove_reaction = slow_remove_reaction

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ), patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel, patch(
            "cogs.betting._get_contestant_from_emoji", return_value="1"
        ):

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Rapid reactions during slow network
            payload1 = self.create_realistic_payload(user_id, "🔥")
            payload2 = self.create_realistic_payload(user_id, "⚡")

            # Fire reactions quickly
            await betting_cog.on_raw_reaction_add(payload1)
            await asyncio.sleep(0.1)
            await betting_cog.on_raw_reaction_add(payload2)

            # Wait for processing with network delays
            await asyncio.sleep(3.0)

            # Should still work correctly despite delays
            assert len(betting_cog._pending_bets) == 0
            assert len(betting_cog._active_timers) == 0

    @pytest.mark.asyncio
    async def test_channel_permissions_error(self, betting_cog, realistic_data):
        """Test handling when bot lacks permissions to remove reactions."""
        user_id = "223872195036839936"

        mock_message = AsyncMock()
        mock_message.id = 1423632708654989457

        # Simulate permission error
        permission_error = discord.HTTPException(
            response=MagicMock(status=403), message="Missing Permissions"
        )
        mock_message.remove_reaction.side_effect = permission_error

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ), patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel, patch(
            "cogs.betting._get_contestant_from_emoji", return_value="1"
        ):

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            mock_user = MagicMock()
            mock_user.id = int(user_id)
            mock_user.name = "TestUser"

            # Should handle permission errors gracefully
            await betting_cog._remove_user_betting_reactions(
                mock_message, mock_user, realistic_data, exclude_emoji="🏆"
            )

            # Should not crash despite permission errors

    @pytest.mark.asyncio
    async def test_concurrent_bet_processing_race_condition(
        self, betting_cog, realistic_data
    ):
        """Test race conditions when multiple users' bets process simultaneously."""
        user_ids = ["223872195036839936", "445566778899001122", "998877665544332211"]

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ) as mock_save, patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel, patch(
            "cogs.betting._get_contestant_from_emoji", return_value="1"
        ):

            mock_message = AsyncMock()
            mock_message.remove_reaction = AsyncMock()
            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # All users react simultaneously
            tasks = []
            for user_id in user_ids:
                payload = self.create_realistic_payload(user_id, "🔥")
                task = asyncio.create_task(betting_cog.on_raw_reaction_add(payload))
                tasks.append(task)

            # Execute concurrently
            await asyncio.gather(*tasks)

            # Wait for all processing
            await asyncio.sleep(3.0)

            # All should be processed without data corruption
            assert len(betting_cog._pending_bets) == 0
            assert len(betting_cog._active_timers) == 0

            # Data should have been saved multiple times safely
            assert mock_save.call_count >= len(user_ids)

    @pytest.mark.asyncio
    async def test_emoji_parsing_edge_cases(self, betting_cog, realistic_data):
        """Test handling of various emoji formats and edge cases."""
        user_id = "223872195036839936"

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ), patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_message = AsyncMock()
            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Test various emoji formats
            emoji_variations = [
                "🔥",  # Standard unicode emoji
                "<:custom:123>",  # Custom Discord emoji
                "🏆",  # Emoji with skin tone modifiers
                "❤️",  # Emoji with variation selector
            ]

            for emoji_str in emoji_variations:
                payload = self.create_realistic_payload(user_id, emoji_str)

                # Should handle all formats without crashing
                await betting_cog.on_raw_reaction_add(payload)
                await asyncio.sleep(0.1)

            # Wait for processing
            await asyncio.sleep(2.0)

    @pytest.mark.asyncio
    async def test_bot_restart_state_recovery(self, betting_cog, realistic_data):
        """Test that system handles state after bot restart gracefully."""
        user_id = "223872195036839936"

        # Simulate state that might exist after bot restart
        betting_cog._pending_bets = {
            user_id: {
                "amount": 100,
                "choice": "Alice",
                "emoji": "🔥",
                "sequence": 1,
                "timestamp": time.time() - 10,  # Old timestamp
            }
        }

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ), patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel, patch(
            "cogs.betting._get_contestant_from_emoji", return_value="1"
        ):

            mock_message = AsyncMock()
            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # New reaction after restart
            payload = self.create_realistic_payload(user_id, "⚡")
            await betting_cog.on_raw_reaction_add(payload)

            # Should handle gracefully and update state
            await asyncio.sleep(2.0)

            # Old state should be cleaned up
            assert len(betting_cog._pending_bets) == 0

    @pytest.mark.asyncio
    async def test_memory_pressure_large_scale(self, betting_cog, realistic_data):
        """Test system behavior under memory pressure with large user counts."""
        # Simulate large number of users
        num_users = 100

        # Add users to data
        for i in range(num_users):
            user_id = 1000000 + i  # Use proper integer user IDs
            realistic_data["balances"][str(user_id)] = 10000

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ), patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel, patch(
            "cogs.betting._get_contestant_from_emoji", return_value="1"
        ):

            mock_message = AsyncMock()
            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # All users react in waves
            for wave in range(5):  # 5 waves of reactions
                tasks = []
                for i in range(0, num_users, 5):  # 20 users per wave
                    user_id = 1000000 + i  # Use proper integer user IDs
                    emoji = ["🔥", "⚡", "💪", "🏆"][wave % 4]
                    payload = self.create_realistic_payload(user_id, emoji)
                    task = asyncio.create_task(betting_cog.on_raw_reaction_add(payload))
                    tasks.append(task)

                await asyncio.gather(*tasks)
                await asyncio.sleep(0.5)  # Small delay between waves

            # Wait for all processing
            await asyncio.sleep(5.0)

            # System should still be stable
            assert len(betting_cog._pending_bets) == 0
            assert len(betting_cog._active_timers) == 0
            assert len(betting_cog._users_in_cleanup) == 0

    @pytest.mark.asyncio
    async def test_logging_system_stress(self, betting_cog, realistic_data):
        """Test that logging system handles high volume without performance issues."""
        user_id = "223872195036839936"

        with patch("cogs.betting.load_data", return_value=realistic_data), patch(
            "cogs.betting.save_data"
        ), patch(
            "cogs.betting.get_live_message_info",
            return_value=(1423632708654989457, 1421853887706562661),
        ), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel, patch(
            "cogs.betting._get_contestant_from_emoji", return_value="1"
        ), patch.object(
            betting_cog, "_log_reaction_debug"
        ) as mock_log:

            mock_message = AsyncMock()
            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Generate high volume of reactions to stress logging
            for i in range(50):
                emoji = ["🔥", "⚡", "💪", "🏆"][i % 4]
                payload = self.create_realistic_payload(user_id, emoji)
                await betting_cog.on_raw_reaction_add(payload)
                await asyncio.sleep(0.02)  # Very rapid reactions

            # Wait for processing
            await asyncio.sleep(3.0)

            # Logging should have been called many times without issues
            assert mock_log.call_count > 50  # Should have logged extensively


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
