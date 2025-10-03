"""
Tests for handling multiple rapid reactions from the same user.
Ensures that only the last reaction is processed and all others are removed.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from betbot.cogs.betting import Betting
from tests.conftest import setup_member_with_role


@pytest.mark.asyncio
class TestMultipleReactions:
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot."""
        bot = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 12345
        bot.loop = asyncio.get_event_loop()
        return bot
    
    @pytest.fixture
    def betting_cog(self, mock_bot):
        """Create betting cog instance."""
        return Betting(mock_bot)
    
    @pytest.fixture
    def test_data(self):
        """Create test data with an active betting round."""
        return {
            "balances": {
                "67890": 2000  # Enough for multiple bets
            },
            "betting": {
                "open": True,
                "locked": False,
                "bets": {},
                "contestants": {"1": "alice", "2": "bob"}
            },
            "settings": {
                "enable_bet_timer": True,
                "bet_channel_id": None
            },
            "reaction_bet_amounts": {
                "🔥": 100,  # contestant 1
                "⚡": 250,  # contestant 1
                "💪": 500,  # contestant 1
                "🏆": 1000, # contestant 1
                "🌟": 100,  # contestant 2
                "💎": 250,  # contestant 2
                "🚀": 500,  # contestant 2
                "👑": 1000  # contestant 2
            },
            "contestant_1_emojis": ["🔥", "⚡", "💪", "🏆"],
            "contestant_2_emojis": ["🌟", "💎", "🚀", "👑"],
            "live_message": 123456789,
            "live_channel": 987654321,
            "live_secondary_message": None,
            "live_secondary_channel": None,
            "timer_end_time": None
        }
    
    def create_mock_payload(self, user_id, message_id, channel_id, emoji_str):
        """Create a mock reaction payload."""
        payload = MagicMock()
        payload.user_id = user_id
        payload.message_id = message_id
        payload.channel_id = channel_id
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value=emoji_str)
        return payload
    
    def setup_mock_discord_objects(self, betting_cog, user_id, message_id, channel_id):
        """Setup mock Discord objects for testing."""
        # Mock user
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.name = "testuser"
        
        # Mock message
        mock_message = AsyncMock()
        mock_message.id = message_id
        mock_message.add_reaction = AsyncMock()
        mock_message.remove_reaction = AsyncMock()
        
        # Mock channel
        mock_channel = AsyncMock()
        mock_channel.id = channel_id
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_channel.send = AsyncMock()
        
        # Setup bot mocks
        betting_cog.bot.get_channel = MagicMock(return_value=mock_channel)
        betting_cog.bot.fetch_user = AsyncMock(return_value=mock_user)
        
        return mock_user, mock_message, mock_channel
    
    async def test_reaction_batching_methods_directly(self, betting_cog, test_data):
        """Test the reaction batching methods directly without going through the full event pipeline."""
        user_id = 67890
        message_id = 123456789
        channel_id = 987654321
        
        # Setup mock objects
        mock_user, mock_message, mock_channel = self.setup_mock_discord_objects(
            betting_cog, user_id, message_id, channel_id
        )
        
        # Test that we can store a pending bet
        betting_cog._pending_reaction_bets[user_id] = {
            "message": mock_message,
            "user": mock_user,
            "data": test_data,
            "contestant_name": "alice",
            "bet_amount": 100,
            "emoji": "🔥",
            "channel": mock_channel
        }
        
        # Test that we can create a timer
        betting_cog._reaction_timers[user_id] = asyncio.create_task(
            betting_cog._delayed_reaction_processing(user_id)
        )
        
        # Verify the batching system is set up
        assert user_id in betting_cog._pending_reaction_bets
        assert user_id in betting_cog._reaction_timers
        
        # Test timer cancellation
        betting_cog._cancel_user_reaction_timer(user_id)
        assert user_id not in betting_cog._reaction_timers
        
        # Verify pending bet is still there (only timer should be removed)
        assert user_id in betting_cog._pending_reaction_bets
    
    async def test_process_batched_reaction_success(self, betting_cog, test_data):
        """Test successful processing of a batched reaction."""
        user_id = 67890
        
        # Setup mock objects
        mock_user, mock_message, mock_channel = self.setup_mock_discord_objects(
            betting_cog, user_id, 123456789, 987654321
        )
        
        # Mock the process_bet method
        betting_cog._process_bet = AsyncMock(return_value=True)
        betting_cog._remove_user_betting_reactions = AsyncMock()
        
        # Set up a pending bet
        betting_cog._pending_reaction_bets[user_id] = {
            "message": mock_message,
            "user": mock_user, 
            "data": test_data,
            "contestant_name": "alice",
            "bet_amount": 100,
            "emoji": "🔥",
            "channel": mock_channel
        }
        
        # Process the batched reaction
        await betting_cog._process_batched_reaction(user_id)
        
        # Verify _process_bet was called with correct parameters
        betting_cog._process_bet.assert_called_once()
        call_kwargs = betting_cog._process_bet.call_args[1] 
        assert call_kwargs["user_id"] == str(user_id)
        assert call_kwargs["amount"] == 100
        assert call_kwargs["choice"] == "alice"
        assert call_kwargs["emoji"] == "🔥"
        
        # Verify reaction cleanup was attempted
        betting_cog._remove_user_betting_reactions.assert_called_once()
        
        # Verify pending bet was cleaned up
        assert user_id not in betting_cog._pending_reaction_bets
    
    async def test_delayed_reaction_processing_cancellation(self, betting_cog, test_data):
        """Test that delayed reaction processing handles cancellation correctly."""
        user_id = 67890
        
        # Start a delayed reaction processing task
        task = asyncio.create_task(betting_cog._delayed_reaction_processing(user_id))
        betting_cog._reaction_timers[user_id] = task
        
        # Set up a pending bet that should be cleaned up on cancellation
        betting_cog._pending_reaction_bets[user_id] = {
            "message": MagicMock(),
            "user": MagicMock(),
            "data": test_data,
            "contestant_name": "alice",
            "bet_amount": 100,
            "emoji": "🔥",
            "channel": MagicMock()
        }
        
        # Cancel the task after a brief moment to simulate rapid new reactions
        await asyncio.sleep(0.1)  # Let the task start
        task.cancel()
        
        # Wait for the cancellation to be processed
        try:
            await task
        except asyncio.CancelledError:
            pass  # This is expected
        
        # Verify cleanup occurred - the pending bet should be cleaned up
        # since the CancelledError handler should remove it
        assert user_id not in betting_cog._pending_reaction_bets
    
    async def test_process_batched_reaction_failure(self, betting_cog, test_data):
        """Test handling of failed bet processing in batched reactions."""
        user_id = 67890
        
        # Setup mock objects
        mock_user, mock_message, mock_channel = self.setup_mock_discord_objects(
            betting_cog, user_id, 123456789, 987654321
        )
        
        # Mock _process_bet to return failure
        betting_cog._process_bet = AsyncMock(return_value=False)
        betting_cog._remove_user_betting_reactions = AsyncMock()
        
        # Set up a pending bet
        betting_cog._pending_reaction_bets[user_id] = {
            "message": mock_message,
            "user": mock_user,
            "data": test_data,
            "contestant_name": "alice", 
            "bet_amount": 100,
            "emoji": "🔥",
            "channel": mock_channel
        }
        
        # Process the batched reaction
        await betting_cog._process_batched_reaction(user_id)
        
        # Verify _process_bet was called
        betting_cog._process_bet.assert_called_once()
        
        # Verify all reactions were removed (including the failed one)
        betting_cog._remove_user_betting_reactions.assert_called_once_with(
            mock_message, mock_user, test_data, exclude_emoji=None
        )
        
        # Verify pending bet was cleaned up
        assert user_id not in betting_cog._pending_reaction_bets


if __name__ == "__main__":
    pytest.main([__file__, "-v"])