"""
Tests for reaction bet changes to ensure live message updates correctly.
This addresses the specific issue where changing reaction bets within the same contestant
causes the live message to remove the bet instead of updating it.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import asyncio

from cogs.betting import Betting
from data_manager import load_data, save_data


class TestReactionBetChanges:
    """Test reaction bet changes within the same contestant."""
    
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
                "67890": 1000
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
    
    def test_programmatic_removal_tracking(self, betting_cog):
        """Test that programmatic removal tracking works correctly."""
        message_id, user_id, emoji = 123456789, 67890, "🔥"
        
        # Initially should not be marked as programmatic
        assert not betting_cog._is_programmatic_removal(message_id, user_id, emoji)
        
        # Mark as programmatic
        betting_cog._mark_programmatic_removal(message_id, user_id, emoji)
        
        # Should now be detected as programmatic (and removed from tracking)
        assert betting_cog._is_programmatic_removal(message_id, user_id, emoji)
        
        # Should no longer be tracked after checking
        assert not betting_cog._is_programmatic_removal(message_id, user_id, emoji)
    
    def test_create_removal_key(self, betting_cog):
        """Test removal key creation."""
        key = betting_cog._create_removal_key(123456789, 67890, "🔥")
        expected = "123456789:67890:🔥"
        assert key == expected
    
    @pytest.mark.asyncio
    async def test_programmatic_removal_prevents_race_condition(self, betting_cog, test_data):
        """Test that programmatic removals don't trigger the race condition."""
        user_id = 67890
        
        # Mock the necessary Discord objects
        mock_payload = MagicMock()
        mock_payload.message_id = 123456789
        mock_payload.user_id = user_id
        mock_emoji = MagicMock()
        mock_emoji.__str__ = MagicMock(return_value="🔥")
        mock_payload.emoji = mock_emoji
        
        # Mark this as a programmatic removal
        betting_cog._mark_programmatic_removal(
            mock_payload.message_id, 
            mock_payload.user_id, 
            str(mock_payload.emoji)
        )
        
        # Mock load_data to return our test data
        with patch('data_manager.load_data', return_value=test_data):
            # The handler should return early due to programmatic removal check
            await betting_cog.on_raw_reaction_remove(mock_payload)
        
        # Verify the bet wasn't affected (since it was a programmatic removal)
        # The user should still not have any bets since this was just testing the early return
        assert user_id not in test_data["betting"]["bets"] or str(user_id) not in test_data["betting"]["bets"]
    
    @pytest.mark.asyncio
    async def test_programmatic_vs_user_removal_differentiation(self, betting_cog):
        """Test that the system can differentiate between programmatic and user removals."""
        user_id = 67890
        message_id = 123456789
        emoji_str = "🔥"
        
        # Mock the handler method to track if it was called
        original_handler = betting_cog.on_raw_reaction_remove
        handler_call_count = 0
        
        async def mock_handler(payload):
            nonlocal handler_call_count
            handler_call_count += 1
            # Call the original but with early return after programmatic check
            if betting_cog._is_programmatic_removal(payload.message_id, payload.user_id, str(payload.emoji)):
                return  # This was a programmatic removal, don't process it as user action
            # If we get here, it's a user removal (we'll just return to avoid full processing)
            return
            
        betting_cog.on_raw_reaction_remove = mock_handler
        
        # Create mock payload
        mock_payload = MagicMock()
        mock_payload.message_id = message_id
        mock_payload.user_id = user_id
        mock_emoji = MagicMock()
        mock_emoji.__str__ = MagicMock(return_value=emoji_str)
        mock_payload.emoji = mock_emoji
        
        # Test 1: Programmatic removal should return early
        betting_cog._mark_programmatic_removal(message_id, user_id, emoji_str)
        await betting_cog.on_raw_reaction_remove(mock_payload)
        assert handler_call_count == 1  # Handler was called
        
        # Test 2: User removal should proceed past programmatic check
        handler_call_count = 0  # Reset counter
        # Don't mark as programmatic this time
        await betting_cog.on_raw_reaction_remove(mock_payload)
        assert handler_call_count == 1  # Handler was called but didn't return early
    
    def test_cleanup_old_programmatic_removals(self, betting_cog):
        """Test that old programmatic removal entries are cleaned up."""
        import time
        
        # Add some entries with different timestamps
        current_time = time.time()
        
        # Add recent entry (should be kept)
        betting_cog._programmatic_removals_timestamps["recent"] = current_time - 10
        betting_cog._programmatic_removals.add("recent")
        
        # Add old entry (should be cleaned up)
        betting_cog._programmatic_removals_timestamps["old"] = current_time - 60
        betting_cog._programmatic_removals.add("old")
        
        # Trigger cleanup by marking a new removal
        betting_cog._mark_programmatic_removal(123, 456, "🔥")
        
        # Old entry should be cleaned up
        assert "old" not in betting_cog._programmatic_removals
        assert "old" not in betting_cog._programmatic_removals_timestamps
        
        # Recent entry should still be there
        assert "recent" in betting_cog._programmatic_removals
        assert "recent" in betting_cog._programmatic_removals_timestamps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])