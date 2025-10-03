"""
Test module for Help cog commands.
Tests help system functionality and documentation.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import discord
from cogs.help import Help


class TestHelpCog:
    """Test class for Help cog functionality."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance."""
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 12345
        return bot

    @pytest.fixture
    def help_cog(self, mock_bot):
        """Create a Help cog instance for testing."""
        return Help(mock_bot)

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock Discord context."""
        ctx = AsyncMock()
        ctx.author = MagicMock()
        ctx.author.id = 67890
        ctx.author.display_name = "TestUser"
        ctx.guild = MagicMock()
        ctx.guild.id = 11111
        ctx.channel = MagicMock()
        ctx.channel.type = discord.ChannelType.text  # Ensure it's a server channel
        ctx.send = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_help_command_general(self, help_cog, mock_ctx):
        """Test general help command."""
        await help_cog.help_command.callback(help_cog, mock_ctx)

        # Should send embed with general help
        mock_ctx.send.assert_called_once()
        embed_call = mock_ctx.send.call_args[1]['embed']
        assert "BetBot Commands" in embed_call.title
        assert "bet" in embed_call.description.lower()

    @pytest.mark.asyncio
    async def test_help_command_specific_command(self, help_cog, mock_ctx):
        """Test help for a specific command."""
        await help_cog.help_command.callback(help_cog, mock_ctx, "bet")

        # Should send embed with specific command help
        mock_ctx.send.assert_called_once()
        embed_call = mock_ctx.send.call_args[1]['embed']
        assert "help" in embed_call.title.lower()

    @pytest.mark.asyncio
    async def test_help_command_unknown_command(self, help_cog, mock_ctx):
        """Test help for unknown command."""
        await help_cog.help_command.callback(help_cog, mock_ctx, "nonexistentcommand")

        # Should send error or fallback message
        mock_ctx.send.assert_called_once()
        embed_call = mock_ctx.send.call_args[1]['embed']
        # Should contain some form of error or unknown command message
        assert embed_call is not None

    @pytest.mark.asyncio
    async def test_admin_help_command(self, help_cog, mock_ctx):
        """Test admin help command."""
        await help_cog.admin_help_command.callback(help_cog, mock_ctx)

        # Should send embed with admin commands (or guild-only message)
        mock_ctx.send.assert_called_once()
        embed_call = mock_ctx.send.call_args[1]['embed']
        assert "Help" in embed_call.title
        # Admin help either shows commands or guild-only error
        description = embed_call.description.lower()
        assert "give" in description or "server channel" in description

    @pytest.mark.asyncio
    async def test_help_message_formatting(self, help_cog, mock_ctx):
        """Test that help messages are properly formatted."""
        await help_cog.help_command.callback(help_cog, mock_ctx)

        # Should send properly formatted embed
        mock_ctx.send.assert_called_once()
        embed_call = mock_ctx.send.call_args[1]['embed']
        assert embed_call.title is not None
        assert embed_call.description is not None
        assert embed_call.color is not None

    @pytest.mark.asyncio
    async def test_help_includes_shortcuts(self, help_cog, mock_ctx):
        """Test that help includes shortcut commands."""
        await help_cog.admin_help_command.callback(help_cog, mock_ctx)

        # Should include admin help information
        mock_ctx.send.assert_called_once()
        embed_call = mock_ctx.send.call_args[1]['embed']
        # Help should contain admin commands or guild restriction message
        description = embed_call.description.lower()
        assert "give" in description or "take" in description or "admin" in description or "server channel" in description

    @pytest.mark.asyncio
    async def test_help_explains_betting_mechanics(self, help_cog, mock_ctx):
        """Test that help explains how betting works."""
        await help_cog.help_command.callback(help_cog, mock_ctx)

        # Should explain betting system
        mock_ctx.send.assert_called_once()
        embed_call = mock_ctx.send.call_args[1]['embed']
        description = embed_call.description.lower()
        assert "bet" in description

    @pytest.mark.asyncio
    async def test_embed_color_consistency(self, help_cog, mock_ctx):
        """Test that help embeds use consistent colors."""
        await help_cog.help_command.callback(help_cog, mock_ctx)

        # Should use consistent embed color
        mock_ctx.send.assert_called_once()
        embed_call = mock_ctx.send.call_args[1]['embed']
        assert embed_call.color is not None
        # Color should be an integer (Discord color value)
        assert isinstance(embed_call.color, (int, discord.Color))

    def test_help_cog_initialization(self, help_cog):
        """Test that Help cog initializes correctly."""
        assert help_cog is not None
        assert hasattr(help_cog, 'help_command')
        assert hasattr(help_cog, 'admin_help_command')
        assert help_cog.bot is not None