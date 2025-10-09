"""
Shared utilities for betting cogs.
"""

import discord
from discord.ext import commands
from typing import Optional, Tuple, Dict, Any
import asyncio
import time
import re

# Add enhanced logging
from utils.logger import logger
from utils.performance_monitor import performance_monitor
from utils.betting_timer import BettingTimer
from utils.betting_utils import BettingPermissions, BettingUtils

from config import (
    SEPARATOR_EMOJI,
    CONTESTANT_EMOJIS,
    COLOR_ERROR,
    COLOR_GOLD,
    COLOR_DARK_ORANGE,
    COLOR_INFO,
    COLOR_WARNING,
    COLOR_SUCCESS,
    BET_TIMER_DURATION,
    # Centralized Messages
    MSG_BET_ALREADY_OPEN,
    MSG_BET_LOCKED,
    MSG_NO_ACTIVE_BET,
    MSG_BET_LOCKED_NO_NEW_BETS,
    MSG_NO_BETS_TO_CLOSE,
    MSG_INTERNAL_ERROR_LOCKED,
    MSG_AMOUNT_POSITIVE,
    MSG_INVALID_BET_FORMAT,
    MSG_UNKNOWN_CONTESTANT,
    MSG_FAILED_SEND_LIVE_MESSAGE,
    MSG_BETTING_LOCKED_SUMMARY,
    MSG_BETTING_TIMER_EXPIRED_SUMMARY,
    MSG_LIVE_BET_INITIAL_DESCRIPTION,
    # Centralized Titles
    TITLE_BETTING_ERROR,
    TITLE_CANNOT_LOCK_BETS,
    TITLE_BETS_LOCKED,
    TITLE_BETTING_ROUND_OPENED,
    TITLE_INVALID_BET_FORMAT,
    TITLE_BET_PLACED,
    TITLE_CANNOT_CLOSE_BETS,
    TITLE_BETTING_CHANNEL_SET,
    TITLE_TIMER_TOGGLED,
    TITLE_CURRENT_BETS_OVERVIEW,
    TITLE_LIVE_BETTING_ROUND,
    MSG_NO_ACTIVE_BET_AND_MISSING_ARGS,
    TITLE_NO_OPEN_BETTING_ROUND,
    MSG_PLACE_MANUAL_BET_INSTRUCTIONS,
    MSG_INVALID_OPENBET_FORMAT,
    MSG_BET_LOCKED_WITH_LIVE_LINK,
    # reaction debug config
    REACTION_DEBUG_LOGGING_ENABLED,
    ALLOW_RUNTIME_REACTION_DEBUG_TOGGLE,
    REACTION_DEBUG_LOG_FILENAME,
)
from data_manager import (
    load_data,
    save_data,
    ensure_user,
    Data,
    MultiBettingSession,
    TimerConfig,
)
from data_manager import get_bets, set_bet, remove_bet, is_multi_session_mode
from data_manager import UserBet
from utils.live_message import (
    get_live_message_info,
    get_saved_bet_channel_id,
    set_live_message_info,
    set_secondary_live_message_info,
    clear_live_message_info,
    update_live_message,
    _get_contestant_from_emoji,
    get_live_message_link,
    get_live_message_link_for_session,
    get_secondary_live_message_info,
    schedule_live_message_update,
    schedule_live_message_update_for_session,
    initialize_live_message_scheduler,
)
from utils.bet_state import BetState, SessionBetState
from utils.bet_state import WinnerInfo


class BetUtils(commands.Cog):
    """Shared utilities for betting functionality."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check_permission(self, ctx: commands.Context, action: str) -> bool:
        """Check if the user has permission to perform an action."""
        return await BettingPermissions.check_permission(ctx, action)

    def _cancel_bet_timer(self):
        """Cancel the current betting timer."""
        # This will be implemented by the timer manager
        pass

    def _clear_timer_state_in_data(self, data: Data) -> None:
        """Clear timer state from data."""
        data["timer_end_time"] = None

    async def _send_embed(
        self,
        ctx: commands.Context,
        title: str,
        description: str,
        color: discord.Color,
    ) -> None:
        """Send an embed message."""
        await BettingUtils.send_embed(ctx, title, description, color)

    def _add_reactions_background(self, message: discord.Message, data: Data) -> None:
        """Add reactions to a message in the background."""
        async def add_reactions():
            try:
                # Add all betting emojis from both contestants with separator
                c1_emojis = data.get("contestant_1_emojis", [])
                c2_emojis = data.get("contestant_2_emojis", [])
                
                # Add contestant 1 emojis
                for emoji in c1_emojis:
                    await message.add_reaction(emoji)
                
                # Add separator
                await message.add_reaction(SEPARATOR_EMOJI)
                
                # Add contestant 2 emojis
                for emoji in c2_emojis:
                    await message.add_reaction(emoji)
            except Exception as e:
                logger.error(f"Failed to add reactions to message {message.id}: {e}")

        asyncio.create_task(add_reactions())


async def setup(bot: commands.Bot) -> None:
    """Setup function for the BetUtils cog."""
    await bot.add_cog(BetUtils(bot))