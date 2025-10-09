"""
Enhanced testing utilities and fixtures.
"""

import pytest
import asyncio
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, Optional
import tempfile
import json
from pathlib import Path

from data_manager import Data
from utils.bet_state import BetState, Economy

# Removed unused imports for cleaned up codebase


@pytest.fixture
def enhanced_test_data():
    """Enhanced test data with more realistic scenarios."""
    import copy

    # Import from the same module where it's defined
    from tests.conftest import INITIAL_TEST_DATA

    data = copy.deepcopy(INITIAL_TEST_DATA)

    # Add more users with different balances
    data["balances"].update(
        {
            "user1": 1000,
            "user2": 500,
            "user3": 2000,
            "rich_user": 10000,
            "poor_user": 10,
        }
    )

    # Set up an active betting round
    data["betting"]["open"] = True
    data["betting"]["contestants"] = {
        "alice": "Alice",
        "bob": "Bob",
        "charlie": "Charlie",
    }
    # Use accessor to populate initial bet for consistency with production code
    from data_manager import set_bet
    from utils.bet_state import make_bet_info
    from data_manager import Data
    from typing import cast
    set_bet(cast(Data, data), None, "user1", make_bet_info(100, "alice", "🔥"))

    return data


@pytest.fixture
def temp_data_file():
    """Create a temporary data file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_data = {
            "balances": {"test_user": 1000},
            "betting": {"open": False, "locked": False, "contestants": {}, "bets": {}},
        }
        json.dump(temp_data, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def bet_state_with_data(enhanced_test_data):
    """BetState instance with realistic test data."""
    return BetState(enhanced_test_data)


@pytest.fixture
def economy_with_data(enhanced_test_data):
    """Economy instance with test data."""
    return Economy(enhanced_test_data)


# Removed fixtures for cleaned up utilities


@pytest.fixture
async def mock_discord_objects():
    """Mock Discord objects for testing commands."""
    # Mock bot
    bot = AsyncMock(spec=discord.Client)
    bot.user = MagicMock()
    bot.user.id = 12345
    bot.user.name = "TestBot"

    # Mock guild
    guild = MagicMock(spec=discord.Guild)
    guild.id = 67890
    guild.name = "Test Guild"

    # Mock channel
    channel = AsyncMock(spec=discord.TextChannel)
    channel.id = 11111
    channel.name = "test-channel"
    channel.guild = guild

    # Mock user
    user = MagicMock(spec=discord.Member)
    user.id = 22222
    user.name = "TestUser"
    user.display_name = "Test User"
    user.guild = guild

    # Mock message
    message = AsyncMock(spec=discord.Message)
    message.id = 33333
    message.author = user
    message.channel = channel
    message.guild = guild
    message.content = "!test"

    # Mock context
    ctx = AsyncMock()
    ctx.bot = bot
    ctx.guild = guild
    ctx.channel = channel
    ctx.author = user
    ctx.message = message
    ctx.send = AsyncMock()

    return {
        "bot": bot,
        "guild": guild,
        "channel": channel,
        "user": user,
        "message": message,
        "ctx": ctx,
    }


class TestScenario:
    """Helper class for creating test scenarios."""

    @staticmethod
    def create_betting_round(data, contestants: Dict[str, str], bets=None):
        """Set up a betting round scenario."""
        data["betting"]["open"] = True
        data["betting"]["locked"] = False
        data["betting"]["contestants"] = contestants
        if bets:
            data["betting"]["bets"].update(bets)
        return data

    @staticmethod
    def create_locked_betting_round(data, contestants: Dict[str, str], bets):
        """Set up a locked betting round scenario."""
        data["betting"]["open"] = False
        data["betting"]["locked"] = True
        data["betting"]["contestants"] = contestants
        if bets:
            data["betting"]["bets"].update(bets)
        return data

    @staticmethod
    def create_user_with_balance(data, user_id: str, balance: int):
        """Add a user with specific balance to test data."""
        data["balances"][user_id] = balance
        return data


@pytest.fixture
def test_scenarios():
    """Provide test scenario helper."""
    return TestScenario


# Performance testing utilities
class PerformanceTimer:
    """Context manager for timing operations in tests."""

    def __init__(self, max_time: float):
        self.max_time = max_time
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def __enter__(self):
        self.start_time = asyncio.get_event_loop().time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = asyncio.get_event_loop().time()
        if self.start_time is not None and self.end_time is not None:
            elapsed = self.end_time - self.start_time
            assert (
                elapsed <= self.max_time
            ), f"Operation took {elapsed:.3f}s, expected <= {self.max_time}s"


@pytest.fixture
def performance_timer():
    """Performance timer fixture."""
    return PerformanceTimer


# Integration tests removed with enhanced bot cleanup


# Database testing utilities
@pytest.fixture
def mock_file_operations():
    """Mock file operations for database testing."""
    mock_data = {
        "balances": {},
        "betting": {"open": False, "locked": False, "contestants": {}, "bets": {}},
    }

    with patch("builtins.open"), patch("json.load", return_value=mock_data), patch(
        "json.dump"
    ), patch("os.path.exists", return_value=True):
        yield mock_data


# Async testing utilities
def run_async_test(coro):
    """Helper to run async tests in sync test functions."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Custom assertions
def assert_valid_embed(embed: discord.Embed):
    """Assert that an embed is properly formatted."""
    assert embed.title is not None, "Embed must have a title"
    assert embed.description is not None, "Embed must have a description"
    assert embed.color is not None, "Embed must have a color"


def assert_bet_state_valid(bet_state: BetState):
    """Assert that bet state is in a valid condition."""
    # Basic state validation
    assert isinstance(bet_state.is_open, bool)
    assert isinstance(bet_state.is_locked, bool)

    # Logical consistency
    if bet_state.is_locked:
        assert not bet_state.is_open, "Betting cannot be both open and locked"

    # Data integrity
    for user_id, bet_info in bet_state.bets.items():
        assert bet_info["amount"] > 0, f"Bet amount must be positive for user {user_id}"
        assert (
            bet_info["choice"] in bet_state.contestants
        ), f"Invalid contestant choice for user {user_id}"


def assert_balance_consistency(economy: Economy, user_id: str, expected_balance: int):
    """Assert that user balance is consistent."""
    actual_balance = economy.get_balance(user_id)
    assert (
        actual_balance == expected_balance
    ), f"Expected balance {expected_balance}, got {actual_balance}"


def test_help_message_formatting():
    """Test that help messages have proper formatting with visual hierarchy."""
    from config import DESC_GENERAL_HELP, DESC_ADMIN_HELP

    # Test general help has bullet points and visual structure
    assert "•" in DESC_GENERAL_HELP
    assert "**" in DESC_GENERAL_HELP  # Bold formatting
    assert "`" in DESC_GENERAL_HELP  # Code formatting

    # Test general help explains betting mechanics
    assert "How Betting Works" in DESC_GENERAL_HELP
    assert "User Commands" in DESC_GENERAL_HELP
    assert "Quick Betting with Reactions" in DESC_GENERAL_HELP

    # Test admin help is well-structured
    assert "**" in DESC_ADMIN_HELP  # Bold headers
    assert "•" in DESC_ADMIN_HELP  # Bullet points
    assert "BetBoy role" in DESC_ADMIN_HELP  # Permission info
    assert "Manage Server" in DESC_ADMIN_HELP  # Permission info


def test_message_formatter_visual_improvements():
    """Test that message formatter produces visually enhanced content."""
    from utils.message_formatter import MessageFormatter

    # Test data
    contestants = {"1": "Alice", "2": "Bob"}
    emoji_config = {
        "contestant_1_emojis": ["🔥", "⚡", "💪", "🏆"],
        "contestant_2_emojis": ["🌟", "💎", "🚀", "👑"],
    }
    amounts = {
        "🔥": 100,
        "⚡": 250,
        "💪": 500,
        "🏆": 1000,
        "🌟": 100,
        "💎": 250,
        "🚀": 500,
        "👑": 1000,
    }

    # Test reaction options formatting
    options = MessageFormatter.format_reaction_options(
        contestants, emoji_config, amounts
    )
    options_text = "".join(options)

    # Should have visual separators
    assert "━" in options_text or "─" in options_text

    # Should group by contestant with visual hierarchy
    assert "🔴" in options_text and "🔵" in options_text  # Contestant indicator emojis
    assert (
        "**Alice:**" in options_text and "**Bob:**" in options_text
    )  # Bold contestant names

    # Should show all themed emojis with amounts
    for emoji, amount in amounts.items():
        assert f"{emoji} `{amount}`" in options_text
