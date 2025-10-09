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
    BettingSession,
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

    async def _lock_bets_internal(
        self,
        ctx: commands.Context,
        silent_lock: bool = False,
        session_id: Optional[str] = None
    ) -> None:
        """Lock bets for the current betting round or a specific session."""
        from utils.bet_state import BetState, SessionBetState

        data = load_data()

        if session_id:
            # Multi-session mode: lock specific session
            if session_id not in data.get("betting_sessions", {}):
                await self._send_embed(
                    ctx, TITLE_BETTING_ERROR,
                    f"Session '{session_id}' not found.", COLOR_ERROR
                )
                return

            session = data["betting_sessions"][session_id]
            # Create a wrapper dict with open/locked fields for SessionBetState
            betting_session: BettingSession = {
                "open": session.get("status") == "open",
                "locked": session.get("status") == "locked",
                "bets": session.get("bets", {}),
                "contestants": session.get("contestants", {}),
            }
            session_state = SessionBetState(data, betting_session)
            session_state.lock_bets()

            # Update the actual session status
            session["status"] = "locked"

            save_data(data)

            if not silent_lock:
                await self._send_embed(
                    ctx, TITLE_BETS_LOCKED,
                    f"Bets locked for session '{session_id}'.", COLOR_SUCCESS
                )
            
            # Update live message to reflect locked state
            await update_live_message(self.bot, data, session_id=session_id)
        else:
            # Single-session mode: lock main betting round
            bet_state = BetState(data)
            bet_state.lock_bets()

            # Ensure data is saved (BetState.lock_bets should do this, but be explicit)
            save_data(data)

            if not silent_lock:
                await self._send_embed(
                    ctx, TITLE_BETS_LOCKED, MSG_BETTING_LOCKED_SUMMARY, COLOR_SUCCESS
                )
            
            # Update live message to reflect locked state
            await update_live_message(self.bot, data)

    async def _process_winner_declaration(
        self,
        ctx: commands.Context,
        data: Data,
        winner: str
    ) -> None:
        """Process winner declaration and handle payouts."""
        from utils.bet_state import BetState, SessionBetState

        # Determine if we're in multi-session mode and need to resolve session
        session_id = None
        if is_multi_session_mode(data):
            # Try to find session by contestant name
            from data_manager import find_session_by_contestant
            tuple_found = find_session_by_contestant(winner, data)
            if tuple_found:
                session_id = tuple_found[0]

        if session_id:
            # Multi-session winner declaration
            if session_id not in data.get("betting_sessions", {}):
                await self._send_embed(
                    ctx, TITLE_BETTING_ERROR,
                    f"Session for contestant '{winner}' not found.", COLOR_ERROR
                )
                return

            session = data["betting_sessions"][session_id]
            # Create a wrapper dict with open/locked fields for SessionBetState
            betting_session: BettingSession = {
                "open": session.get("status") == "open",
                "locked": session.get("status") == "locked",
                "bets": session.get("bets", {}),
                "contestants": session.get("contestants", {}),
            }
            session_state = SessionBetState(data, betting_session)
            winner_info = session_state.declare_winner(winner)
            session["winner"] = winner
            session["status"] = "completed"
            session["closed_at"] = time.time()
            session["closed_by"] = str(ctx.author.id)

            # Remove from active sessions
            if session_id in data.get("active_sessions", []):
                data["active_sessions"].remove(session_id)

            save_data(data)

            await self._send_embed(
                ctx, f"Winner Declared: {winner}",
                f"Session '{session_id}' completed. Total pot: ${winner_info['total_pot']}, "
                f"Winning pot: ${winner_info['winning_pot']}",
                COLOR_SUCCESS
            )
            
            # Update live message to reflect winner declaration
            await update_live_message(self.bot, data, session_id=session_id)
        else:
            # Single-session winner declaration
            bet_state = BetState(data)
            winner_info = bet_state.declare_winner(winner)

            await self._send_embed(
                ctx, f"Winner Declared: {winner}",
                f"Total pot: ${winner_info['total_pot']}, Winning pot: ${winner_info['winning_pot']}",
                COLOR_SUCCESS
            )
            
            # Update live message to reflect winner declaration
            await update_live_message(self.bot, data)

    async def _close_session(
        self,
        ctx: commands.Context,
        session_id: str,
        winner_name: Optional[str] = None
    ) -> None:
        """Close a betting session and optionally declare a winner."""
        from utils.bet_state import SessionBetState

        data = load_data()

        if session_id not in data.get("betting_sessions", {}):
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR,
                f"Session '{session_id}' not found.", COLOR_ERROR
            )
            return

        session = data["betting_sessions"][session_id]

        # If winner is provided, process winner declaration first
        if winner_name:
            # Create a wrapper dict with open/locked fields for SessionBetState
            betting_session: BettingSession = {
                "open": session.get("status") == "open",
                "locked": session.get("status") == "locked",
                "bets": session.get("bets", {}),
                "contestants": session.get("contestants", {}),
            }
            session_state = SessionBetState(data, betting_session)
            winner_info = session_state.declare_winner(winner_name)

            session["winner"] = winner_name
            session["status"] = "completed"

            success_msg = f"Session '{session_id}' closed with winner '{winner_name}'. " \
                         f"Total pot: ${winner_info['total_pot']}, Winning pot: ${winner_info['winning_pot']}"
            
            # Update live message to reflect winner declaration
            await update_live_message(self.bot, data, session_id=session_id, winner_info=winner_info)
            
        else:
            # Just close the session without declaring winner
            session["status"] = "closed"
            success_msg = f"Session '{session_id}' closed (no winner declared)."

            # Update live message to reflect session closure
            await update_live_message(self.bot, data, session_id=session_id, betting_closed=True, close_summary="Session closed.")

    def _find_fuzzy_contestant(
        self, data: Data, choice_input: str
    ) -> Optional[Tuple[str, str]]:
        """Finds a contestant ID and name based on fuzzy matching for typo tolerance."""
        contestants = data["betting"]["contestants"]
        choice_lower = choice_input.lower()

        # Exact match
        for c_id, c_name in contestants.items():
            if c_name.lower() == choice_lower:
                return c_id, c_name

        # Partial match (e.g., "ali" for "Alice")
        for c_id, c_name in contestants.items():
            if len(choice_lower) >= 3 and choice_lower in c_name.lower():
                return c_id, c_name

        return None

    def _find_contestant_info(
        self, data: Data, choice_input: str
    ) -> Optional[Tuple[str, str]]:
        """Finds a contestant ID and name based on fuzzy matching for typo tolerance."""
        from data_manager import is_multi_session_mode, find_session_by_contestant

        # Check if we're in multi-session mode
        if is_multi_session_mode(data):
            # Use multi-session contestant lookup
            session_result = find_session_by_contestant(choice_input, data)
            if session_result:
                session_id, contestant_id, contestant_name = session_result
                return contestant_id, contestant_name
            # If no match in multi-session mode, return None
            return None
        else:
            # Legacy single-session mode
            # Try fuzzy matching first
            fuzzy_result = self._find_fuzzy_contestant(data, choice_input)
            if fuzzy_result:
                return fuzzy_result

            # Fall back to original method if no fuzzy match
            return BettingUtils.find_contestant_info(data, choice_input)

    async def _process_bet(
        self,
        channel: Optional[discord.TextChannel],
        data: Data,
        user_id: str,
        amount: int,
        choice: str,
        emoji: Optional[str] = None,
        notify_user: bool = True,
        session_id: Optional[str] = None,
    ) -> bool:
        """Centralized bet processing logic.
        Returns True if bet was successful, False otherwise."""

        # Ensure the user has an account and validate their balance
        ensure_user(data, user_id)
        user_balance = data["balances"][user_id]

        if amount <= 0:
            if notify_user and channel:
                await channel.send(
                    embed=discord.Embed(
                        title=TITLE_BETTING_ERROR,
                        description=MSG_AMOUNT_POSITIVE,
                        color=COLOR_ERROR,
                    )
                )
            return False

        # Balance warning for large bets (>= 70% of balance)
        bet_percentage = (amount / user_balance) * 100 if user_balance > 0 else 0
        if bet_percentage >= 70 and notify_user and channel:
            warning_emoji = "🚨" if bet_percentage >= 90 else "⚠️"
            await channel.send(
                embed=discord.Embed(
                    title=f"{warning_emoji} Large Bet Warning",
                    description=f"💰 **Your balance:** `{user_balance}` coins\n💸 **Bet amount:** `{amount}` coins ({bet_percentage:.0f}% of balance)\n\n⚠️ This is a significant portion of your funds. Bet placed successfully!",
                    color=COLOR_WARNING,
                )
            )

        if amount > user_balance:
            if notify_user and channel:
                shortfall = amount - user_balance
                await channel.send(
                    embed=discord.Embed(
                        title="❌ Insufficient Funds",
                        description=f"💰 **Your balance:** `{user_balance}` coins\n💸 **Bet amount:** `{amount}` coins\n❌ **You need:** `{shortfall}` more coins\n\n💡 *Tip: Use `!betall {choice}` to bet all your coins*",
                        color=COLOR_ERROR,
                    )
                )
            return False

        # Find and validate contestant (works for both single and multi-session)
        contestant_info = None

        # If an explicit session_id was provided, try to resolve the
        # contestant directly from that session first.
        if session_id:
            sess = data.get("betting_sessions", {}).get(session_id)
            if sess and sess.get("contestants"):
                # Try to match by display name (case-insensitive)
                for c_id, display in sess["contestants"].items():
                    if display.lower() == choice.lower():
                        contestant_info = (c_id, display)
                        break

        # If not found in specific session, fall back to global lookup
        if not contestant_info:
            contestant_info = self._find_contestant_info(data, choice)

        if not contestant_info:
            if notify_user and channel:
                await channel.send(
                    embed=discord.Embed(
                        title=TITLE_BETTING_ERROR,
                        description=f"Contestant '{choice}' not found.",
                        color=COLOR_ERROR,
                    )
                )
            return False

        # Place the bet
        from utils.bet_state import make_bet_info
        bet_payload = make_bet_info(amount, choice, emoji)
        set_bet(data, session_id, user_id, bet_payload)
        
        return True

async def setup(bot: commands.Bot) -> None:
    """Setup function for the BetUtils cog."""
    await bot.add_cog(BetUtils(bot))