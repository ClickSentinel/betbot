"""
Test to reproduce the exact issue: rapid reactions don't process until another reaction is added later.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
import discord

from cogs.reaction_handler import ReactionHandler


@pytest.mark.asyncio
async def test_reproduction_case():
    """Reproduce the exact issue described: rapid reactions don't process until another reaction."""

    # Setup bot and cog
    bot = AsyncMock()
    bot.user = Mock()
    bot.user.id = 99999  # Different from test user

    cog = ReactionHandler(bot)

    # Mock data
    mock_data = {
        "betting": {
            "open": True,
            "contestants": {"1": "Alice", "2": "Bob"},
            "bets": {},
        },
        "balances": {"123": 1000},
        "live_message": 999,
        "live_channel": 888,
        "live_secondary_message": None,
        "live_secondary_channel": None,
        "contestant_1_emojis": ["🔥", "⚡", "💪", "🏆"],
        "contestant_2_emojis": ["🌟", "💎", "🚀", "👑"],
        "reaction_bet_amounts": {
            "🔥": 100,
            "⚡": 250,
            "💪": 500,
            "🏆": 1000,
            "🌟": 100,
            "💎": 250,
            "🚀": 500,
            "👑": 1000,
        },
    }

    # Mock Discord objects
    mock_user = Mock()
    mock_user.id = 123
    mock_user.name = "TestUser"

    mock_message = Mock()
    mock_message.id = 999
    mock_message.remove_reaction = AsyncMock()

    mock_channel = Mock(spec=discord.TextChannel)
    mock_channel.id = 888
    mock_channel.send = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)

    # Setup bot mocks
    bot.get_channel.return_value = mock_channel
    bot.fetch_user.return_value = mock_user

    # Set up proper async mocks for Discord API calls
    mock_channel = AsyncMock(spec=discord.TextChannel)
    mock_channel.id = 888
    mock_message = AsyncMock()
    mock_message.id = 999
    mock_message.channel = mock_channel
    mock_message.remove_reaction = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    mock_channel.send = AsyncMock()  # For error messages

    mock_user = AsyncMock()
    mock_user.id = 123

    cog.bot.get_channel = Mock(return_value=mock_channel)
    cog.bot.fetch_user = AsyncMock(return_value=mock_user)

    with patch("cogs.reaction_handler.load_data", return_value=mock_data), patch(
        "cogs.reaction_handler.save_data"
    ), patch("cogs.reaction_handler.schedule_live_message_update"), patch(
        "cogs.reaction_handler.ensure_user"
    ):

        print("=== Reproducing the Issue ===")
        print(f"Initial balance: {mock_data['balances']['123']}")
        print(f"Initial bets: {mock_data['betting']['bets']}")

        # Simulate rapid reactions like user described
        reactions = ["🔥", "⚡", "💪", "🌟"]  # Mix of contestants

        print(f"\\n1. Adding {len(reactions)} rapid reactions...")
        for i, emoji in enumerate(reactions):
            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = emoji

            print(f"   → Adding reaction {i + 1}: {emoji}")
            await cog.on_raw_reaction_add(payload)

            # Very short delay to simulate rapid but not instant clicking
            await asyncio.sleep(0.1)

        print(f"\\nAfter all reactions added:")
        print(f"   Pending bets: {cog._pending_reaction_bets}")
        print(f"   Active timers: {list(cog._reaction_timers.keys())}")
        print(f"   Current balance: {mock_data['balances']['123']}")
        print(f"   Current bets: {mock_data['betting']['bets']}")

        # Now wait and see if the final bet gets processed
        print(f"\\n2. Waiting 2 seconds for batching to complete...")
        await asyncio.sleep(2.0)

        print(f"\\nAfter waiting:")
        print(f"   Pending bets: {cog._pending_reaction_bets}")
        print(f"   Active timers: {list(cog._reaction_timers.keys())}")
        print(f"   Final balance: {mock_data['balances']['123']}")
        print(f"   Final bets: {mock_data['betting']['bets']}")

        # Check if bet was processed
        if "123" in mock_data["betting"]["bets"]:
            bet_info = mock_data["betting"]["bets"]["123"]
            print(f"   ✅ SUCCESS: Bet processed - {bet_info}")
            expected_balance = 1000 - bet_info["amount"]
            if mock_data["balances"]["123"] == expected_balance:
                print(f"   ✅ Balance correct: {mock_data['balances']['123']}")
            else:
                print(
                    f"   ❌ Balance wrong: expected {expected_balance}, got {
                        mock_data['balances']['123']}"
                )
        else:
            print(f"   ❌ ISSUE REPRODUCED: No bet was processed!")

        # Now test the workaround: add another reaction
        print(f"\\n3. Testing workaround: adding one more reaction...")
        payload = Mock()
        payload.user_id = 123
        payload.message_id = 999
        payload.channel_id = 888
        payload.emoji = "👑"  # Different emoji

        await cog.on_raw_reaction_add(payload)
        await asyncio.sleep(1.5)  # Wait for processing

        print(f"\\nAfter workaround reaction:")
        print(f"   Final balance: {mock_data['balances']['123']}")
        print(f"   Final bets: {mock_data['betting']['bets']}")


if __name__ == "__main__":
    asyncio.run(test_reproduction_case())
