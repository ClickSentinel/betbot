"""
Core reaction betting system tests - focused on essential functionality.
This test suite validates the core reaction betting features without
complex mock infrastructure issues.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import discord

from cogs.reaction_handler import ReactionHandler


class TestReactionSystemCore:
    """Core reaction betting system functionality tests."""

    @pytest.mark.asyncio
    async def test_rapid_reaction_batching_system(self):
        """Test the complete rapid reaction batching flow."""

        # Setup bot and cog
        bot = Mock()  # Use Mock instead of AsyncMock
        bot.user = Mock()
        bot.user.id = 99999  # Different from test user

        cog = ReactionHandler(bot)

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

        mock_user = Mock()
        mock_user.id = 123
        # Add roles for permission checking
        mock_role = Mock()
        mock_role.name = 'betboy'
        mock_user.roles = [mock_role]

        # Mock message.reactions to simulate user having previous reactions
        # The test simulates rapid clicking of 🔥, ⚡, 💪, then 🌟
        # So the message should appear to have reactions for 🔥, ⚡, 💪 from user 123
        mock_reactions = []
        for emoji in ["🔥", "⚡", "💪"]:
            mock_reaction = Mock()
            mock_reaction.emoji = emoji
            # Mock the async iterator to return the test user
            async def mock_users():
                yield mock_user
            mock_reaction.users = mock_users
            mock_reactions.append(mock_reaction)
        mock_message.reactions = mock_reactions

        async def mock_fetch_user(user_id):
            return mock_user
        
        cog.bot.get_channel = Mock(return_value=mock_channel)
        cog.bot.get_user = Mock(return_value=None)  # Force it to use fetch_user
        cog.bot.fetch_user = mock_fetch_user

        # Mock set_bet to actually modify the data
        def mock_set_bet(data, session_id, user_id, bet_info):
            """Mock that simulates real bet processing."""
            # Ensure user_id is string for data access
            user_id_str = str(user_id)
            # Directly modify the data
            if session_id:
                session = data.setdefault("betting_sessions", {}).setdefault(session_id, {})
                session.setdefault("bets", {})
                session["bets"][user_id_str] = bet_info
            else:
                data["betting"].setdefault("bets", {})
                data["betting"]["bets"][user_id_str] = bet_info

            # Update balance
            amount = bet_info["amount"]
            if data["balances"].get(user_id_str, 0) >= amount:
                data["balances"][user_id_str] -= amount
                return True
            return False

        with patch("cogs.reaction_handler.load_data", return_value=mock_data), patch(
            "cogs.reaction_handler.save_data"
        ), patch("cogs.reaction_handler.schedule_live_message_update"), patch(
            "cogs.reaction_handler.ensure_user"
        ), patch("cogs.reaction_handler.set_bet", side_effect=mock_set_bet):

            # Simulate a series of rapid reactions
            payload_fire = MagicMock()
            payload_fire.user_id = 123
            payload_fire.message_id = 999
            payload_fire.channel_id = 888
            payload_fire.emoji = "🔥"

            payload_thunder = MagicMock()
            payload_thunder.user_id = 123
            payload_thunder.message_id = 999
            payload_thunder.channel_id = 888
            payload_thunder.emoji = "⚡"

            payload_fist = MagicMock()
            payload_fist.user_id = 123
            payload_fist.message_id = 999
            payload_fist.channel_id = 888
            payload_fist.emoji = "💪"

            payload_star = MagicMock()
            payload_star.user_id = 123
            payload_star.message_id = 999
            payload_star.channel_id = 888
            payload_star.emoji = "🌟"

            # Fire! (test user 123 clicks 🔥)
            await cog.on_raw_reaction_add(payload_fire)
            # Thunder! (test user 123 clicks ⚡)
            await cog.on_raw_reaction_add(payload_thunder)
            # Fist! (test user 123 clicks 💪)
            await cog.on_raw_reaction_add(payload_fist)
            # Star! (test user 123 clicks 🌟)
            await cog.on_raw_reaction_add(payload_star)

            # Wait for batching to complete
            await asyncio.sleep(2.0)

            # Verify only final reaction was processed
            assert "123" in mock_data["betting"]["bets"]
            final_bet = mock_data["betting"]["bets"]["123"]
            assert final_bet["choice"] == "Bob"  # 🌟 is for Bob
            assert final_bet["amount"] == 100  # 🌟 is 100 coins
            assert final_bet["emoji"] == "🌟"

            # Verify balance deducted correctly
            assert mock_data["balances"]["123"] == 900  # 1000 - 100

            print("✅ Rapid reaction batching test passed")

    @pytest.mark.asyncio
    async def test_insufficient_balance_handling(self):
        """Test insufficient balance prevents bet and removes reactions."""

        bot = AsyncMock()
        bot.user = Mock()
        bot.user.id = 99999

        cog = ReactionHandler(bot)

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

        with patch("cogs.reaction_handler.load_data", return_value=mock_data), patch(
            "cogs.reaction_handler.save_data"
        ), patch("cogs.reaction_handler.schedule_live_message_update"), patch(
            "cogs.reaction_handler.ensure_user"
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

        cog = ReactionHandler(bot)

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

        with patch("cogs.reaction_handler.load_data", return_value=mock_data):

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

        cog = ReactionHandler(bot)

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
            channel, data, user_id, amount, choice, emoji, notify_user=True, session_id=None
        ):
            nonlocal bet_processed
            user_id_str = str(user_id)

            if data["balances"][user_id_str] >= amount:
                data["balances"][user_id_str] -= amount
                from data_manager import set_bet
                from utils.bet_state import make_bet_info
                set_bet(data, session_id, user_id_str, make_bet_info(amount, choice, emoji))
                bet_processed = True
                return True
            return False

        with patch("cogs.reaction_handler.load_data", return_value=mock_data), patch(
            "cogs.reaction_handler.save_data"
        ), patch("cogs.reaction_handler.schedule_live_message_update"), patch(
            "cogs.reaction_handler.ensure_user"
        ), patch("cogs.bet_utils.BetUtils._process_bet", side_effect=mock_process_bet):
            # Create a mock payload
            payload = MagicMock()
            payload.user_id = 456
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = "🔥"  # Bet amount emoji

            # Simulate primary processing failure by not calling _process_bet
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
