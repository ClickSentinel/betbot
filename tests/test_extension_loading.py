"""
Test suite for Discord.py extension loading.
Tests that bot.load_extension() works correctly for all cogs.
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


class TestExtensionLoading:
    """Test Discord.py extension loading for all cogs."""

    COG_EXTENSIONS = [
        "cogs.bet_commands",
        "cogs.reaction_handler",
        "cogs.live_message_manager",
        "cogs.session_manager",
        "cogs.bet_utils",
        "cogs.economy",
        "cogs.help",
    ]

    @pytest.fixture
    async def mock_bot(self):
        """Create a mock bot for testing."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        # Mock the actual Discord connection to avoid needing a token
        with patch.object(bot, '_connect', AsyncMock()):
            yield bot

        # Clean up
        await bot.close()

    def test_cog_extensions_list_is_complete(self):
        """Test that the extensions list matches what's loaded in bot.py."""
        # Import bot module to check what it loads
        from bot import MyBot

        # Create a temporary bot instance to check its setup_hook
        intents = discord.Intents.default()
        temp_bot = MyBot(command_prefix="!", intents=intents)

        # Get the extensions that would be loaded
        loaded_extensions = []
        original_load_extension = temp_bot.load_extension

        async def mock_load_extension(name, package=None):
            loaded_extensions.append(name)
            # Mock successful loading
            return None

        temp_bot.load_extension = mock_load_extension

        # Run setup_hook to see what gets loaded
        try:
            asyncio.run(temp_bot.setup_hook())
        except Exception:
            pass  # We expect some failures since we're mocking

        # Check that our test list matches what the bot tries to load
        # (excluding any that might fail to load)
        expected_extensions = set(self.COG_EXTENSIONS)
        loaded_set = set(loaded_extensions)

        # All our test extensions should be in the loaded list
        assert expected_extensions.issubset(loaded_set), \
            f"Test extensions {expected_extensions - loaded_set} not found in bot setup_hook"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("extension_name", COG_EXTENSIONS)
    async def test_individual_extension_loading(self, extension_name):
        """Test loading each extension individually."""
        # Create a fresh bot for each test
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)
        bot.remove_command("help")  # Remove default help command

        try:
            # Attempt to load the extension
            await bot.load_extension(extension_name)

            # Verify the extension was loaded
            assert extension_name in bot.extensions, \
                f"Extension {extension_name} was not loaded successfully"

            # Verify cogs were added
            cogs_added = [name for name, cog in bot.cogs.items()]
            assert len(cogs_added) > 0, \
                f"No cogs were added when loading {extension_name}"

        except Exception as e:
            pytest.fail(f"Failed to load extension {extension_name}: {e}")
        finally:
            await bot.close()

    @pytest.mark.asyncio
    async def test_extension_loading_with_dependencies(self):
        """Test that extensions can be loaded in the correct order with dependencies."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)
        bot.remove_command("help")  # Remove default help command

        try:
            # Load extensions in the order they appear in bot.py
            loaded_extensions = []

            for extension_name in self.COG_EXTENSIONS:
                try:
                    await bot.load_extension(extension_name)
                    loaded_extensions.append(extension_name)
                except Exception as e:
                    pytest.fail(f"Failed to load extension {extension_name}: {e}")

            # Verify all extensions were loaded
            assert len(loaded_extensions) == len(self.COG_EXTENSIONS), \
                f"Only {len(loaded_extensions)}/{len(self.COG_EXTENSIONS)} extensions loaded"

            # Verify all are in bot.extensions
            for ext in loaded_extensions:
                assert ext in bot.extensions, f"Extension {ext} not in bot.extensions"

            # Verify cogs exist
            assert len(bot.cogs) > 0, "No cogs were registered"

        finally:
            await bot.close()

    @pytest.mark.asyncio
    async def test_extension_reloading(self):
        """Test that extensions can be reloaded."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        extension_name = self.COG_EXTENSIONS[0]

        try:
            # Load an extension
            await bot.load_extension(extension_name)

            initial_cog_count = len(bot.cogs)
            initial_extension_present = extension_name in bot.extensions

            # Reload the extension
            await bot.reload_extension(extension_name)

            # Verify it was reloaded (cogs should still be there)
            assert len(bot.cogs) == initial_cog_count, \
                f"Cog count changed after reload: {initial_cog_count} -> {len(bot.cogs)}"

            assert extension_name in bot.extensions, \
                f"Extension {extension_name} not present after reload"

        except Exception as e:
            pytest.fail(f"Failed to reload extension {extension_name}: {e}")
        finally:
            await bot.close()

    @pytest.mark.asyncio
    async def test_extension_unloading(self):
        """Test that extensions can be unloaded."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        bot = MyBot(command_prefix="!", intents=intents)

        extension_name = self.COG_EXTENSIONS[0]

        try:
            # Load an extension
            await bot.load_extension(extension_name)

            initial_cog_count = len(bot.cogs)
            assert extension_name in bot.extensions

            # Unload the extension
            await bot.unload_extension(extension_name)

            # Verify it was unloaded
            assert extension_name not in bot.extensions, \
                f"Extension {extension_name} still present after unload"

            # Cogs should be removed (though this depends on implementation)
            # At minimum, the extension should not be present

        except Exception as e:
            pytest.fail(f"Failed to unload extension {extension_name}: {e}")
        finally:
            await bot.close()

    def test_extension_name_format(self):
        """Test that extension names follow the correct format."""
        for extension_name in self.COG_EXTENSIONS:
            assert extension_name.startswith("cogs."), \
                f"Extension name should start with 'cogs.': {extension_name}"

            assert "." in extension_name, \
                f"Extension name should contain a dot: {extension_name}"

            parts = extension_name.split(".")
            assert len(parts) == 2, \
                f"Extension name should have exactly 2 parts: {extension_name}"

            assert parts[0] == "cogs", \
                f"Extension name should start with 'cogs': {extension_name}"

            # Module name should be valid Python identifier
            assert parts[1].replace("_", "").isalnum(), \
                f"Extension module name should be valid identifier: {parts[1]}"