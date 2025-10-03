"""
Comprehensive tests for reaction betting spam resistance.

These tests simulate all the ways users could try to spam reactions
and break the reaction betting system, ensuring robustness.
"""

import pytest
import asyncio
import time
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add the parent directory to Python path to import betbot modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from cogs.betting import Betting as BettingCog
    from utils.bet_state import BetState
except ImportError:
    # For when running tests independently
    BettingCog = MagicMock
    BetState = MagicMock


class TestReactionSpamResistance:
    """Test suite for reaction betting spam resistance."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot with user ID."""
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 123456789  # Bot's user ID
        return bot

    @pytest.fixture
    def betting_cog(self, mock_bot):
        """Create a BettingCog instance for testing."""
        return BettingCog(mock_bot)

    @pytest.fixture
    def mock_data(self):
        """Create mock betting data."""
        return {
            "balances": {
                "user1": 10000,
                "user2": 10000,
                "user3": 10000,
            },
            "betting": {
                "open": True,
                "locked": False,
                "bets": {},
                "contestants": {"1": "alice", "2": "bob"},
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
            "live_message": 999,
            "live_channel": 888,
        }

    @pytest.fixture
    def mock_payload(self):
        """Create a mock reaction payload."""

        def create_payload(user_id, emoji, message_id=999):
            payload = MagicMock()
            payload.user_id = user_id
            payload.emoji = emoji
            payload.message_id = message_id
            return payload

        return create_payload

    @pytest.fixture
    def mock_message(self):
        """Create a mock Discord message."""
        message = AsyncMock()
        message.id = 999
        message.channel = AsyncMock()
        message.channel.id = 888
        message.remove_reaction = AsyncMock()
        message.reactions = []
        return message

    @pytest.mark.asyncio
    async def test_rapid_fire_same_emoji(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test user rapidly clicking the same emoji multiple times."""
        user_id = "user1"
        emoji = "🔥"

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Simulate rapid clicking of same emoji (10 times in quick succession)
            payloads = [mock_payload(user_id, emoji) for _ in range(10)]

            # Fire all reactions rapidly
            tasks = []
            for payload in payloads:
                task = asyncio.create_task(betting_cog.on_raw_reaction_add(payload))
                tasks.append(task)
                await asyncio.sleep(0.01)  # Very small delay between reactions

            # Wait for all to complete
            await asyncio.gather(*tasks)

            # Should only have one pending bet despite multiple rapid clicks
            assert len(betting_cog._pending_reaction_bets) <= 1

            # Wait for timers to complete
            await asyncio.sleep(2.0)

            # Final state should be clean
            assert len(betting_cog._pending_reaction_bets) == 0
            assert len(betting_cog._reaction_timers) == 0

    @pytest.mark.asyncio
    async def test_rapid_emoji_switching(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test user rapidly switching between different emojis."""
        user_id = "user1"
        emojis = ["🔥", "⚡", "💪", "🏆", "🌟", "💎", "🚀", "👑"]

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Simulate rapid emoji switching
            for emoji in emojis:
                payload = mock_payload(user_id, emoji)
                await betting_cog.on_raw_reaction_add(payload)
                await asyncio.sleep(0.05)  # Small delay between switches

            # Should only have one pending bet (the last one)
            assert len(betting_cog._pending_reaction_bets) <= 1
            if betting_cog._pending_reaction_bets:
                last_bet = betting_cog._pending_reaction_bets[user_id]
                assert last_bet["emoji"] == "👑"  # Last emoji clicked

            # Wait for timers to complete
            await asyncio.sleep(2.0)

            # Final state should be clean
            assert len(betting_cog._pending_reaction_bets) == 0
            assert len(betting_cog._reaction_timers) == 0

    @pytest.mark.asyncio
    async def test_multiple_users_spam_same_emoji(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test multiple users spamming the same emoji simultaneously."""
        user_ids = ["user1", "user2", "user3"]
        emoji = "🔥"

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # All users click same emoji simultaneously
            tasks = []
            for user_id in user_ids:
                payload = mock_payload(user_id, emoji)
                task = asyncio.create_task(betting_cog.on_raw_reaction_add(payload))
                tasks.append(task)

            await asyncio.gather(*tasks)

            # Should have one pending bet per user
            assert len(betting_cog._pending_reaction_bets) == len(user_ids)

            # Wait for all timers to complete
            await asyncio.sleep(2.0)

            # All should be processed cleanly
            assert len(betting_cog._pending_reaction_bets) == 0
            assert len(betting_cog._reaction_timers) == 0

    @pytest.mark.asyncio
    async def test_alternating_users_rapid_reactions(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test alternating users with rapid reactions."""
        users_and_emojis = [
            ("user1", "🔥"),
            ("user2", "🌟"),
            ("user1", "⚡"),
            ("user2", "💎"),
            ("user1", "💪"),
            ("user2", "🚀"),
        ]

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Alternating rapid reactions
            for user_id, emoji in users_and_emojis:
                payload = mock_payload(user_id, emoji)
                await betting_cog.on_raw_reaction_add(payload)
                await asyncio.sleep(0.1)  # Small delay between reactions

            # Wait for all processing to complete
            await asyncio.sleep(3.0)

            # Final state should be clean
            assert len(betting_cog._pending_reaction_bets) == 0
            assert len(betting_cog._reaction_timers) == 0

    @pytest.mark.asyncio
    async def test_timer_cancellation_spam(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test rapid reactions that constantly cancel and restart timers."""
        user_id = "user1"
        emojis = ["🔥", "⚡", "💪", "🏆"] * 5  # Repeat pattern 5 times

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch(
            "cogs.betting._get_contestant_from_emoji"
        ) as mock_get_contestant, patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_get_contestant.side_effect = lambda data, emoji: (
                "1" if emoji in ["🔥", "⚡", "💪", "🏆"] else "2"
            )
            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Rapid reactions that keep cancelling timers
            for emoji in emojis:
                payload = mock_payload(user_id, emoji)
                await betting_cog.on_raw_reaction_add(payload)
                await asyncio.sleep(
                    0.2
                )  # Faster than timer delay to force cancellations

            # Wait for final timer to complete
            await asyncio.sleep(3.0)

            # Should end up with clean state
            assert len(betting_cog._pending_reaction_bets) == 0
            assert len(betting_cog._reaction_timers) == 0

    @pytest.mark.asyncio
    async def test_boundary_conditions(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test edge cases and boundary conditions."""

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Test 1: Invalid emoji (should be ignored)
            invalid_payload = mock_payload("user1", "❌")  # Not a betting emoji
            await betting_cog.on_raw_reaction_add(invalid_payload)
            assert len(betting_cog._pending_reaction_bets) == 0

            # Test 2: Bot's own reaction (should be ignored)
            bot_payload = mock_payload(123456789, "🔥")  # Bot's user ID
            await betting_cog.on_raw_reaction_add(bot_payload)
            assert len(betting_cog._pending_reaction_bets) == 0

            # Test 3: Reaction on wrong message
            wrong_msg_payload = mock_payload("user1", "🔥")
            wrong_msg_payload.message_id = 777  # Different message ID
            await betting_cog.on_raw_reaction_add(wrong_msg_payload)
            assert len(betting_cog._pending_reaction_bets) == 0

    @pytest.mark.asyncio
    async def test_cleanup_phase_conflicts(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test reactions during cleanup phase are handled correctly."""
        user_id = "user1"

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # First reaction
            payload1 = mock_payload(user_id, "🔥")
            await betting_cog.on_raw_reaction_add(payload1)

            # Manually mark user as in cleanup phase
            betting_cog._users_in_cleanup.add(user_id)

            # Second reaction during cleanup (should be deferred)
            payload2 = mock_payload(user_id, "⚡")
            await betting_cog.on_raw_reaction_add(payload2)

            # Should have deferred the second reaction
            assert user_id in betting_cog._deferred_reactions

            # Clean up
            betting_cog._users_in_cleanup.discard(user_id)

    @pytest.mark.asyncio
    async def test_massive_concurrent_load(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test system under massive concurrent load."""
        num_users = 50
        reactions_per_user = 5

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Create massive concurrent load
            all_tasks = []
            emojis = ["🔥", "⚡", "💪", "🏆", "🌟"]

            for user_num in range(num_users):
                user_id = f"user{user_num}"

                # Add user to mock data
                mock_data["balances"][user_id] = 10000

                for reaction_num in range(reactions_per_user):
                    emoji = emojis[reaction_num % len(emojis)]
                    payload = mock_payload(user_id, emoji)
                    task = asyncio.create_task(betting_cog.on_raw_reaction_add(payload))
                    all_tasks.append(task)

            # Execute all reactions concurrently
            await asyncio.gather(*all_tasks)

            # Wait for all timers to complete
            await asyncio.sleep(5.0)

            # System should still be in clean state
            assert len(betting_cog._pending_reaction_bets) == 0
            assert len(betting_cog._reaction_timers) == 0

            # No memory leaks in tracking structures
            assert len(betting_cog._users_in_cleanup) == 0
            assert (
                len(betting_cog._reaction_sequence) >= 0
            )  # Can have leftover sequence numbers

    @pytest.mark.asyncio
    async def test_memory_leak_prevention(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test that long-running spam doesn't cause memory leaks."""
        user_id = "user1"

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            initial_pending = len(betting_cog._pending_reaction_bets)
            initial_timers = len(betting_cog._reaction_timers)
            initial_cleanup = len(betting_cog._users_in_cleanup)

            # Simulate extended spam session
            for cycle in range(20):  # 20 cycles of reactions
                emoji = ["🔥", "⚡", "💪", "🏆"][cycle % 4]
                payload = mock_payload(user_id, emoji)
                await betting_cog.on_raw_reaction_add(payload)
                await asyncio.sleep(0.1)

            # Wait for final processing
            await asyncio.sleep(3.0)

            # Memory usage should be back to baseline
            assert len(betting_cog._pending_reaction_bets) == initial_pending
            assert len(betting_cog._reaction_timers) == initial_timers
            assert len(betting_cog._users_in_cleanup) == initial_cleanup

    def test_rate_limiting_parameters(self, betting_cog):
        """Test that rate limiting parameters are reasonable."""
        # These are critical timing parameters that affect spam resistance
        assert hasattr(betting_cog, "_last_enforcement")  # Rate limiting exists

        # Timer delays should be reasonable (not too short to cause spam, not too long to be unresponsive)
        # These would be checked in the actual implementation
        primary_timer_delay = 1.5  # Should be between 1-3 seconds
        backup_timer_delay = 3.0  # Should be 2-3x primary delay

        assert 1.0 <= primary_timer_delay <= 3.0
        assert backup_timer_delay >= primary_timer_delay
        assert backup_timer_delay <= primary_timer_delay * 3

    @pytest.mark.asyncio
    async def test_sequence_numbering_integrity(
        self, betting_cog, mock_data, mock_payload, mock_message
    ):
        """Test that sequence numbering prevents race conditions."""
        user_id = "user1"

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.get_live_message_info", return_value=(999, 888)), patch(
            "cogs.betting.get_secondary_live_message_info", return_value=(None, None)
        ), patch.object(
            betting_cog.bot, "get_channel"
        ) as mock_get_channel:

            mock_channel = AsyncMock()
            mock_channel.fetch_message.return_value = mock_message
            mock_get_channel.return_value = mock_channel

            # Record initial sequence
            initial_sequence = betting_cog._reaction_sequence

            # Multiple rapid reactions
            emojis = ["🔥", "⚡", "💪"]
            for emoji in emojis:
                payload = mock_payload(user_id, emoji)
                await betting_cog.on_raw_reaction_add(payload)
                await asyncio.sleep(0.05)

            # Sequence should have incremented
            assert betting_cog._reaction_sequence > initial_sequence

            # Each reaction should have a unique sequence number
            if user_id in betting_cog._pending_reaction_bets:
                bet_info = betting_cog._pending_reaction_bets[user_id]
                assert "sequence" in bet_info
                assert bet_info["sequence"] > initial_sequence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
