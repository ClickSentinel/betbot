"""
Test module for live message functionality.
Tests live message management and scheduling.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import discord
from utils.live_message import (
    get_live_message_info,
    get_secondary_live_message_info,
    clear_live_message_info,
    set_live_message_info,
    set_secondary_live_message_info,
    get_live_message_link,
    initialize_live_message_scheduler,
    get_emoji_config,
    get_reaction_bet_amounts,
)


class TestLiveMessage:
    """Test class for live message functionality."""

    @pytest.fixture
    def test_data(self):
        """Test data structure."""
        return {
            "live_message": 123456789,
            "live_channel": 987654321,
            "live_secondary_message": 111222333,
            "live_secondary_channel": 444555666,
            "emoji_config": {"option_1_emoji": "🔴", "option_2_emoji": "🔵"},
            "reaction_bet_amounts": {"option_1": 100, "option_2": 200},
        }

    def test_get_live_message_info(self, test_data):
        """Test getting live message information."""
        message_id, channel_id = get_live_message_info(test_data)
        assert message_id == 123456789
        assert channel_id == 987654321

    def test_get_secondary_live_message_info(self, test_data):
        """Test getting secondary live message information."""
        message_id, channel_id = get_secondary_live_message_info(test_data)
        assert message_id == 111222333
        assert channel_id == 444555666

    @patch("utils.live_message.save_data")
    def test_set_live_message_info(self, mock_save, test_data):
        """Test setting live message information."""
        message_id = 123456789
        channel_id = 987654321

        set_live_message_info(test_data, message_id, channel_id)

        assert test_data["live_message"] == message_id
        assert test_data["live_channel"] == channel_id
        mock_save.assert_called_once_with(test_data)

    @patch("utils.live_message.save_data")
    def test_set_secondary_live_message_info(self, mock_save, test_data):
        """Test setting secondary live message information."""
        message_id = 111222333
        channel_id = 444555666

        set_secondary_live_message_info(test_data, message_id, channel_id)

        assert test_data["live_secondary_message"] == message_id
        assert test_data["live_secondary_channel"] == channel_id
        mock_save.assert_called_once_with(test_data)

    @patch("utils.live_message.save_data")
    def test_clear_live_message_info(self, mock_save, test_data):
        """Test clearing live message information."""
        clear_live_message_info(test_data)

        assert test_data["live_message"] is None
        assert test_data["live_channel"] is None
        assert test_data["live_secondary_message"] is None
        assert test_data["live_secondary_channel"] is None
        mock_save.assert_called_once_with(test_data)

    def test_get_emoji_config(self, test_data):
        """Test getting emoji configuration."""
        emoji_config = get_emoji_config(test_data)
        assert emoji_config == {"contestant_1_emojis": [], "contestant_2_emojis": []}

    def test_get_reaction_bet_amounts(self, test_data):
        """Test getting reaction bet amounts."""
        amounts = get_reaction_bet_amounts(test_data)
        assert amounts == {"option_1": 100, "option_2": 200}

    def test_get_live_message_link(self, test_data):
        """Test generating live message links."""
        mock_bot = MagicMock()
        mock_bot.user = MagicMock()
        mock_bot.user.id = 12345

        link = get_live_message_link(mock_bot, test_data, True)

        # Should return a string link
        assert isinstance(link, str)
        assert "discord.com" in link

    def test_get_live_message_link_inactive(self, test_data):
        """Test getting message link when inactive."""
        mock_bot = MagicMock()
        test_data["live_message"] = None
        test_data["live_channel"] = None

        link = get_live_message_link(mock_bot, test_data, False)

        # Should handle inactive state gracefully
        assert isinstance(link, str)

    def test_initialize_live_message_scheduler(self):
        """Test initializing live message scheduler."""
        mock_bot = MagicMock()

        # This function should not raise an error
        try:
            initialize_live_message_scheduler(mock_bot)
            success = True
        except Exception:
            success = False

        assert success

    def test_get_live_message_info_missing_data(self):
        """Test getting live message info when data is missing."""
        from typing import cast
        from utils.betting_utils import Data

        empty_data = cast(Data, {})
        message_id, channel_id = get_live_message_info(empty_data)
        assert message_id is None
        assert channel_id is None

    def test_get_emoji_config_missing_data(self):
        """Test getting emoji config when data is missing."""
        from typing import cast
        from utils.betting_utils import Data

        empty_data = cast(Data, {})
        emoji_config = get_emoji_config(empty_data)
        assert isinstance(emoji_config, dict)  # Should return empty dict or default

    def test_get_reaction_bet_amounts_missing_data(self):
        """Test getting reaction bet amounts when data is missing."""
        from typing import cast
        from utils.betting_utils import Data

        empty_data = cast(Data, {})
        amounts = get_reaction_bet_amounts(empty_data)
        assert isinstance(amounts, dict)  # Should return empty dict or default
