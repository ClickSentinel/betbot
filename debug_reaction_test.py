"""
Simple test to debug the reaction batching issue
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
import discord

from cogs.betting import Betting


@pytest.mark.asyncio
async def test_debug_reaction_processing():
    """Debug test to see what's happening in reaction processing."""

    # Setup bot and cog
    bot = AsyncMock()
    bot.user = Mock()
    bot.user.id = 99999  # Different from our test user ID (123)

    cog = Betting(bot)

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

    # Mock objects
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

    with patch("cogs.betting.load_data", return_value=mock_data) as mock_load, patch(
        "cogs.betting.save_data"
    ) as mock_save, patch(
        "cogs.betting.schedule_live_message_update"
    ) as mock_schedule, patch(
        "cogs.betting.ensure_user"
    ) as mock_ensure:

        print(f"Initial data: {mock_data}")

        # Create reaction payload
        payload = Mock()
        payload.user_id = 123
        payload.message_id = 999
        payload.channel_id = 888
        payload.emoji = "🔥"

        print(
            f"Processing reaction for user {payload.user_id}, emoji {str(payload.emoji)}"
        )

        # Add debugging to see if the method is reached
        original_method = cog.on_raw_reaction_add

        async def debug_reaction_add(payload):
            print(
                f"→ on_raw_reaction_add called with user_id={payload.user_id}, bot_id={bot.user.id}"
            )

            # Check bot user ID filter
            if bot.user and payload.user_id == bot.user.id:
                print("→ Rejected: Bot's own reaction")
                return

            print("→ Loading data...")
            try:
                result = await original_method(payload)
                print(f"→ Method completed successfully")
                return result
            except Exception as e:
                print(f"→ Method failed with error: {e}")
                raise

        cog.on_raw_reaction_add = debug_reaction_add

        # Process the reaction
        await cog.on_raw_reaction_add(payload)

        print(f"Pending bets after reaction: {cog._pending_reaction_bets}")
        print(f"Active timers: {list(cog._reaction_timers.keys())}")

        # Wait for batching delay
        print("Waiting for batch processing...")
        await asyncio.sleep(1.1)

        print(f"Final data bets: {mock_data['betting']['bets']}")
        print(f"Final user balance: {mock_data['balances']['123']}")
        print(f"Save data called: {mock_save.called}")
        print(f"Ensure user called: {mock_ensure.called}")

        # Check if _process_bet was called by looking at the data
        if "123" in mock_data["betting"]["bets"]:
            print("✅ Bet was processed successfully!")
            bet_info = mock_data["betting"]["bets"]["123"]
            print(f"Bet details: {bet_info}")
        else:
            print("❌ Bet was not processed")

        # Check reaction removal calls
        if mock_message.remove_reaction.called:
            print(f"Reactions removed: {mock_message.remove_reaction.call_args_list}")
        else:
            print("No reactions were removed")


if __name__ == "__main__":
    asyncio.run(test_debug_reaction_processing())
