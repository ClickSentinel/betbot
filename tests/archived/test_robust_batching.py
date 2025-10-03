"""
Comprehensive test for the robust reaction batching system.
Tests the improved system with backup processing and better error handling.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
import discord

from cogs.betting import Betting


@pytest.mark.asyncio
async def test_robust_reaction_batching():
    """Test the robust reaction batching system with backup processing."""

    # Setup bot and cog
    bot = AsyncMock()
    bot.user = Mock()
    bot.user.id = 99999

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

    bot.get_channel.return_value = mock_channel
    bot.fetch_user.return_value = mock_user

    # Track successful bet processing
    bet_processed = False
    final_bet_info = {}

    async def mock_process_bet(
        channel, data, user_id, amount, choice, emoji, notify_user=True
    ):
        nonlocal bet_processed, final_bet_info
        user_id_str = str(user_id)

        if data["balances"][user_id_str] >= amount:
            data["balances"][user_id_str] -= amount
            data["betting"]["bets"][user_id_str] = {
                "choice": choice.lower(),
                "amount": amount,
                "emoji": emoji,
            }
            bet_processed = True
            final_bet_info = {
                "choice": choice.lower(),
                "amount": amount,
                "emoji": emoji,
            }
            return True
        return False

    with patch("cogs.betting.load_data", return_value=mock_data), patch(
        "cogs.betting.save_data"
    ), patch("cogs.betting.schedule_live_message_update"), patch(
        "cogs.betting.ensure_user"
    ), patch.object(
        cog, "_process_bet", side_effect=mock_process_bet
    ):

        print("=== Testing Robust Reaction Batching ===")

        # Test 1: Rapid reactions with natural processing
        print("\\n1. Testing rapid reactions (should work with primary timer)...")
        reactions = ["🔥", "⚡", "💪", "🌟"]

        for emoji in reactions:
            payload = Mock()
            payload.user_id = 123
            payload.message_id = 999
            payload.channel_id = 888
            payload.emoji = emoji

            # Simulate the actual reaction handler
            cog._cancel_user_reaction_timer(123)
            cog._pending_reaction_bets[123] = {
                "message": mock_message,
                "user": mock_user,
                "data": mock_data,
                "contestant_name": (
                    "Bob" if emoji in ["🌟", "💎", "🚀", "👑"] else "Alice"
                ),
                "bet_amount": mock_data["reaction_bet_amounts"][emoji],
                "emoji": emoji,
                "channel": mock_channel,
            }

            # Start timer
            timer_task = asyncio.create_task(cog._delayed_reaction_processing(123))
            cog._reaction_timers[123] = timer_task

            # Start backup
            asyncio.create_task(cog._backup_reaction_processing(123, 3.0))

            await asyncio.sleep(0.1)  # Rapid clicking simulation

        # Wait for primary processing
        await asyncio.sleep(1.5)

        assert bet_processed, "Primary timer should have processed the bet"
        assert (
            final_bet_info["choice"] == "bob"
        ), f"Expected 'bob', got {final_bet_info['choice']}"
        assert (
            final_bet_info["emoji"] == "🌟"
        ), f"Expected '🌟', got {final_bet_info['emoji']}"
        assert (
            mock_data["balances"]["123"] == 900
        ), f"Expected 900, got {mock_data['balances']['123']}"

        print("✅ Primary timer processing works correctly")

        # Test 2: Simulate timer failure (backup should kick in)
        print("\\n2. Testing backup processing (simulating timer failure)...")

        # Reset state
        bet_processed = False
        final_bet_info = {}
        mock_data["balances"]["123"] = 1000
        mock_data["betting"]["bets"] = {}

        # Add pending bet without starting primary timer (simulates timer failure)
        cog._pending_reaction_bets[456] = {
            "message": mock_message,
            "user": mock_user,
            "data": mock_data,
            "contestant_name": "Alice",
            "bet_amount": 250,
            "emoji": "⚡",
            "channel": mock_channel,
        }

        # Start only backup processing (no primary timer)
        asyncio.create_task(
            cog._backup_reaction_processing(456, 1.0)
        )  # Shorter delay for testing

        # Wait for backup to trigger
        await asyncio.sleep(1.5)

        assert bet_processed, "Backup processing should have processed the bet"
        assert (
            final_bet_info["choice"] == "alice"
        ), f"Expected 'alice', got {final_bet_info['choice']}"
        assert (
            final_bet_info["amount"] == 250
        ), f"Expected 250, got {final_bet_info['amount']}"

        print("✅ Backup processing works correctly")

        # Test 3: Ensure backup doesn't interfere when primary works
        print("\\n3. Testing that backup doesn't interfere with working primary...")

        bet_processed = False
        final_bet_info = {}
        mock_data["balances"]["123"] = 1000
        mock_data["betting"]["bets"] = {}

        # Add pending bet and start both primary and backup
        cog._pending_reaction_bets[789] = {
            "message": mock_message,
            "user": mock_user,
            "data": mock_data,
            "contestant_name": "Bob",
            "bet_amount": 500,
            "emoji": "🚀",
            "channel": mock_channel,
        }

        # Start primary timer
        timer_task = asyncio.create_task(cog._delayed_reaction_processing(789))
        cog._reaction_timers[789] = timer_task

        # Start backup
        asyncio.create_task(cog._backup_reaction_processing(789, 2.0))

        # Wait for primary to complete
        await asyncio.sleep(1.5)

        assert bet_processed, "Primary should have processed the bet"

        # Check that bet was only processed once
        first_balance = mock_data["balances"]["123"]

        # Wait for backup delay to pass
        await asyncio.sleep(1.0)

        assert (
            mock_data["balances"]["123"] == first_balance
        ), "Backup should not have processed again"

        print("✅ Backup correctly avoids double-processing")

        print("\\n🎉 All robust batching tests passed!")


if __name__ == "__main__":
    asyncio.run(test_robust_reaction_batching())
