"""
Tests for the reaction batching system to ensure reactions stick correctly
and only the final reaction remains after rapid clicking.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
import discord

from cogs.betting import Betting


@pytest.fixture
def betting_cog():
    """Create a Betting cog instance for testing."""
    bot = AsyncMock()
    bot.user = Mock()
    bot.user.id = 12345  # Bot's user ID

    cog = Betting(bot)
    return cog


@pytest.fixture
def mock_data():
    """Create mock betting data with active round."""
    return {
        "betting": {
            "open": True,
            "contestants": {"1": "Alice", "2": "Bob"},
            "bets": {},
        },
        "balances": {"123": 1000},  # User has 1000 coins
        "live_message": 999,  # Correct key name
        "live_channel": 888,  # Correct key name
        "live_secondary_message": None,
        "live_secondary_channel": None,
        "contestant_1_emojis": ["🔥", "⚡", "💪", "🏆"],
        "contestant_2_emojis": ["🌟", "💎", "🚀", "👑"],
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
    }


@pytest.fixture
def mock_user():
    """Create a mock Discord user."""
    user = AsyncMock()
    user.id = 123
    user.name = "TestUser"
    return user


@pytest.fixture
def mock_message():
    """Create a mock Discord message."""
    message = AsyncMock()
    message.id = 999
    message.channel.id = 888
    message.add_reaction = AsyncMock()
    message.remove_reaction = AsyncMock()
    return message


@pytest.fixture
def mock_channel():
    """Create a mock Discord text channel."""
    channel = AsyncMock(spec=discord.TextChannel)
    channel.id = 888
    channel.send = AsyncMock()
    channel.fetch_message = AsyncMock()
    return channel


class TestReactionBatchingSystem:
    """Test suite for reaction batching functionality."""

    @pytest.mark.asyncio
    async def test_single_reaction_bet_sticks(
        self, betting_cog, mock_data, mock_user, mock_message, mock_channel
    ):
        """Test that a single reaction bet processes correctly and the reaction sticks."""

        # Setup
        mock_channel.fetch_message.return_value = mock_message
        betting_cog.bot.get_channel.return_value = mock_channel
        betting_cog.bot.fetch_user.return_value = mock_user

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.schedule_live_message_update"), patch(
            "cogs.betting.ensure_user"
        ):

            # Create reaction payload
            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = "🔥"

            # Process the reaction
            await betting_cog.on_raw_reaction_add(payload)

            # Wait for batching delay
            await asyncio.sleep(1.1)

            # Verify the user now has a bet
            assert "123" in mock_data["betting"]["bets"]
            bet_info = mock_data["betting"]["bets"]["123"]
            assert bet_info["choice"] == "alice"  # Lowercase
            assert bet_info["amount"] == 100

            # Verify user balance was deducted
            assert mock_data["balances"]["123"] == 900  # 1000 - 100

            # Verify the final emoji was NOT removed (exclude_emoji should prevent it)
            # The remove_reaction calls should only target other emojis
            remove_calls = mock_message.remove_reaction.call_args_list
            final_emoji_removed = any(call[0][0] == "🔥" for call in remove_calls)
            assert not final_emoji_removed, "Final emoji should not be removed"

    @pytest.mark.asyncio
    async def test_rapid_multiple_reactions_only_final_sticks(
        self, betting_cog, mock_data, mock_user, mock_message, mock_channel
    ):
        """Test that when user rapidly clicks multiple reactions, only the final one remains."""

        # Setup
        mock_channel.fetch_message.return_value = mock_message
        betting_cog.bot.get_channel.return_value = mock_channel
        betting_cog.bot.fetch_user.return_value = mock_user

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.schedule_live_message_update"), patch(
            "cogs.betting.ensure_user"
        ):

            # Simulate rapid reactions: 🔥 -> ⚡ -> 💪 -> 🌟
            reactions = ["🔥", "⚡", "💪", "🌟"]  # Different contestants and amounts

            for emoji in reactions:
                payload = Mock()
                payload.user_id = 123
                payload.message_id = 999
                payload.channel_id = 888
                payload.emoji = emoji

                # Process reaction immediately (no delay between them)
                await betting_cog.on_raw_reaction_add(payload)

            # Wait for batching delay
            await asyncio.sleep(1.1)

            # Verify only the final bet was processed
            assert "123" in mock_data["betting"]["bets"]
            bet_info = mock_data["betting"]["bets"]["123"]
            assert bet_info["choice"] == "bob"  # 🌟 is for Bob (contestant 2)
            assert bet_info["amount"] == 100  # 🌟 is 100 coins

            # Verify balance reflects final bet only
            assert (
                mock_data["balances"]["123"] == 900
            )  # 1000 - 100 (not multiple deductions)

            # Verify the older reactions were removed but final one excluded
            remove_calls = mock_message.remove_reaction.call_args_list
            removed_emojis = [call[0][0] for call in remove_calls]

            # Should have removed 🔥, ⚡, 💪 but NOT 🌟
            assert "🔥" in removed_emojis
            assert "⚡" in removed_emojis
            assert "💪" in removed_emojis
            assert "🌟" not in removed_emojis  # Final emoji should be excluded

    @pytest.mark.asyncio
    async def test_insufficient_balance_removes_all_reactions(
        self, betting_cog, mock_data, mock_user, mock_message, mock_channel
    ):
        """Test that when user has insufficient balance, all reactions are removed."""

        # Setup user with low balance
        mock_data["balances"]["123"] = 50  # Not enough for any reaction bet

        mock_channel.fetch_message.return_value = mock_message
        betting_cog.bot.get_channel.return_value = mock_channel
        betting_cog.bot.fetch_user.return_value = mock_user

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.schedule_live_message_update"), patch(
            "cogs.betting.ensure_user"
        ):

            # Try to bet 100 coins with 🔥
            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = "🔥"

            # Process the reaction
            await betting_cog.on_raw_reaction_add(payload)

            # Should immediately remove reaction and not create pending bet
            assert mock_message.remove_reaction.called
            assert 123 not in betting_cog._pending_reaction_bets

            # Should send error message to channel
            assert mock_channel.send.called
            embed_call = mock_channel.send.call_args[1]["embed"]
            assert "Insufficient Funds" in embed_call.title

    @pytest.mark.asyncio
    async def test_betting_locked_removes_reactions(
        self, betting_cog, mock_data, mock_user, mock_message, mock_channel
    ):
        """Test that reactions are removed when betting is locked."""

        # Lock betting
        mock_data["betting"]["open"] = False

        mock_channel.fetch_message.return_value = mock_message
        betting_cog.bot.get_channel.return_value = mock_channel
        betting_cog.bot.fetch_user.return_value = mock_user

        with patch("cogs.betting.load_data", return_value=mock_data):

            # Try to place reaction bet
            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = "🔥"

            # Process the reaction
            await betting_cog.on_raw_reaction_add(payload)

            # Should remove the reaction immediately
            assert mock_message.remove_reaction.called

            # Should not create pending bet
            assert 123 not in betting_cog._pending_reaction_bets

    @pytest.mark.asyncio
    async def test_reaction_removal_cancels_bet(
        self, betting_cog, mock_data, mock_user
    ):
        """Test that manually removing a reaction cancels the bet and refunds coins."""

        # Setup existing bet
        mock_data["betting"]["bets"]["123"] = {
            "choice": "alice",
            "amount": 100,
            "emoji": "🔥",
        }
        mock_data["balances"]["123"] = 900  # Already deducted

        betting_cog.bot.fetch_user.return_value = mock_user

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.schedule_live_message_update"):

            # Create reaction remove payload
            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = "🔥"

            # Mock programmatic removal check to return False (user action)
            betting_cog._is_programmatic_removal = Mock(return_value=False)

            # Process reaction removal
            await betting_cog.on_raw_reaction_remove(payload)

            # Verify bet was cancelled and refund issued
            assert "123" not in mock_data["betting"]["bets"]
            assert mock_data["balances"]["123"] == 1000  # Refunded

    @pytest.mark.asyncio
    async def test_programmatic_removal_ignored(self, betting_cog, mock_data):
        """Test that programmatic reaction removals are ignored to prevent race conditions."""

        with patch("cogs.betting.load_data", return_value=mock_data):

            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = "🔥"

            # Mock programmatic removal check to return True
            betting_cog._is_programmatic_removal = Mock(return_value=True)

            # Process reaction removal
            await betting_cog.on_raw_reaction_remove(payload)

            # Should not fetch user since it's programmatic
            betting_cog.bot.fetch_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_timer_cancellation_on_new_reaction(
        self, betting_cog, mock_data, mock_user, mock_message, mock_channel
    ):
        """Test that new reactions cancel previous timers correctly."""

        # Setup
        mock_channel.fetch_message.return_value = mock_message
        betting_cog.bot.get_channel.return_value = mock_channel
        betting_cog.bot.fetch_user.return_value = mock_user

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.schedule_live_message_update"), patch(
            "cogs.betting.ensure_user"
        ):

            # First reaction
            payload1 = Mock()
            payload1.user_id = 123
            payload1.message_id = 999
            payload1.channel_id = 888
            payload1.emoji = "🔥"

            await betting_cog.on_raw_reaction_add(payload1)

            # Verify timer exists
            assert 123 in betting_cog._reaction_timers
            first_timer = betting_cog._reaction_timers[123]

            # Second reaction (should cancel first timer)
            payload2 = Mock()
            payload2.user_id = 123
            payload2.message_id = 999
            payload2.channel_id = 888
            payload2.emoji = "⚡"

            await betting_cog.on_raw_reaction_add(payload2)

            # Verify first timer was cancelled
            assert first_timer.cancelled()

            # Verify new timer exists
            assert 123 in betting_cog._reaction_timers
            second_timer = betting_cog._reaction_timers[123]
            assert second_timer != first_timer
            assert not second_timer.cancelled()
