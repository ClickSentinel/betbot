import importlib
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def disable_save_data(monkeypatch):
    """
    Replace `save_data` with a no-op MagicMock in common modules so tests
    don't have to patch it inline. This centralizes the pattern and prevents
    accidental disk writes during test runs.

    The fixture is autouse so existing tests that used `with patch(...save_data)`
    become redundant and will continue to work without modification.
    """
    mock = MagicMock(name="save_data")

    # Common module import paths used across the test-suite and source
    module_names = [
        "data_manager",
        "cogs.bet_commands",
        "cogs.bet_utils",
        "cogs.reaction_handler",
        "cogs.live_message_manager",
        "cogs.session_manager",
        "cogs.economy",
        "utils.bet_state",
        "utils.live_message",
    ]

    # Patch any of the above that are importable in the test environment.
    for mod_name in module_names:
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "save_data"):
                monkeypatch.setattr(mod, "save_data", mock)
        except ModuleNotFoundError:
            # Some test contexts import via the package name (betbot.*). We'll
            # try those below instead of failing here.
            continue

    # Also attempt package-qualified module names to be thorough.
    alt_names = [
        "betbot.data_manager",
        "betbot.cogs.bet_commands",
        "betbot.cogs.bet_utils",
        "betbot.cogs.reaction_handler",
        "betbot.cogs.live_message_manager",
        "betbot.cogs.session_manager",
        "betbot.utils.bet_state",
        "betbot.utils.live_message",
        "betbot.cogs.economy",
    ]

    for mod_name in alt_names:
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "save_data"):
                monkeypatch.setattr(mod, "save_data", mock)
        except ModuleNotFoundError:
            continue

    return mock
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import json
import os

# Test data path
TEST_DATA_FILE = "test_data.json"

# Mock initial data
INITIAL_TEST_DATA = {
    "balances": {},
    "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
    "settings": {"enable_bet_timer": True, "bet_channel_id": None},
    "reaction_bet_amounts": {"🔴": 100, "🔵": 500},
    "contestant_1_emojis": ["🔴"],
    "contestant_2_emojis": ["🔵"],
}


# Fixtures
@pytest.fixture
def test_data():
    """Provides clean test data for each test."""
    import copy

    return copy.deepcopy(INITIAL_TEST_DATA)


@pytest.fixture
def mock_ctx():
    """Creates a mock Discord context."""
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 123456789  # Should be int, not string
    ctx.author.display_name = "TestUser"
    ctx.channel = MagicMock(spec=discord.TextChannel)
    ctx.guild = MagicMock(spec=discord.Guild)
    return ctx


@pytest.fixture
def mock_bot():
    """Creates a mock Discord bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.get_channel = MagicMock(return_value=MagicMock(spec=discord.TextChannel))
    bot.fetch_user = AsyncMock()
    bot.loop = MagicMock()
    bot.loop.create_task = MagicMock()
    return bot


@pytest.fixture
def mock_message():
    """Creates a mock Discord message."""
    message = MagicMock(spec=discord.Message)
    message.id = 123456789
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.id = 987654321
    message.edit = AsyncMock()
    message.add_reaction = AsyncMock()
    message.remove_reaction = AsyncMock()
    message.clear_reactions = AsyncMock()
    return message


# Mock classes to simulate permissions and roles
class MockRole:
    def __init__(self, name):
        self.name = name


class MockMember:
    def __init__(self, roles=None):
        self.roles = roles or []
        self.guild_permissions = MagicMock()
        self.guild_permissions.manage_guild = False


# Test utilities
def setup_member_with_role(role_name):
    """Creates a mock member with a specific role."""
    return MockMember(roles=[MockRole(role_name)])


def setup_member_with_permission():
    """Creates a mock member with manage_guild permission."""
    member = MockMember()
    member.guild_permissions.manage_guild = True
    return member


def assert_embed_contains(mock_send, title=None, description=None, color=None):
    """Asserts that a discord.Embed was sent with specific contents."""
    mock_send.assert_called_once()
    call_args = mock_send.call_args[1]
    embed = call_args["embed"]

    if title is not None:
        assert embed.title == title
    if description is not None:
        assert embed.description == description
    if color is not None:
        assert embed.color == color
