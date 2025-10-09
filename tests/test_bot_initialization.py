"""
Test suite for bot initialization and startup.
Tests that the bot can be created and initialized properly.
"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from bot import MyBot
import discord


class TestBotInitialization:
    """Test bot creation and initialization."""

    def test_bot_creation(self):
        """Test that a bot can be created with proper configuration."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        # Verify bot properties
        assert bot.command_prefix == "!"
        assert bot.intents.message_content is True
        assert bot.intents.reactions is True
        assert isinstance(bot._ambiguous_matches, dict)

        # Clean up
        asyncio.run(bot.close())

    def test_bot_creation_without_intents(self):
        """Test bot creation fails without proper intents."""
        with pytest.raises(TypeError, match="missing.*intents"):
            # Should require intents parameter
            MyBot(command_prefix="!")

    @pytest.mark.asyncio
    async def test_bot_setup_hook_execution(self):
        """Test that setup_hook loads all extensions successfully."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)
        bot.remove_command("help")  # Remove default help command

        try:
            # Execute setup_hook without mocking connection
            # This will attempt to load extensions
            await bot.setup_hook()

            # Verify extensions were loaded
            expected_extensions = [
                "cogs.bet_commands",
                "cogs.reaction_handler",
                "cogs.live_message_manager",
                "cogs.session_manager",
                "cogs.bet_utils",
                "cogs.economy",
                "cogs.help",
            ]

            for ext in expected_extensions:
                assert ext in bot.extensions, f"Extension {ext} was not loaded"

            # Verify cogs were registered
            assert len(bot.cogs) > 0, "No cogs were registered"

        finally:
            await bot.close()

    @pytest.mark.asyncio
    async def test_bot_cleanup_stale_timer_state(self):
        """Test that stale timer state is cleaned up on startup."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        # Mock data_manager functions at the module level where they're imported
        with patch('data_manager.load_data') as mock_load, \
             patch('data_manager.save_data') as mock_save:

            # Mock data with stale timer
            mock_data = {"timer_end_time": 1234567890}
            mock_load.return_value = mock_data

            try:
                await bot._cleanup_stale_timer_state()

                # Verify cleanup was called
                mock_save.assert_called_once()
                saved_data = mock_save.call_args[0][0]
                assert saved_data["timer_end_time"] is None, \
                    "Timer end time was not cleared"

            finally:
                await bot.close()

    @pytest.mark.asyncio
    async def test_bot_cleanup_handles_exceptions(self):
        """Test that cleanup handles exceptions gracefully."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        # Mock data_manager to raise exception
        with patch('data_manager.load_data', side_effect=Exception("Test error")), \
             patch('data_manager.save_data') as mock_save:

            try:
                # Should not raise exception
                await bot._cleanup_stale_timer_state()

                # Save should not have been called due to exception
                mock_save.assert_not_called()

            finally:
                await bot.close()

    def test_bot_ambiguous_matches_initialization(self):
        """Test that ambiguous matches dict is properly initialized."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        assert isinstance(bot._ambiguous_matches, dict)
        assert len(bot._ambiguous_matches) == 0

        # Clean up
        asyncio.run(bot.close())

    def test_bot_get_context_ambiguous_matches_storage(self):
        """Test that ambiguous matches are stored properly."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        # Initially empty
        assert len(bot._ambiguous_matches) == 0

        # Add some ambiguous matches
        bot._ambiguous_matches[123] = ["bet", "balance"]
        bot._ambiguous_matches[456] = ["help", "h"]

        assert len(bot._ambiguous_matches) == 2
        assert bot._ambiguous_matches[123] == ["bet", "balance"]

        # Clean up
        asyncio.run(bot.close())

    def test_bot_intents_configuration(self):
        """Test that bot is configured with required intents."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        # Verify critical intents are enabled
        assert bot.intents.message_content is True, "message_content intent must be enabled"
        assert bot.intents.reactions is True, "reactions intent must be enabled"

        # Verify some default intents
        assert bot.intents.guilds is True, "guilds intent should be enabled by default"
        assert bot.intents.messages is True, "messages intent should be enabled by default"

        # Clean up
        asyncio.run(bot.close())