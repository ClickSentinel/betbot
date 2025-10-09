import discord
from discord.ext import commands
from typing import Optional, Tuple, Dict, Any, cast
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
from data_manager import get_bets, set_bet, remove_bet, is_multi_session_mode, find_session_by_contestant
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
from utils.bet_state import BetState, SessionBetState
from utils.bet_state import WinnerInfo

# Import BetUtils for type hints
from .bet_utils import BetUtils


class BetCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.timer = BettingTimer(bot)
        data = load_data()
        self.bet_state = BetState(data)

        # Initialize the live message scheduler
        initialize_live_message_scheduler(bot)

        # Track programmatic reaction removals to prevent race conditions
        self._programmatic_removals: set = set()

    async def _check_permission(self, ctx: commands.Context, action: str) -> bool:
        """Check if the user has permission to perform an action."""
        # Import here to avoid circular imports
        from utils.betting_utils import BettingPermissions

        return await BettingPermissions.check_permission(ctx, action)

    def _cancel_bet_timer(self):
        """Cancel the current betting timer."""
        if hasattr(self.timer, 'cancel_timer'):
            self.timer.cancel_timer()

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

    async def _add_betting_reactions(self, message: discord.Message, data: Data) -> None:
        """Add betting reactions to a message in grouped order by contestant."""
        from config import SEPARATOR_EMOJI

        # Get contestant emojis from data
        contestant_1_emojis = data.get("contestant_1_emojis", [])
        contestant_2_emojis = data.get("contestant_2_emojis", [])

        # Add reactions in order: contestant 1 emojis, separator, contestant 2 emojis
        for emoji in contestant_1_emojis:
            await message.add_reaction(emoji)
        
        await message.add_reaction(SEPARATOR_EMOJI)
        
        for emoji in contestant_2_emojis:
            await message.add_reaction(emoji)

    async def _add_single_reaction_with_retry(
        self, message: discord.Message, emoji: str, max_retries: int = 3
    ) -> None:
        """Add a single reaction with retry logic for rate limiting."""
        import asyncio
        
        for attempt in range(max_retries + 1):
            try:
                await message.add_reaction(emoji)
                return  # Success
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    if attempt < max_retries:
                        # Exponential backoff: 1s, 2s, 4s...
                        delay = 2 ** attempt
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Max retries reached, re-raise
                        raise
                else:
                    # Other HTTP error, don't retry
                    raise

    async def _handle_timer_expired(self, ctx: commands.Context):
        """Handle timer expiration."""
        data = load_data()
        if not data["betting"]["open"]:
            return

        data["betting"]["locked"] = True
        self._clear_timer_state_in_data(data)
        save_data(data)

        await self._send_embed(
            ctx,
            TITLE_BETS_LOCKED,
            MSG_BETTING_TIMER_EXPIRED_SUMMARY,
            COLOR_WARNING,
        )

        # Update live message
        await update_live_message(self.bot, data)

    @commands.command(name="openbet", aliases=["ob"])
    async def openbet(
        self,
        ctx: commands.Context,
        name1: Optional[str] = None,
        name2: Optional[str] = None,
    ) -> None:
        data = load_data()

        if not await self._check_permission(ctx, "open betting rounds"):
            return

        # Check if both contestant names are provided and not empty
        if name1 is None or name2 is None or not name1.strip() or not name2.strip():
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_INVALID_OPENBET_FORMAT, COLOR_ERROR
            )
            return

        # Clean up the names by stripping whitespace
        name1 = name1.strip()
        name2 = name2.strip()

        # Check if contestant names are identical (case-insensitive)
        if name1.lower() == name2.lower():
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Contestant names cannot be identical.**\nPlease provide two different contestant names.\nExample: `!openbet Alice Bob`",
                COLOR_ERROR,
            )
            return

        # Check if contestant names are too long (Discord embed field limit
        # considerations)
        if len(name1) > 50 or len(name2) > 50:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Contestant names are too long.**\nPlease keep contestant names under 50 characters each.\nExample: `!openbet Alice Bob`",
                COLOR_ERROR,
            )
            return

        # If running in multi-session mode, allow opening additional
        # sessions regardless of legacy `data['betting']` flags. These
        # legacy flags only control the single-session flow and would
        # otherwise prevent creating new per-session rounds.
        from data_manager import is_multi_session_mode

        if not is_multi_session_mode(data):
            if data["betting"]["open"]:
                await self._send_embed(
                    ctx, TITLE_BETTING_ERROR, MSG_BET_ALREADY_OPEN, COLOR_ERROR
                )
                return
            if data["betting"]["locked"]:
                await self._send_embed(
                    ctx, TITLE_BETTING_ERROR, MSG_BET_LOCKED, COLOR_ERROR
                )
                return

        clear_live_message_info(data)
        self._cancel_bet_timer()

        # Create session ID
        data = load_data()
        if "next_session_id" not in data:
            data["next_session_id"] = 1  # type: ignore

        session_id = str(data["next_session_id"])  # type: ignore
        data["next_session_id"] = int(session_id) + 1  # type: ignore

        # For backward compatibility, also set up legacy betting structure
        data["betting"] = {
            "open": True,
            "locked": False,
            "bets": {},
            "contestants": {"1": name1, "2": name2},
        }
        if data["settings"]["enable_bet_timer"]:
            data["timer_end_time"] = time.time() + BET_TIMER_DURATION

        save_data(data)

        # Log betting session opened and record metric with session id
        logger.info(
            f"Betting session opened: {session_id} - {name1} vs {name2} by user {ctx.author}"
        )
        performance_monitor.record_metric(
            "betting.round_opened",
            1,
            {"contestant1": name1, "contestant2": name2, "session_id": session_id},
        )

        # Create live message
        main_chan_id = get_saved_bet_channel_id(data)
        target_channel: Optional[discord.TextChannel] = None

        if main_chan_id:
            channel_obj = self.bot.get_channel(main_chan_id)
            if isinstance(channel_obj, discord.TextChannel):
                target_channel = channel_obj

        if target_channel is None and isinstance(ctx.channel, discord.TextChannel):
            target_channel = ctx.channel

        if target_channel is None:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "Betting rounds can only be opened in a server text channel.",
                COLOR_ERROR,
            )
            return

        initial_embed_description = MSG_LIVE_BET_INITIAL_DESCRIPTION.format(
            contestant1_emoji=CONTESTANT_EMOJIS[0],
            name1=name1,
            contestant2_emoji=CONTESTANT_EMOJIS[1],
            name2=name2,
        )

        main_live_msg = None
        try:
            main_live_msg = await target_channel.send(
                embed=discord.Embed(
                    title=TITLE_LIVE_BETTING_ROUND,
                    description=initial_embed_description,
                    color=COLOR_GOLD,
                )
            )
            set_live_message_info(data, main_live_msg.id, target_channel.id)
            await update_live_message(self.bot, data, session_id=session_id)
        except Exception as e:
            logger.error(f"Error sending live message: {e}")
            set_live_message_info(data, None, None)
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_FAILED_SEND_LIVE_MESSAGE, COLOR_ERROR
            )
            return

        if main_live_msg:
            self._add_reactions_background(main_live_msg, data)

        # Send confirmation message
        session_note = f"\n\nSession ID: `{session_id}`"
        if data["settings"]["enable_bet_timer"]:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ROUND_OPENED,
                f"Betting round opened for **{name1}** vs **{name2}**! Bets will automatically lock in `{BET_TIMER_DURATION}` seconds." + session_note,
                COLOR_SUCCESS,
            )
        else:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ROUND_OPENED,
                f"Betting round opened for **{name1}** vs **{name2}**! Use `!lockbets` to close." + session_note,
                COLOR_SUCCESS,
            )

        # Schedule the betting timer if enabled
        if data["settings"]["enable_bet_timer"]:
            await self.timer.start_timer(
                ctx, BET_TIMER_DURATION, self._handle_timer_expired
            )

    @commands.command(name="lockbets", aliases=["lb"])
    async def lock_bets(self, ctx: commands.Context, target: Optional[str] = None) -> None:
        """Lock bets. If multi-session mode is active, an optional target (contestant
        name or session id) may be provided to select which session to lock.
        If omitted, the command will try to resolve by channel or fall back to a
        single active session when unambiguous.
        """
        if not await self._check_permission(ctx, "close betting rounds"):
            return

        data = load_data()

        # Attempt to resolve a session id when in multi-session mode
        session_id: Optional[str] = None

        if is_multi_session_mode(data):
            if target:
                # Prefer contestant name resolution first
                tuple_found = find_session_by_contestant(target, data)
                if tuple_found:
                    session_id = tuple_found[0]
                elif target in data.get("betting_sessions", {}):
                    session_id = target
            else:
                # Try channel-based resolution: if exactly one session is in this channel
                channel_sessions = [
                    sid
                    for sid, s in data.get("betting_sessions", {}).items()
                    if s.get("channel_id") == getattr(ctx.channel, "id", None)
                ]
                if len(channel_sessions) == 1:
                    session_id = channel_sessions[0]
                else:
                    # If only one active session exists globally, pick it
                    active = data.get("active_sessions", [])
                    if len(active) == 1:
                        session_id = active[0]

        bet_utils = cast(BetUtils, self.bot.get_cog("BetUtils"))
        if bet_utils:
            await bet_utils._lock_bets_internal(ctx, session_id=session_id)

    @commands.command(name="declarewinner", aliases=["dw"])
    async def declare_winner(self, ctx: commands.Context, winner: str) -> None:
        if not await self._check_permission(ctx, "declare winners"):
            return

        data = load_data()
        if not data["betting"]["locked"]:
            await self._send_embed(
                ctx, TITLE_CANNOT_CLOSE_BETS, MSG_INTERNAL_ERROR_LOCKED, COLOR_ERROR
            )
            return

        self._cancel_bet_timer()
        # Updated call
        bet_utils = cast(BetUtils, self.bot.get_cog("BetUtils"))
        if bet_utils:
            await bet_utils._process_winner_declaration(ctx, data, winner)

    @commands.command(name="closebet", aliases=["cb"])
    async def close_bet(self, ctx: commands.Context, *args) -> None:
        """Close bets. Usage:
        - `!closebet <winner>` : legacy behavior - declare winner across current round or resolved session
        - `!closebet <session_id>` : explicitly close a session (no winner)
        - `!closebet <session_id> <winner>` : explicitly close a session and declare a winner
        """
        data = load_data()

        if not await self._check_permission(ctx, "close betting rounds"):
            return

        if len(args) == 0:
            await self._send_embed(ctx, TITLE_CANNOT_CLOSE_BETS, "Missing argument: provide a winner name or a session id.", COLOR_ERROR)
            return

        # (moved helper to instance method _close_session)

        # If first arg matches a session id, treat as explicit session close
        target = args[0]

        if is_multi_session_mode(data) and target in data.get("betting_sessions", {}):
            # Optional winner can be provided as second arg
            winner_arg = args[1] if len(args) > 1 else None
            bet_utils = cast(BetUtils, self.bot.get_cog("BetUtils"))
            if bet_utils:
                await bet_utils._close_session(ctx, target, winner_arg)
            return

        # Otherwise fallback to legacy behavior: treat first arg as winner name
        winner = target

        # Attempt to resolve a session id for multi-session mode before locking
        session_id: Optional[str] = None

        if is_multi_session_mode(data):
            # Try to resolve by winner name first (unique contestant names)
            tuple_found = find_session_by_contestant(winner, data)
            if tuple_found:
                session_id = tuple_found[0]

        bet_utils = cast(BetUtils, self.bot.get_cog("BetUtils"))
        if bet_utils:
            if data["betting"]["open"]:
                await bet_utils._lock_bets_internal(ctx, silent_lock=True, session_id=session_id)
        data = load_data()

        self._cancel_bet_timer()
        # Declare winner using the existing flow
        bet_utils = cast(BetUtils, self.bot.get_cog("BetUtils"))
        if bet_utils:
            await bet_utils._process_winner_declaration(ctx, data, winner)

    @commands.command(name="closesession", aliases=["cs"])
    async def close_session(self, ctx: commands.Context, session_id: str, winner: Optional[str] = None) -> None:
        """Deprecated explicit session close wrapper retained for compatibility
        and tests. Closes a session by id and optionally declares a winner.
        """
        if not await self._check_permission(ctx, "close betting sessions"):
            return

        # Reuse the same logic as explicit session close in close_bet
        d = load_data()
        session = d.get("betting_sessions", {}).get(session_id)
        if not session:
            await self._send_embed(ctx, TITLE_BETTING_ERROR, f"Session '{session_id}' not found.", COLOR_ERROR)
            return

        # Delegate to close_bet's helper path by invoking close_bet with args
        # that match the explicit session close signature. This keeps behavior
        # consistent in one place.
        bet_utils = cast(BetUtils, self.bot.get_cog("BetUtils"))
        if bet_utils:
            await bet_utils._close_session(ctx, session_id, winner)

    @commands.command(name="setbetchannel", aliases=["sbc"])
    @commands.has_permissions(manage_guild=True)
    async def set_bet_channel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        data = load_data()
        if channel is None:
            if isinstance(ctx.channel, discord.TextChannel):
                channel = ctx.channel
            else:
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ERROR,
                    "This command must be used in a server text channel or by specifying a channel.",
                    COLOR_ERROR,
                )
                return

        set_live_message_info(
            data, None, channel.id
        )  # Clear existing message, set new channel
        save_data(data)
        await self._send_embed(
            ctx,
            TITLE_BETTING_CHANNEL_SET,
            f"Live betting message will now appear in {channel.mention}.",
            COLOR_SUCCESS,
        )

    @commands.command(name="togglebettimer", aliases=["tbt"])
    async def toggle_bet_timer(self, ctx: commands.Context) -> None:
        if not await self._check_permission(ctx, "toggle betting timer"):
            return

        data = load_data()
        data["settings"]["enable_bet_timer"] = not data["settings"]["enable_bet_timer"]
        save_data(data)

        status = "enabled" if data["settings"]["enable_bet_timer"] else "disabled"

        # Log timer toggle
        logger.info(f"Betting timer {status} by user {ctx.author}")
        performance_monitor.record_metric(
            "betting.timer_toggled", 1, {"status": status, "user": str(ctx.author)}
        )

        await self._send_embed(
            ctx,
            TITLE_TIMER_TOGGLED,
            f"Automatic betting timer has been **{status}**.",
            COLOR_INFO,
        )

        if not data["settings"]["enable_bet_timer"]:
            self._cancel_bet_timer()  # Cancel timer if disabled

    @commands.command(name="bet", aliases=["b"])
    async def place_bet(self, ctx: commands.Context, *args) -> None:
        data = load_data()

        # Handle !bet with no arguments
        if len(args) == 0:
            from data_manager import is_multi_session_mode

            if is_multi_session_mode(data):
                # Multi-session mode: show info about all active sessions
                active_sessions = data.get("active_sessions", [])
                if active_sessions:
                    session_info = []
                    total_contestants = 0
                    total_bets = 0

                    for session_id in active_sessions:
                        session = data["betting_sessions"].get(session_id, {})
                        if session.get("status") == "open":
                            contestants = session.get("contestants", {})
                            bets = session.get("bets", {})
                            session_info.append(
                                f"🎯 **{session_id}**: {', '.join(contestants.values())}"
                            )
                            total_contestants += len(contestants)
                            total_bets += len(bets)

                    if session_info:
                        no_args_bet_info = (
                            [
                                f"**Multi-Session Betting Active**",
                                f"**Active Sessions:** {len(session_info)}",
                                f"**Total Contestants:** {total_contestants}",
                                f"**Total Bets:** {total_bets}",
                                "",
                                "**Sessions:**",
                            ]
                            + session_info
                            + [
                                "",
                                f"**How to bet:** {MSG_PLACE_MANUAL_BET_INSTRUCTIONS}",
                            ]
                        )

                        await self._send_embed(
                            ctx,
                            TITLE_CURRENT_BETS_OVERVIEW,
                            "\n".join(no_args_bet_info),
                            COLOR_INFO,
                        )
                        return

                # No active sessions in multi-session mode
                await self._send_embed(
                    ctx, TITLE_NO_OPEN_BETTING_ROUND, MSG_NO_ACTIVE_BET, COLOR_ERROR
                )
                return
            else:
                # Legacy single-session mode
                if data["betting"]["open"]:
                    # Display current betting info, similar to !bettinginfo
                    contestants = data["betting"].get("contestants", {})
                    no_args_bet_info = [
                        f"**Betting Round Status:** {'Open' if data['betting']['open'] else 'Closed'}",
                        f"**Contestants:** {', '.join(contestants.values())}",
                        f"**Total Bets:** {len(data['betting']['bets'])}",
                        f"**How to bet:** {MSG_PLACE_MANUAL_BET_INSTRUCTIONS}",
                    ]
                    live_message_link = get_live_message_link(
                        self.bot,
                        data,
                        data["betting"]["open"] or data["betting"]["locked"],
                    )
                    await self._send_embed(
                        ctx,
                        TITLE_CURRENT_BETS_OVERVIEW,
                        "\n".join(no_args_bet_info)
                        + (
                            f"\n\nLive Message: {live_message_link}"
                            if live_message_link
                            else ""
                        ),
                        COLOR_INFO,
                    )
                elif data["betting"]["locked"]:
                    # Betting is locked - provide specific message with live link
                    live_message_link = get_live_message_link(
                        self.bot,
                        data,
                        True,  # Show live message link since bets are locked
                    )
                    if live_message_link:
                        await self._send_embed(
                            ctx,
                            TITLE_BETTING_ERROR,
                            MSG_BET_LOCKED_WITH_LIVE_LINK.format(
                                live_link=live_message_link
                            ),
                            COLOR_ERROR,
                        )
                    else:
                        await self._send_embed(
                            ctx,
                            TITLE_BETTING_ERROR,
                            MSG_BET_LOCKED_NO_NEW_BETS,
                            COLOR_ERROR,
                        )
                else:
                    await self._send_embed(
                        ctx, TITLE_NO_OPEN_BETTING_ROUND, MSG_NO_ACTIVE_BET, COLOR_ERROR
                    )
                return

        # Validate betting is available when arguments are provided
        from data_manager import is_multi_session_mode

        if is_multi_session_mode(data):
            # Multi-session mode: check if any sessions are open
            active_sessions = data.get("active_sessions", [])
            has_open_session = False

            for session_id in active_sessions:
                session = data["betting_sessions"].get(session_id, {})
                if session.get("status") == "open":
                    has_open_session = True
                    break

            if not has_open_session:
                await self._send_embed(
                    ctx,
                    TITLE_NO_OPEN_BETTING_ROUND,
                    MSG_NO_ACTIVE_BET_AND_MISSING_ARGS,
                    COLOR_ERROR,
                )
                return
        else:
            # Legacy single-session mode validation
            if not data["betting"]["open"]:
                await self._send_embed(
                    ctx,
                    TITLE_NO_OPEN_BETTING_ROUND,
                    MSG_NO_ACTIVE_BET_AND_MISSING_ARGS,
                    COLOR_ERROR,
                )
                return

            if data["betting"]["locked"]:
                await self._send_embed(
                    ctx, TITLE_BETTING_ERROR, MSG_BET_LOCKED_NO_NEW_BETS, COLOR_ERROR
                )
                return

        amount: Optional[int] = None
        choice: Optional[str] = None

        # Flexible argument parsing
        if len(args) == 2:
            try:
                # Try parsing as <choice> <amount>
                potential_choice = str(args[0])
                potential_amount = int(args[1])
                amount = potential_amount
                choice = potential_choice
            except ValueError:
                try:
                    # Try parsing as <amount> <choice>
                    potential_amount = int(args[0])
                    potential_choice = str(args[1])
                    amount = potential_amount
                    choice = potential_choice
                except ValueError:
                    # Both failed, invalid format
                    await self._send_embed(
                        ctx,
                        TITLE_INVALID_BET_FORMAT,
                        MSG_INVALID_BET_FORMAT,
                        COLOR_ERROR,
                    )
                    return
        else:
            # Incorrect number of arguments
            await self._send_embed(
                ctx, TITLE_INVALID_BET_FORMAT, MSG_INVALID_BET_FORMAT, COLOR_ERROR
            )
            return

        # Ensure the user has an account
        ensure_user(data, str(ctx.author.id))

        # Check if the amount is positive
        if amount <= 0:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_AMOUNT_POSITIVE, COLOR_ERROR
            )
            return

        contestant_info = cast(BetUtils, self.bot.get_cog("BetUtils"))._find_contestant_info(data, choice)
        if not contestant_info:
            # Generate helpful error message with available contestants
            contestants = data["betting"].get("contestants", {})
            if contestants:
                contestants_list = "\n".join(
                    [f"• **{name}**" for name in contestants.values()]
                )
                example_contestant = list(contestants.values())[0]
                error_msg = MSG_UNKNOWN_CONTESTANT.format(
                    contestant_name=choice,
                    contestants_list=contestants_list,
                    example_contestant=example_contestant,
                )
            else:
                error_msg = "No betting round is currently active."

            await self._send_embed(ctx, TITLE_BETTING_ERROR, error_msg, COLOR_ERROR)
            return

        contestant_id, contestant_name = contestant_info

        # Check if user is changing an existing bet
        user_id_str = str(ctx.author.id)
        existing_bet = get_bets(data).get(user_id_str)
        old_contestant = existing_bet.get("choice") if existing_bet else None
        old_amount = existing_bet.get("amount", 0) if existing_bet else 0

        # Use BetState for proper balance validation (accounts for existing bet
        # refunds)
        bet_state = BetState(data)
        user_balance = bet_state.economy.get_balance(user_id_str)
        required_additional = amount - old_amount

        if required_additional > user_balance:
            current_bet_info = (
                f"\n🎯 **Current bet:** `{old_amount}` coins on **{old_contestant}**"
                if existing_bet
                else ""
            )
            await self._send_embed(
                ctx,
                "❌ Insufficient Funds",
                f"💰 **Your balance:** `{user_balance}` coins\n💸 **Additional needed:** `{required_additional}` coins\n❌ **Total required:** `{amount}` coins{current_bet_info}\n\n💡 *Tip: Use `!betall {contestant_name}` to bet all your coins*",
                COLOR_ERROR,
            )
            return

        # Place the bet using centralized logic
        channel = ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None

        # Determine if this is a bet change for messaging
        is_bet_change = (
            existing_bet
            and old_contestant
            and old_contestant.lower() != contestant_name.lower()
        )

        success = await cast(BetUtils, self.bot.get_cog("BetUtils"))._process_bet(
            channel, data, user_id_str, amount, contestant_name, notify_user=False
        )

        if success:
            # Send appropriate success message
            if is_bet_change:
                amount_change = amount - old_amount
                change_indicator = (
                    f" (net change: {
                    '+'if amount_change > 0 else ''}{amount_change} coins)"
                    if amount_change != 0
                    else ""
                )
                await self._send_embed(
                    ctx,
                    "🔄 Bet Changed",
                    f"<@{ctx.author.id}>, your bet has been updated!\n\n"
                    f"**Before:** `{old_amount}` coins on **{old_contestant}**\n"
                    f"**After:** `{amount}` coins on **{contestant_name}**{change_indicator}\n\n"
                    f"🎯 Good luck with your new choice!",
                    COLOR_SUCCESS,
                )
            else:
                await self._send_embed(
                    ctx,
                    TITLE_BET_PLACED,
                    f"Your bet of `{amount}` coins on **{contestant_name}** has been placed!",
                    COLOR_SUCCESS,
                )
        else:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "Failed to place bet. Please try again.",
                COLOR_ERROR,
            )

    @commands.command(name="betall", aliases=["allin"])
    async def bet_all(
        self, ctx: commands.Context, *, contestant: Optional[str] = None
    ) -> None:
        """Bet all coins on a contestant."""
        data = load_data()

        # Check if betting is open
        if not data["betting"]["open"]:
            if data["betting"]["locked"]:
                live_message_link = get_live_message_link(self.bot, data, True)
                if live_message_link:
                    await self._send_embed(
                        ctx,
                        TITLE_BETTING_ERROR,
                        MSG_BET_LOCKED_WITH_LIVE_LINK.format(
                            live_link=live_message_link
                        ),
                        COLOR_ERROR,
                    )
                else:
                    await self._send_embed(
                        ctx,
                        TITLE_BETTING_ERROR,
                        MSG_BET_LOCKED_NO_NEW_BETS,
                        COLOR_ERROR,
                    )
            else:
                await self._send_embed(
                    ctx, TITLE_NO_OPEN_BETTING_ROUND, MSG_NO_ACTIVE_BET, COLOR_ERROR
                )
            return

        # Handle missing contestant parameter
        if not contestant:
            contestants = data["betting"].get("contestants", {})
            await self._send_embed(
                ctx,
                TITLE_INVALID_BET_FORMAT,
                f"**Missing contestant name.**\nUse `!betall <contestant>` to bet all your coins.\n\n**Available contestants:**\n{', '.join(contestants.values())}\n\n**Example:** `!betall {list(contestants.values())[0] if contestants.values() else 'Alice'}`",
                COLOR_ERROR,
            )
            return

        # Ensure user exists and get balance
        ensure_user(data, str(ctx.author.id))
        user_data = data.get("users", {}).get(str(ctx.author.id), {})
        user_balance = user_data.get("balance", 0)

        if user_balance <= 0:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                f"❌ You have no coins to bet! Your current balance is `{user_balance}` coins.",
                COLOR_ERROR,
            )
            return

        # Use existing bet processing logic with all coins
        channel = ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None
        success = await cast(BetUtils, self.bot.get_cog("BetUtils"))._process_bet(
            channel, data, str(ctx.author.id), user_balance, contestant, None, True
        )

        if success:
            save_data(data)
            schedule_live_message_update()
            await self._send_embed(
                ctx,
                TITLE_BET_PLACED,
                f"🎰 **All-in bet placed!**\n\n💰 **Amount:** `{user_balance}` coins (all your coins)\n🎯 **Choice:** **{contestant}**\n\n🔥 Good luck!",
                COLOR_SUCCESS,
            )

    @commands.command(name="mybet", aliases=["mb"])
    async def mybet(self, ctx: commands.Context) -> None:
        from data_manager import is_multi_session_mode, get_user_bets_across_sessions
        
        data = load_data()
        
        # Ensure the user has an account
        ensure_user(data, str(ctx.author.id))
        user_id = str(ctx.author.id)
        
        # Get all user bets across sessions
        user_bets = get_user_bets_across_sessions(data, user_id)
        
        if not user_bets:
            # No bets found - check if betting is available at all
            if is_multi_session_mode(data):
                active_sessions = data.get("active_sessions", [])
                if active_sessions:
                    await self._send_embed(
                        ctx,
                        TITLE_BETTING_ERROR,
                        "You have not placed any bets in the current active sessions.",
                        COLOR_ERROR,
                    )
                else:
                    await self._send_embed(
                        ctx, TITLE_BETTING_ERROR, MSG_NO_ACTIVE_BET, COLOR_ERROR
                    )
            else:
                if data["betting"]["open"]:
                    await self._send_embed(
                        ctx,
                        TITLE_BETTING_ERROR,
                        "You have not placed any bets in the current round.",
                        COLOR_ERROR,
                    )
                else:
                    await self._send_embed(
                        ctx, TITLE_BETTING_ERROR, MSG_NO_ACTIVE_BET, COLOR_ERROR
                    )
            return

        # Get user's current balance for context
        user_balance = data.get("balances", {}).get(user_id, 0)

        # Build bet information display
        bet_info = []
        
        if is_multi_session_mode(data):
            # Multi-session mode: show bets from each session
            total_bet_amount = 0
            
            for session_id, (session_title, bet) in user_bets.items():
                contestant_info = cast(BetUtils, self.bot.get_cog("BetUtils"))._find_contestant_info(data, bet["choice"])
                contestant_name = contestant_info[1] if contestant_info else "Unknown"
                
                bet_info.append(f"🎯 **{session_title}:** `{bet['amount']}` coins on **{contestant_name}**")
                total_bet_amount += bet["amount"]
            
            # Add summary
            bet_info.insert(0, f"💰 **Total Bet Amount:** `{total_bet_amount}` coins")
            bet_info.insert(1, f"💰 **Remaining Balance:** `{user_balance}` coins")
            
            # Calculate overall betting percentage
            total_funds = user_balance + total_bet_amount
            if total_funds > 0:
                bet_percentage = (total_bet_amount / total_funds) * 100
                bet_info.insert(2, f"📊 **Total Bet Size:** {bet_percentage:.0f}% of your funds")
            
            # Add session count
            bet_info.insert(3, f"🎲 **Active Sessions:** {len(user_bets)}")
        else:
            # Legacy single-session mode (shouldn't reach here with new function, but kept for safety)
            session_id, (session_title, bet) = next(iter(user_bets.items()))
            contestant_info = cast(BetUtils, self.bot.get_cog("BetUtils"))._find_contestant_info(data, bet["choice"])
            contestant_name = contestant_info[1] if contestant_info else "Unknown"
            
            # Calculate betting percentage
            bet_percentage = (
                (bet["amount"] / (user_balance + bet["amount"])) * 100
                if (user_balance + bet["amount"]) > 0
                else 0
            )
            
            bet_info = [
                f"🎯 **Current Bet:** `{bet['amount']}` coins on **{contestant_name}**",
                f"💰 **Remaining Balance:** `{user_balance}` coins",
                f"📊 **Bet Size:** {bet_percentage:.0f}% of your total funds",
            ]

        # Add betting status context
        if is_multi_session_mode(data):
            # In multi-session mode, check if any sessions are still open
            active_open_sessions = 0
            for session_id in data.get("active_sessions", []):
                session = data.get("betting_sessions", {}).get(session_id)
                if session and session.get("status") == "open":
                    active_open_sessions += 1
            
            if active_open_sessions > 0:
                bet_info.append(f"✅ **Status:** You can still modify bets in {active_open_sessions} active session{'s' if active_open_sessions != 1 else ''}")
            else:
                bet_info.append("⏳ **Status:** All sessions locked - awaiting results")
        else:
            # Legacy mode
            if data["betting"]["locked"]:
                bet_info.append("⏳ **Status:** Betting locked - awaiting results")
            else:
                remaining_time = None
                timer_end = data.get("timer_end_time")
                if timer_end:
                    remaining_time = max(0, int(timer_end - time.time()))

                if remaining_time and remaining_time > 0:
                    bet_info.append(
                        f"⏱️ **Time Remaining:** {remaining_time}s to modify bet"
                    )
                else:
                    bet_info.append("✅ **Status:** You can still modify your bet")

        await self._send_embed(
            ctx,
            "🎰 Your Current Bets" if len(user_bets) > 1 else "🎰 Your Current Bet",
            "\n".join(bet_info),
            COLOR_INFO,
        )

    @commands.command(name="bettinginfo", aliases=["bi"])
    async def bettinginfo(self, ctx: commands.Context) -> None:
        data = load_data()
        if not data["betting"]["open"]:
            if data["betting"]["locked"]:
                # Betting round exists but is locked - show current betting
                # info
                live_message_link = get_live_message_link(self.bot, data, True)
                contestants = data["betting"].get("contestants", {})
                locked_info = [
                    f"**Status:** 🔒 Betting Locked",
                    f"**Contestants:** {', '.join(contestants.values())}",
                    f"**Total Bets:** {len(data['betting']['bets'])}",
                    f"**Winner will be declared shortly**",
                ]
                await self._send_embed(
                    ctx,
                    "🔒 Betting Round - Locked",
                    "\n".join(locked_info)
                    + (
                        f"\n\n**Live Message:** [View Current Bets]({live_message_link})"
                        if live_message_link
                        else ""
                    ),
                    COLOR_ERROR,
                )
            else:
                # No betting round at all
                await self._send_embed(
                    ctx, TITLE_BETTING_ERROR, MSG_NO_ACTIVE_BET, COLOR_ERROR
                )
            return

        # --- Debug Info Gathering ---
        debug_info = [
            f"**Debug Info**",
            f"Betting Open: {data['betting']['open']}",
            f"Bets Locked: {data['betting']['locked']}",
            f"Total Bets: {len(data['betting']['bets'])}",
            f"Contestants: {', '.join(data['betting']['contestants'].values())}",
        ]

        # --- Live Message Link ---
        # Fix: Pass self.bot and is_active argument
        live_message_link = get_live_message_link(
            self.bot, data, data["betting"]["open"] or data["betting"]["locked"]
        )

        await self._send_embed(
            ctx,
            TITLE_CURRENT_BETS_OVERVIEW,
            "\n".join(debug_info)
            + (f"\n\nLive Message: {live_message_link}" if live_message_link else ""),
            COLOR_INFO,
        )

    @commands.command(name="livemessage", aliases=["lm"])
    async def livemessage(self, ctx: commands.Context, session_id: Optional[str] = None) -> None:
        """Post a link to the live betting message. If multi-session mode is active,
        you can specify a session ID to get the link for a specific session."""
        data = load_data()

        # Check if multi-session mode is active
        from data_manager import is_multi_session_mode

        if is_multi_session_mode(data):
            if session_id:
                # Check if the session exists
                if session_id not in data.get("betting_sessions", {}):
                    active_sessions = data.get("active_sessions", [])
                    if active_sessions:
                        sessions_list = ", ".join(active_sessions)
                        await self._send_embed(
                            ctx,
                            TITLE_BETTING_ERROR,
                            f"**Session '{session_id}' not found.**\n\nActive sessions: {sessions_list}",
                            COLOR_ERROR,
                        )
                    else:
                        await self._send_embed(
                            ctx,
                            TITLE_BETTING_ERROR,
                            f"**Session '{session_id}' not found.**\nNo active sessions.",
                            COLOR_ERROR,
                        )
                    return

                # Get session-specific live message link
                live_link = get_live_message_link_for_session(self.bot, data, session_id)
                if live_link:
                    session = data["betting_sessions"].get(session_id)
                    if session:
                        session_title = session.get("title", f"Session {session_id}")
                        await self._send_embed(
                            ctx,
                            f"📍 Live Message - {session_title}",
                            f"Here's the link to the live betting message for session `{session_id}`:\n\n{live_link}",
                            COLOR_INFO,
                        )
                    else:
                        await self._send_embed(
                            ctx,
                            TITLE_BETTING_ERROR,
                            f"Session data not found for `{session_id}`.",
                            COLOR_ERROR,
                        )
                else:
                    await self._send_embed(
                        ctx,
                        TITLE_BETTING_ERROR,
                        f"No live message found for session `{session_id}`.",
                        COLOR_ERROR,
                    )
            else:
                # No session specified - try to find the most relevant live message
                # First check if there's a legacy live message
                legacy_link = get_live_message_link_for_session(self.bot, data, None)
                if legacy_link:
                    await self._send_embed(
                        ctx,
                        "📍 Live Betting Message",
                        f"Here's the link to the live betting message:\n\n{legacy_link}",
                        COLOR_INFO,
                    )
                else:
                    # Check for active sessions in this channel
                    active_sessions = []
                    for sid in data.get("active_sessions", []):
                        session = data.get("betting_sessions", {}).get(sid, {})
                        if session.get("channel_id") == ctx.channel.id:
                            active_sessions.append(sid)

                    if len(active_sessions) == 1:
                        # Exactly one session in this channel
                        session_id = str(active_sessions[0])  # Ensure it's a string
                        live_link = get_live_message_link_for_session(self.bot, data, session_id)
                        if live_link:
                            session = data["betting_sessions"].get(session_id)
                            if session:
                                session_title = session.get("title", f"Session {session_id}")
                                await self._send_embed(
                                    ctx,
                                    f"📍 Live Message - {session_title}",
                                    f"Found one active session in this channel. Here's the link to the live betting message:\n\n{live_link}",
                                    COLOR_INFO,
                                )
                            else:
                                await self._send_embed(
                                    ctx,
                                    TITLE_BETTING_ERROR,
                                    f"Session data not found for `{session_id}`.",
                                    COLOR_ERROR,
                                )
                        else:
                            await self._send_embed(
                                ctx,
                                TITLE_BETTING_ERROR,
                                f"No live message found for session `{session_id}`.",
                                COLOR_ERROR,
                            )
                    elif len(active_sessions) > 1:
                        # Multiple sessions in this channel
                        sessions_list = ", ".join(f"`{sid}`" for sid in active_sessions)
                        await self._send_embed(
                            ctx,
                            TITLE_BETTING_ERROR,
                            f"Multiple active sessions found in this channel. Please specify which session you want:\n\nActive sessions: {sessions_list}\n\nUsage: `!livemessage <session_id>`",
                            COLOR_ERROR,
                        )
                    else:
                        # No sessions in this channel
                        all_sessions = list(data.get("active_sessions", []))
                        if all_sessions:
                            sessions_list = ", ".join(f"`{sid}`" for sid in all_sessions)
                            await self._send_embed(
                                ctx,
                                TITLE_BETTING_ERROR,
                                f"No active sessions found in this channel.\n\nActive sessions: {sessions_list}\n\nUsage: `!livemessage <session_id>`",
                                COLOR_ERROR,
                            )
                        else:
                            await self._send_embed(
                                ctx,
                                TITLE_BETTING_ERROR,
                                "No active betting sessions found.",
                                COLOR_ERROR,
                            )
        else:
            # Legacy single-session mode
            live_link = get_live_message_link_for_session(self.bot, data, None)
            if live_link:
                await self._send_embed(
                    ctx,
                    "📍 Live Betting Message",
                    f"Here's the link to the live betting message:\n\n{live_link}",
                    COLOR_INFO,
                )
            else:
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ERROR,
                    "No live betting message found.",
                    COLOR_ERROR,
                )

    @commands.command(name="setbettimer")
    @commands.has_permissions(manage_guild=True)
    async def set_bet_timer(self, ctx: commands.Context, seconds: int) -> None:
        data = load_data()
        if seconds < 0:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "Timer duration cannot be negative.",
                COLOR_ERROR,
            )
            return

        data["settings"]["bet_timer_duration"] = seconds
        save_data(data)

        await self._send_embed(
            ctx,
            TITLE_TIMER_TOGGLED,
            f"Bet timer duration set to `{seconds}` seconds.",
            COLOR_SUCCESS,
        )

    @commands.command(name="manualbet")
    # Added permission check for manualbet
    @commands.has_permissions(manage_guild=True)
    async def manual_bet(
        self, ctx: commands.Context, user: discord.User, amount: int, *, choice: str
    ) -> None:
        data = load_data()
        if not data["betting"]["open"]:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_NO_ACTIVE_BET, COLOR_ERROR
            )
            return

        if data["betting"]["locked"]:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_BET_LOCKED_NO_NEW_BETS, COLOR_ERROR
            )
            return

        # Ensure the user has an account
        ensure_user(data, str(user.id))  # Fix: Convert to string

        # Check if the amount is positive
        if amount <= 0:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_AMOUNT_POSITIVE, COLOR_ERROR
            )
            return

        contestant_info = cast(BetUtils, self.bot.get_cog("BetUtils"))._find_contestant_info(data, choice)
        if not contestant_info:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_INVALID_BET_FORMAT, COLOR_ERROR
            )
            return

        contestant_id, contestant_name = contestant_info

        # Deduct the bet amount from the user's balance
        user_balance = data["balances"][str(user.id)]
        if amount > user_balance:
            shortfall = amount - user_balance
            await self._send_embed(
                ctx,
                "❌ Insufficient Funds",
                f"💰 **User's balance:** `{user_balance}` coins\n💸 **Bet amount:** `{amount}` coins\n❌ **Shortfall:** `{shortfall}` coins",
                COLOR_ERROR,
            )
            return

        # Place the bet using accessor (session-aware)
        from utils.bet_state import make_bet_info

        bet_payload = make_bet_info(amount, contestant_name, None)
        # Determine if this contestant belongs to a session
        from data_manager import find_session_by_contestant

        session_tuple = find_session_by_contestant(contestant_name, data)
        session_id_for_set = session_tuple[0] if session_tuple else None

        # Deduct the amount from user's balance and persist
        data["balances"][str(user.id)] -= amount
        set_bet(data, session_id_for_set, str(user.id), bet_payload)
        # Persist manual bet immediately so live-message updater sees it
        save_data(data)

        # Schedule live message update (batched for better performance)
        # Prefer a session-targeted update when this manual bet belongs to a session
        try:
            if session_id_for_set:
                schedule_live_message_update_for_session(session_id_for_set)
            else:
                schedule_live_message_update()
        except Exception:
            schedule_live_message_update()

        await self._send_embed(
            ctx,
            TITLE_BET_PLACED,
            f"Manual bet of `{amount}` coins on **{contestant_name}** has been placed for {user.mention}!",
            COLOR_SUCCESS,
        )

    @commands.command(name="setbettargetchannel")
    @commands.has_permissions(manage_guild=True)
    async def set_bet_target_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        data = load_data()
        data["settings"]["bet_channel_id"] = channel.id
        save_data(data)

        await self._send_embed(
            ctx,
            TITLE_BETTING_CHANNEL_SET,
            f"Betting target channel set to {channel.mention}.",
            COLOR_SUCCESS,
        )

    @commands.command(name="debug")
    async def debug(self, ctx: commands.Context) -> None:
        data = load_data()
        debug_info = f"Betting Open: {
            data['betting']['open']}\nBets Locked: {
            data['betting']['locked']}\nTotal Bets: {
            len(
                data['betting']['bets'])}"
        await ctx.send(f"```\n{debug_info}\n```")

    @commands.command(name="togglereactiondebug", aliases=["trd"])
    @commands.has_permissions(manage_guild=True)
    async def toggle_reaction_debug(self, ctx: commands.Context) -> None:
        """Toggle extensive reaction debug logging on/off."""
        # Respect configuration: if runtime toggling is disabled, require editing config.py
        if not ALLOW_RUNTIME_REACTION_DEBUG_TOGGLE:
            description = (
                "Runtime toggling of reaction debug logging is disabled in configuration.\n"
                "To change this, edit `betbot/config.py` and set `REACTION_DEBUG_LOGGING_ENABLED`\n"
                "and/or `ALLOW_RUNTIME_REACTION_DEBUG_TOGGLE`, then restart the bot.\n\n"
                f"Debug log filename: `{REACTION_DEBUG_LOG_FILENAME}`"
            )
            await self._send_embed(
                ctx,
                "🔧 Reaction Debug Logging",
                description,
                COLOR_WARNING,
            )
            return

        # Toggle at runtime
        self.enable_reaction_debug_logging = not self.enable_reaction_debug_logging
        status = "**enabled**" if self.enable_reaction_debug_logging else "**disabled**"
        description = f"Extensive reaction debug logging is now {status}.\n\nDebug log filename: `{REACTION_DEBUG_LOG_FILENAME}`"
        await self._send_embed(
            ctx,
            "🔧 Reaction Debug Logging Toggled",
            description,
            COLOR_SUCCESS if self.enable_reaction_debug_logging else COLOR_WARNING,
        )

    @commands.command(name="forceclose", aliases=["fc"])
    async def force_close_betting(self, ctx: commands.Context) -> None:
        """Force close/reset betting state - use when betting is stuck."""
        if not await self._check_permission(ctx, "force close betting"):
            return

        data = load_data()

        # Reset betting state
        data["betting"] = {
            "open": False,
            "locked": False,
            "bets": {},
            "contestants": {},
        }

        # Clear live messages
        data["live_message"] = None
        data["live_channel"] = None
        data["live_secondary_message"] = None
        data["live_secondary_channel"] = None
        data["timer_end_time"] = None

        save_data(data)

        await self._send_embed(
            ctx,
            "🔧 Force Close Complete",
            "Betting state has been forcefully reset. You can now start a new round with `!openbet`.",
            discord.Color.green(),
        )

    @commands.command(name="listsessions", aliases=["ls"])
    async def list_sessions(self, ctx: commands.Context) -> None:
        """List all active betting sessions."""
        from data_manager import is_multi_session_mode

        data = load_data()

        if not is_multi_session_mode(data):
            # If betting_sessions exist (created by !openbet), treat them as
            # active sessions to surface session ids in the listing.
            if data.get("betting_sessions"):
                active_sessions = list(data.get("betting_sessions", {}).keys())
            # Check legacy single session
            if data["betting"]["open"] or data["betting"]["locked"]:
                contestants = data["betting"].get("contestants", {})
                status = "🟢 Open" if data["betting"]["open"] else "🔒 Locked"
                await self._send_embed(
                    ctx,
                    "📋 Betting Status",
                    f"**Legacy Session**\n"
                    f"**Status:** {status}\n"
                    f"**Contestants:** {', '.join(contestants.values())}\n"
                    f"**Total Bets:** {len(data['betting']['bets'])}\n\n"
                    f"💡 Use `!openbet` to start a new betting round (multi-session mode enabled automatically)",
                    COLOR_INFO,
                )
            else:
                await self._send_embed(
                    ctx,
                    "📋 No Active Sessions",
                    "No betting sessions are currently active.\n\n"
                    f"🎯 **Start a session:** `!openbet Contestant1 Contestant2`\n"
                    f"📊 **Legacy note:** `!openbet Contestant1 Contestant2`",
                    COLOR_INFO,
                )
            return

        # Multi-session mode
        active_sessions = data.get("active_sessions", [])

        if not active_sessions:
            await self._send_embed(
                ctx,
                "📋 No Active Sessions",
                "No betting sessions are currently active.\n\n"
                f"🎯 **Start a session:** `!openbet Contestant1 Contestant2`",
                COLOR_INFO,
            )
            return

        session_list = []
        total_bets = 0
        open_sessions = 0

        for session_id in active_sessions:
            session = data["betting_sessions"].get(session_id, {})
            contestants = session.get("contestants", {})
            bets = session.get("bets", {})
            status = session.get("status", "unknown")

            status_emoji = (
                "🟢" if status == "open" else "🔒" if status == "locked" else "❓"
            )

            session_list.append(
                f"{status_emoji} **{session_id}**\n"
                f"   └─ {', '.join(contestants.values())} ({len(bets)} bets)"
            )

            total_bets += len(bets)
            if status == "open":
                open_sessions += 1

        summary = [
            f"**Active Sessions:** {len(active_sessions)}",
            f"**Open for Betting:** {open_sessions}",
            f"**Total Bets:** {total_bets}",
            "",
            "**Sessions:**",
        ]

        await self._send_embed(
            ctx,
            "📋 Active Betting Sessions",
            "\n".join(summary + session_list)
            + f"\n\n💡 Use `!sessioninfo <session_id>` for details",
            COLOR_INFO,
        )

    @commands.command(name="sessioninfo", aliases=["si"])
    async def session_info(
        self, ctx: commands.Context, session_id: Optional[str] = None
    ) -> None:
        """Show detailed information about a specific session."""
        from data_manager import is_multi_session_mode

        data = load_data()

        if not is_multi_session_mode(data):
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "Multi-session mode is not active.\nUse `!bettinginfo` for legacy session info.",
                COLOR_ERROR,
            )
            return

        if not session_id:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Missing session ID.**\nUsage: `!sessioninfo <session_id>`\nExample: `!sessioninfo nfl_game`",
                COLOR_ERROR,
            )
            return

        session = data.get("betting_sessions", {}).get(session_id)
        if not session:
            active_sessions = data.get("active_sessions", [])
            if active_sessions:
                sessions_list = ", ".join(active_sessions)
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ERROR,
                    f"**Session '{session_id}' not found.**\n\nActive sessions: {sessions_list}",
                    COLOR_ERROR,
                )
            else:
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ERROR,
                    f"**Session '{session_id}' not found.**\nNo active sessions exist.",
                    COLOR_ERROR,
                )
            return

        # Gather session details
        contestants = session.get("contestants", {})
        bets = session.get("bets", {})
        status = session.get("status", "unknown")
        timer_config = session.get("timer_config", {})
        created_at = session.get("created_at", 0)
        created_by = session.get("created_by")

        # Calculate betting statistics
        total_pot = sum(bet["amount"] for bet in bets.values())

        contestant_stats = {}
        for contestant_key, contestant_name in contestants.items():
            contestant_bets = [
                bet for bet in bets.values() if bet["choice"] == contestant_name.lower()
            ]
            contestant_stats[contestant_name] = {
                "bets": len(contestant_bets),
                "pot": sum(bet["amount"] for bet in contestant_bets),
            }

        # Status display
        status_emoji = (
            "🟢" if status == "open" else "🔒" if status == "locked" else "❌"
        )
        status_text = status.title()

        # Timer info
        timer_info = "Disabled"
        if timer_config.get("enabled"):
            duration = timer_config.get("duration", 300)
            timer_info = f"{duration} seconds"

        # Creation info
        created_text = "Unknown"
        if created_at > 0:
            import datetime

            created_time = datetime.datetime.fromtimestamp(created_at)
            created_text = created_time.strftime("%Y-%m-%d %H:%M:%S")

        creator_text = "Unknown"
        if created_by:
            try:
                creator = await self.bot.fetch_user(int(created_by))
                creator_text = creator.display_name
            except:
                creator_text = f"User ID: {created_by}"

        # Build info display
        info_parts = [
            f"**Status:** {status_emoji} {status_text}",
            f"**Contestants:** {', '.join(contestants.values())}",
            f"**Total Bets:** {len(bets)}",
            f"**Total Pot:** {total_pot} coins",
            f"**Timer:** {timer_info}",
            f"**Created:** {created_text}",
            f"**Creator:** {creator_text}",
        ]

        # Add betting breakdown if there are bets
        if bets:
            info_parts.append("")
            info_parts.append("**Betting Breakdown:**")
            for contestant_name, stats in contestant_stats.items():
                percentage = (stats["pot"] / total_pot * 100) if total_pot > 0 else 0
                info_parts.append(
                    f"• **{contestant_name}**: {stats['bets']} bets, {stats['pot']} coins ({percentage:.1f}%)"
                )

        await self._send_embed(
            ctx,
            f"📊 Session Info: {session_id}",
            "\n".join(info_parts),
            COLOR_INFO,
        )


async def setup(bot):
    """Setup function for the bet_commands cog."""
    await bot.add_cog(BetCommands(bot))