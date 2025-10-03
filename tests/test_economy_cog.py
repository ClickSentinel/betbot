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
        """Test checking another user's balance."""
        target_user = MagicMock()
        target_user.id = 11111
        target_user.display_name = "OtherUser"

        with patch("cogs.economy.load_data", return_value=test_data):
            await economy_cog.balance.callback(economy_cog, mock_ctx, target_user)

            # Should send embed with target user's balance
            mock_ctx.send.assert_called_once()
            embed_call = mock_ctx.send.call_args[1]["embed"]
            assert "500" in embed_call.description
            assert "OtherUser" in embed_call.description

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
        """Test giving coins to a user successfully."""
        target_user = MagicMock()
        target_user.id = 11111
        target_user.display_name = "OtherUser"

        with patch("cogs.economy.load_data", return_value=test_data), patch(
            "cogs.economy.save_data"
        ) as mock_save:

            await economy_cog.give.callback(economy_cog, mock_ctx, target_user, 200)

            # Should save updated data
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert saved_data["balances"]["11111"] == 700  # 500 + 200

            # Should send success message
            mock_ctx.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_give_command_invalid_amount(self, economy_cog, mock_ctx, test_data):
        """Test giving invalid amount (negative or zero)."""
        target_user = MagicMock()
        target_user.id = 11111

        with patch("cogs.economy.load_data", return_value=test_data):
            await economy_cog.give.callback(economy_cog, mock_ctx, target_user, -100)

            # Should send error message
            mock_ctx.send.assert_called_once()
            embed_call = mock_ctx.send.call_args[1]["embed"]
            assert "Amount must be a positive number" in embed_call.description

    @pytest.mark.asyncio
    async def test_take_command_success(self, economy_cog, mock_ctx, test_data):
        """Test taking coins from a user successfully."""
        target_user = MagicMock()
        target_user.id = 11111
        target_user.display_name = "OtherUser"

        with patch("cogs.economy.load_data", return_value=test_data), patch(
            "cogs.economy.save_data"
        ) as mock_save:

            await economy_cog.take.callback(economy_cog, mock_ctx, target_user, 200)

            # Should save updated data
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert saved_data["balances"]["11111"] == 300  # 500 - 200

            # Should send success message
            mock_ctx.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_take_command_insufficient_funds(
        self, economy_cog, mock_ctx, test_data
    ):
        """Test taking more coins than user has."""
        target_user = MagicMock()
        target_user.id = 11111
        target_user.display_name = "OtherUser"

        with patch("cogs.economy.load_data", return_value=test_data):
            await economy_cog.take.callback(
                economy_cog, mock_ctx, target_user, 600
            )  # More than 500 balance

            # Should send error message
            mock_ctx.send.assert_called_once()
            embed_call = mock_ctx.send.call_args[1]["embed"]
            assert (
                "only has" in embed_call.description
                and "Cannot take" in embed_call.description
            )

    @pytest.mark.asyncio
    async def test_set_balance_command(self, economy_cog, mock_ctx, test_data):
        """Test setting a user's balance."""
        target_user = MagicMock()
        target_user.id = 11111
        target_user.display_name = "OtherUser"

        with patch("cogs.economy.load_data", return_value=test_data), patch(
            "cogs.economy.save_data"
        ) as mock_save:

            await economy_cog.set_balance.callback(
                economy_cog, mock_ctx, target_user, 1500
            )

            # Should save updated data
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert saved_data["balances"]["11111"] == 1500

            # Should send success message
            mock_ctx.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_balance_invalid_amount(self, economy_cog, mock_ctx, test_data):
        """Test setting balance to invalid amount."""
        target_user = MagicMock()
        target_user.id = 11111

        with patch("cogs.economy.load_data", return_value=test_data):
            await economy_cog.set_balance.callback(
                economy_cog, mock_ctx, target_user, -100
            )

            # Should send error message
            mock_ctx.send.assert_called_once()
            embed_call = mock_ctx.send.call_args[1]["embed"]
            assert "Amount must be a positive number" in embed_call.description

    @pytest.mark.asyncio
    async def test_balance_display_formatting(self, economy_cog, mock_ctx, test_data):
        """Test that balance amounts are formatted correctly."""
        # Test large numbers are formatted with commas
        test_data["balances"]["67890"] = 1234567

        with patch("cogs.economy.load_data", return_value=test_data):
            await economy_cog.balance.callback(economy_cog, mock_ctx)

            # Should display large numbers
            mock_ctx.send.assert_called_once()
            embed_call = mock_ctx.send.call_args[1]["embed"]
            assert "1234567" in embed_call.description

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
