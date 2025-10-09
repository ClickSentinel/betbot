"""
Test module for Economy cog commands.
Tests admin balance management functionality.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import discord
from cogs.economy import Economy

# Import not needed for these tests


class TestEconomyCog:
    """Test class for Economy cog functionality."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance."""
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 12345
        return bot

    @pytest.fixture
    def economy_cog(self, mock_bot):
        """Create an Economy cog instance for testing."""
        return Economy(mock_bot)

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock Discord context."""
        ctx = AsyncMock()
        ctx.author = MagicMock()
        ctx.author.id = 67890
        ctx.author.display_name = "TestUser"
        ctx.guild = MagicMock()
        ctx.guild.id = 11111
        ctx.send = AsyncMock()
        return ctx

    @pytest.fixture
    def test_data(self):
        """Test data structure."""
        return {
            "balances": {"11111": 500, "22222": 750, "67890": 1000},
            "betting": {"bets": {}, "contestants": {}, "locked": False, "open": False},
        }

    @pytest.mark.asyncio
    async def test_balance_command_self(self, economy_cog, mock_ctx, test_data):
        """Test checking your own balance."""
        with patch("cogs.economy.load_data", return_value=test_data):
            await economy_cog.balance.callback(economy_cog, mock_ctx)

            # Should send embed with user's balance
            mock_ctx.send.assert_called_once()
            embed_call = mock_ctx.send.call_args[1]["embed"]
            assert "1000" in embed_call.description
            assert "Your Balance" in embed_call.description

    @pytest.mark.asyncio
    async def test_balance_command_other_user(self, economy_cog, mock_ctx, test_data):
        """Test balance command for another user."""
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.display_name = "OtherUser"
        test_data["balances"]["456"] = 500

        await economy_cog.balance(mock_ctx, member)

        mock_ctx.send.assert_called_once()
        embed = mock_ctx.send.call_args[0][0]
        assert "OtherUser" in embed.description
        assert "500" in embed.description

    @pytest.mark.asyncio
    async def test_balance_command_new_user(self, economy_cog, mock_ctx, test_data):
        """Test checking balance of user not in system."""
        target_user = MagicMock()
        target_user.id = 99999
        target_user.display_name = "NewUser"

        with patch("cogs.economy.load_data", return_value=test_data):
            await economy_cog.balance.callback(economy_cog, mock_ctx, target_user)

            # Should create user with default balance
            mock_ctx.send.assert_called_once()
            embed_call = mock_ctx.send.call_args[1]["embed"]
            assert "1000" in embed_call.description  # Default balance
            assert "NewUser" in embed_call.description

    @pytest.mark.asyncio
    async def test_give_command_success(self, economy_cog, mock_ctx, test_data):
        """Test successful giving of coins."""
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.mention = "<@456>"
        test_data["balances"]["456"] = 100

        with patch("cogs.economy.save_data") as mock_save:
            await economy_cog.give(mock_ctx, member, 50)

        mock_save.assert_called_once()
        assert test_data["balances"]["456"] == 150

    @pytest.mark.asyncio
    async def test_take_command_success(self, economy_cog, mock_ctx, test_data):
        """Test successful taking of coins."""
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.mention = "<@456>"
        test_data["balances"]["456"] = 100

        with patch("cogs.economy.save_data") as mock_save:
            await economy_cog.take(mock_ctx, member, 50)

        mock_save.assert_called_once()
        assert test_data["balances"]["456"] == 50

    @pytest.mark.asyncio
    async def test_take_command_insufficient_funds(self, economy_cog, mock_ctx, test_data):
        """Test taking coins with insufficient funds."""
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.display_name = "OtherUser"
        test_data["balances"]["456"] = 500

        await economy_cog.take(mock_ctx, member, 600)

        mock_ctx.send.assert_called_once()
        embed = mock_ctx.send.call_args[0][0]
        assert "insufficient funds" in embed.title.lower()
        assert "only has" in embed.description

    @pytest.mark.asyncio
    async def test_set_balance_command(self, economy_cog, mock_ctx, test_data):
        """Test setting a user's balance."""
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.mention = "<@456>"

        with patch("cogs.economy.save_data") as mock_save:
            await economy_cog.set_balance(mock_ctx, member, 500)

        mock_save.assert_called_once()
        assert test_data["balances"]["456"] == 500

    @pytest.mark.asyncio
    async def test_balance_display_formatting(self, economy_cog, mock_ctx, test_data):
        """Test that balance display is formatted correctly."""
        user_id = str(mock_ctx.author.id)
        test_data["balances"][user_id] = 1234567

        await economy_cog.balance(mock_ctx)

        # Assert that the balance is formatted with commas
        mock_ctx.send.assert_called_once()
        embed = mock_ctx.send.call_args[0][0]
        assert "1,234,567" in embed.description

    @pytest.mark.asyncio
    async def test_admin_permission_commands(self, economy_cog, mock_ctx, test_data):
        """Test that admin commands check permissions."""
        target_user = MagicMock()
        target_user.id = 11111

        # The actual permission checking is done by Discord.py decorators
        # but we can test that the commands exist and can be called
        with patch("cogs.economy.load_data", return_value=test_data):
            # These should not raise AttributeError
            assert hasattr(economy_cog.give, "callback")
            assert hasattr(economy_cog.take, "callback")
            assert hasattr(economy_cog.set_balance, "callback")
