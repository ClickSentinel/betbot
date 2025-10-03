"""
Core reaction betting system tests - focused on essential functionality.
This test suite validates the core reaction betting features without
complex mock infrastructure issues.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
import discord

from cogs.betting import Betting


class TestReactionSystemCore:
    """Core reaction betting system functionality tests."""

    @pytest.mark.asyncio
    async def test_rapid_reaction_batching_system(self):
        """Test the complete rapid reaction batching flow."""

        # Setup bot and cog
        bot = AsyncMock()
        bot.user = Mock()
        bot.user.id = 99999  # Different from test user

        cog = Betting(bot)

        # Mock data - matches production format
        mock_data = {
            "betting": {
                "open": True,
                "contestants": {"1": "Alice", "2": "Bob"},
                "bets": {},
            },
            "balances": {"123": 1000},
            "live_message": 999,
            "live_channel": 888,
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

        # Setup proper async mocks for Discord API calls
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_channel.id = 888
        mock_message = AsyncMock()
        mock_message.id = 999
        mock_message.channel = mock_channel
        mock_message.remove_reaction = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_channel.send = AsyncMock()  # For error messages

        mock_user = AsyncMock()
        mock_user.id = 123

        cog.bot.get_channel = Mock(return_value=mock_channel)
        cog.bot.fetch_user = AsyncMock(return_value=mock_user)

        # Mock _process_bet to actually modify the data
        async def mock_process_bet(
            channel, data, user_id, amount, choice, emoji, notify_user=True
        ):
            """Mock that simulates real bet processing."""
            user_id_str = str(user_id)

            if data["balances"][user_id_str] >= amount:
                data["balances"][user_id_str] -= amount
                data["betting"]["bets"][user_id_str] = {
                    "choice": choice.lower(),
                    "amount": amount,
                    "emoji": emoji,
                }
                return True
            return False

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.schedule_live_message_update"), patch(
            "cogs.betting.ensure_user"
        ), patch.object(
            cog, "_process_bet", side_effect=mock_process_bet
        ):

            # Test 1: Rapid reactions should batch correctly
            reactions = ["🔥", "⚡", "💪", "🌟"]  # Mix of contestants and amounts

            # Simulate rapid clicking
            for emoji in reactions:
                payload = Mock()
                payload.user_id = 123
                payload.message_id = 999
                payload.channel_id = 888
                payload.emoji = emoji

                await cog.on_raw_reaction_add(payload)
                await asyncio.sleep(0.1)  # Rapid but not instant

            # Wait for batching to complete
            await asyncio.sleep(2.0)

            # Verify only final reaction was processed
            assert "123" in mock_data["betting"]["bets"]
            final_bet = mock_data["betting"]["bets"]["123"]
            assert final_bet["choice"] == "bob"  # 🌟 is for Bob
            assert final_bet["amount"] == 100  # 🌟 is 100 coins
            assert final_bet["emoji"] == "🌟"

            # Verify balance deducted correctly
            assert mock_data["balances"]["123"] == 900  # 1000 - 100

            # Verify reaction cleanup was called
            assert (
                mock_message.remove_reaction.call_count >= 3
            )  # Other reactions removed

            print("✅ Rapid reaction batching test passed")

    @pytest.mark.asyncio
    async def test_insufficient_balance_handling(self):
        """Test insufficient balance prevents bet and removes reactions."""

        bot = AsyncMock()
        bot.user = Mock()
        bot.user.id = 99999

        cog = Betting(bot)

        # Mock data with low balance
        mock_data = {
            "betting": {
                "open": True,
                "contestants": {"1": "Alice", "2": "Bob"},
                "bets": {},
            },
            "balances": {"123": 50},  # Only 50 coins
            "live_message": 999,
            "live_channel": 888,
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

        # Setup mocks
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_channel.id = 888
        mock_message = AsyncMock()
        mock_message.remove_reaction = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_channel.send = AsyncMock()

        mock_user = AsyncMock()
        mock_user.id = 123

        cog.bot.get_channel = Mock(return_value=mock_channel)
        cog.bot.fetch_user = AsyncMock(return_value=mock_user)

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.schedule_live_message_update"), patch(
            "cogs.betting.ensure_user"
        ):

            # Try to bet 100 coins with only 50 available
            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = "🔥"  # 100 coin bet

            await cog.on_raw_reaction_add(payload)

            # Should immediately handle insufficient balance
            # (No need to wait for timer as it's handled immediately)

            # Verify no bet was created
            assert "123" not in mock_data["betting"]["bets"]

            # Verify balance unchanged
            assert mock_data["balances"]["123"] == 50

            # Verify error message sent
            assert mock_channel.send.called

            print("✅ Insufficient balance handling test passed")

    @pytest.mark.asyncio
    async def test_betting_closed_prevents_bets(self):
        """Test that closed betting prevents new bets."""

        bot = AsyncMock()
        bot.user = Mock()
        bot.user.id = 99999

        cog = Betting(bot)

        # Mock data with betting closed
        mock_data = {
            "betting": {
                "open": False,  # Betting is closed
                "contestants": {"1": "Alice", "2": "Bob"},
                "bets": {},
            },
            "balances": {"123": 1000},
            "live_message": 999,
            "live_channel": 888,
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

        # Setup mocks
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_message = AsyncMock()
        mock_message.remove_reaction = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_user = AsyncMock()
        mock_user.id = 123

        cog.bot.get_channel = Mock(return_value=mock_channel)
        cog.bot.fetch_user = AsyncMock(return_value=mock_user)

        with patch("cogs.betting.load_data", return_value=mock_data):

            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = "🔥"

            await cog.on_raw_reaction_add(payload)

            # Should immediately remove reaction since betting is closed
            assert mock_message.remove_reaction.called

            # No bet should be created
            assert "123" not in mock_data["betting"]["bets"]

            print("✅ Betting closed prevention test passed")

    @pytest.mark.asyncio
    async def test_backup_timer_system(self):
        """Test that backup timer works when primary fails."""

        bot = AsyncMock()
        bot.user = Mock()
        bot.user.id = 99999

        cog = Betting(bot)

        # Mock data
        mock_data = {
            "betting": {
                "open": True,
                "contestants": {"1": "Alice", "2": "Bob"},
                "bets": {},
            },
            "balances": {"456": 1000},  # Different user ID
            "live_message": 999,
            "live_channel": 888,
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

        # Setup mocks
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_message = AsyncMock()
        mock_message.remove_reaction = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_user = AsyncMock()
        mock_user.id = 456

        cog.bot.get_channel = Mock(return_value=mock_channel)
        cog.bot.fetch_user = AsyncMock(return_value=mock_user)

        # Mock _process_bet to actually modify the data
        bet_processed = False

        async def mock_process_bet(
            channel, data, user_id, amount, choice, emoji, notify_user=True
        ):
            nonlocal bet_processed
            user_id_str = str(user_id)

            if data["balances"][user_id_str] >= amount:
                data["balances"][user_id_str] -= amount
                data["betting"]["bets"][user_id_str] = {
                    "choice": choice.lower(),
                    "amount": amount,
                    "emoji": emoji,
                }
                bet_processed = True
                return True
            return False

        with patch("cogs.betting.load_data", return_value=mock_data), patch(
            "cogs.betting.save_data"
        ), patch("cogs.betting.schedule_live_message_update"), patch(
            "cogs.betting.ensure_user"
        ), patch.object(
            cog, "_process_bet", side_effect=mock_process_bet
        ):

            # Manually add a pending bet (simulating primary timer failure)
            cog._pending_reaction_bets[456] = {
                "message": mock_message,
                "user": mock_user,
                "data": mock_data,
                "contestant_name": "Alice",
                "bet_amount": 250,
                "emoji": "⚡",
                "channel": mock_channel,
            }

            # Start only backup processing (no primary timer)
            asyncio.create_task(
                cog._backup_reaction_processing(456, 1.0)
            )  # Shorter delay for testing

            # Wait for backup to trigger
            await asyncio.sleep(1.5)

            # Verify backup processed the bet
            assert bet_processed, "Backup processing should have processed the bet"
            assert "456" in mock_data["betting"]["bets"]
            assert mock_data["betting"]["bets"]["456"]["choice"] == "alice"
            assert mock_data["betting"]["bets"]["456"]["amount"] == 250

            print("✅ Backup timer system test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
