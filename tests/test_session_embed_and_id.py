import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from utils.live_message import update_live_message, set_session_live_message_info
from data_manager import save_data, load_data


@pytest.mark.asyncio
async def test_session_embed_includes_session_id(tmp_path, monkeypatch):
    # Prepare a fake data store
    data = load_data()
    # Create a session entry
    session_id = "42"
    from typing import MutableMapping, cast
    mutable = cast(MutableMapping, data)
    mutable.setdefault("betting_sessions", {})[session_id] = {
        "id": session_id,
        "title": "A vs B",
        "status": "open",
        "contestants": {"c1": "A", "c2": "B"},
        "bets": {},
        "timer_config": {"enabled": False},
        "created_at": 0,
        "creator_id": "tester",
        "channel_id": 12345,
        "live_message_id": 54321,
    }
    save_data(data)

    # Mock bot and channel/message
    mock_bot = MagicMock()
    # Create a fake channel class and monkeypatch discord.TextChannel so the
    # isinstance(...) check in update_live_message succeeds.
    class FakeChannel:
        def __init__(self):
            # fetch_message should be an async function returning the message
            self.fetch_message = AsyncMock()

    mock_message = MagicMock()
    mock_message.edit = AsyncMock()

    fake_channel = FakeChannel()
    fake_channel.fetch_message.return_value = mock_message

    mock_bot.get_channel.return_value = fake_channel
    mock_user = MagicMock()
    mock_user.display_name = "Tester"
    mock_bot.fetch_user = AsyncMock(return_value=mock_user)

    # Monkeypatch discord.TextChannel to our FakeChannel so isinstance passes
    monkeypatch.setattr("discord.TextChannel", FakeChannel)

    # Patch MessageFormatter.create_live_message_embed to return a simple embed
    with patch("utils.message_formatter.MessageFormatter.create_live_message_embed", new=AsyncMock(return_value=discord.Embed(title="test"))) as patched:
        # Call update_live_message for the session
        await update_live_message(mock_bot, data, session_id=session_id)

    # The edit should have been called on the mock_message
    assert fake_channel.fetch_message.called
    # The embed passed to edit should include the footer set by update_live_message
    # Our code sets the footer after create_live_message_embed
    called_embed = mock_message.edit.call_args[1]["embed"]
    assert called_embed.footer.text == f"Session ID: {session_id}"


def test_numeric_session_id_generation_simulation():
    # Simulate the logic used by openbet to pick the next numeric session id
    data = {
        "betting_sessions": {"1": {}, "2": {}, "5": {}},
        # next_session_id missing should start at 1
    }

    # Simulate picking next id
    next_id = 1
    if "next_session_id" in data and isinstance(data["next_session_id"], (int, str)):
        next_id = int(data["next_session_id"])
    candidate = str(next_id)
    while candidate in data.get("betting_sessions", {}):
        next_id += 1
        candidate = str(next_id)

    assert candidate == "3"
