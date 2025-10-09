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


class Betting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.timer = BettingTimer(bot)
        data = load_data()
        self.bet_state = BetState(data)

        # Initialize the live message scheduler
        initialize_live_message_scheduler(bot)

        # Track programmatic reaction removals to prevent race conditions
        self._programmatic_removals: set = set()
        self._programmatic_removals_timestamps: dict = {}

        # Setup reaction debug logging
        import os

        # Build a safe path for the reaction debug file under the package logs dir
        # We will never expose the absolute path in messages sent to Discord.
        logs_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "logs")
        )
        self.reaction_log_file = os.path.join(logs_dir, REACTION_DEBUG_LOG_FILENAME)
        # Create logs directory if it doesn't exist
        os.makedirs(os.path.dirname(self.reaction_log_file), exist_ok=True)

        # Track pending reaction bets for batching multiple rapid reactions
        # user_id -> pending bet info
        self._pending_reaction_bets: Dict[int, Dict[str, Any]] = {}
        # user_id -> timer task
        self._reaction_timers: Dict[int, asyncio.Task] = {}

        # Track users currently in reaction cleanup phase
        # user_ids currently having reactions cleaned up
        self._users_in_cleanup: set = set()

        # Queue for reactions that arrive during cleanup phase
        # user_id -> latest deferred reaction info
        self._deferred_reactions: Dict[int, Dict[str, Any]] = {}

        # Sequence counter to handle async delivery timing issues
        self._reaction_sequence: int = 0

        # Toggle for extensive reaction debug logging. Default comes from config.
        # If runtime toggling is disabled via config, the command will not allow
        # changing this value.
        self.enable_reaction_debug_logging = bool(REACTION_DEBUG_LOGGING_ENABLED)

        # Rate-limit logs about bot-own reaction checks to avoid flooding
        self._last_bot_own_log = 0.0

    def _is_own_reaction_user(self, payload_user_id: int) -> bool:
        """Return True if the payload user id belongs to this bot instance.

        This helper is defensive: it handles cases where `self.bot.user` may
        not be populated yet (e.g. during startup or restarts) and logs useful
        debug information so we can see why a reaction was ignored.
        """
        bot_user = getattr(self.bot, "user", None)
        if not bot_user:
            # Bot user not ready yet (startup); do not treat payload as bot
            # Log this more verbosely since it can indicate startup timing issues
            self._log_reaction_debug(
                f"🔍 REACTION CHECK: bot.user not set; payload_user_id={payload_user_id}"
            )
            return False

        bot_user_id = getattr(bot_user, "id", None)
        if bot_user_id is None:
            self._log_reaction_debug(
                f"🔍 REACTION CHECK: bot.user.id is None; payload_user_id={payload_user_id}"
            )
            return False

        try:
            # Defensive cast in case of odd types
            if int(payload_user_id) == int(bot_user_id):
                # Rate-limit this particular log to once every 3 seconds to
                # avoid spamming the console when the bot is adding many
                # reactions to a message.
                now = time.time()
                if now - self._last_bot_own_log > 3.0:
                    self._log_reaction_debug(
                        f"🔍 REACTION CHECK: Ignoring bot's own reaction (payload_user_id={payload_user_id}, bot_user_id={bot_user_id})"
                    )
                    self._last_bot_own_log = now
                return True
        except Exception:
            # If comparison fails for whatever reason, don't treat it as bot
            self._log_reaction_debug(
                f"🔍 REACTION CHECK: Failed to compare ids payload={payload_user_id}, bot={bot_user_id}"
            )
            return False

        return False

    def _log_reaction_debug(self, message: str) -> None:
        """Log reaction debug messages to both console and file."""
        # Early exit if debug logging is disabled
        if not self.enable_reaction_debug_logging:
            return

        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        formatted_message = f"[{timestamp}] {message}"

        # Print to console
        print(formatted_message)

        # Write to debug log file
        try:
            with open(self.reaction_log_file, "a", encoding="utf-8") as f:
                f.write(formatted_message + "\n")
                f.flush()  # Ensure immediate write
        except Exception as e:
            print(f"Error writing to reaction debug log: {e}")

    # --- Helper Methods for Deduplication ---

    def _create_removal_key(self, message_id: int, user_id: int, emoji: str) -> str:
        """Create a unique key for tracking programmatic reaction removals."""
        return f"{message_id}:{user_id}:{emoji}"

    def _mark_programmatic_removal(
        self, message_id: int, user_id: int, emoji: str
    ) -> None:
        """Mark a reaction removal as programmatic to avoid processing it as user-initiated."""
        key = self._create_removal_key(message_id, user_id, emoji)
        current_time = time.time()
        self._programmatic_removals.add(key)
        self._programmatic_removals_timestamps[key] = current_time

        # Clean up old entries (older than 30 seconds)
        cutoff_time = current_time - 30
        old_keys = [
            k
            for k, t in self._programmatic_removals_timestamps.items()
            if t < cutoff_time
        ]
        for old_key in old_keys:
            self._programmatic_removals.discard(old_key)
            self._programmatic_removals_timestamps.pop(old_key, None)

    def _is_programmatic_removal(
        self, message_id: int, user_id: int, emoji: str
    ) -> bool:
        """Check if a reaction removal is programmatic and remove it from tracking."""
        key = self._create_removal_key(message_id, user_id, emoji)
        if key in self._programmatic_removals:
            self._programmatic_removals.remove(key)
            self._programmatic_removals_timestamps.pop(key, None)
            return True
        return False

    # --- Reaction Batching Methods ---

    def _cancel_user_reaction_timer(self, user_id: int) -> None:
        """Cancel any existing reaction timer for a user."""
        if user_id in self._reaction_timers:
            self._log_reaction_debug(
                f"🔍 CANCEL TIMER: Cancelling existing timer for user {user_id}"
            )
            task = self._reaction_timers[user_id]
            if not task.done():
                try:
                    task.cancel()
                    self._log_reaction_debug(
                        f"🔍 CANCEL TIMER: Successfully cancelled timer for user {user_id}"
                    )
                except Exception as e:
                    self._log_reaction_debug(
                        f"🔍 CANCEL TIMER: Error cancelling timer for user {user_id}: {e}"
                    )
            else:
                self._log_reaction_debug(
                    f"🔍 CANCEL TIMER: Timer for user {user_id} was already done"
                )
            # Always remove from tracking dict, even if cancel failed
            del self._reaction_timers[user_id]
            self._log_reaction_debug(
                f"🔍 CANCEL TIMER: Removed timer from tracking for user {user_id}"
            )
        else:
            self._log_reaction_debug(
                f"🔍 CANCEL TIMER: No existing timer to cancel for user {user_id}"
            )

    async def _process_batched_reaction(self, user_id: int) -> None:
        """Process the final batched reaction after the delay period."""
        self._log_reaction_debug(
            f"🔍 PROCESS BATCH: Processing batched reaction for user {user_id}"
        )
        try:
            # Remove the timer from tracking
            self._reaction_timers.pop(user_id, None)
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: Removed timer for user {user_id}"
            )

            # Get the pending bet info
            if user_id not in self._pending_reaction_bets:
                self._log_reaction_debug(
                    f"🔍 PROCESS BATCH: No pending bet for user {user_id}, nothing to do"
                )
                return  # No pending bet, nothing to do

            bet_info = self._pending_reaction_bets.pop(user_id)
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: Retrieved pending bet info for user {user_id}"
            )

            # Extract the bet information
            message = bet_info["message"]
            user = bet_info["user"]
            data = bet_info["data"]
            channel = bet_info["channel"]

            # Extract the bet information from the stored data
            # The batching system already captured the latest reaction that
            # arrived
            contestant_name = bet_info["contestant_name"]
            bet_amount = bet_info["bet_amount"]
            final_emoji = bet_info["emoji"]
            sequence = bet_info.get("sequence", "unknown")
            timestamp = bet_info.get("timestamp", 0)

            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: Final bet details - {contestant_name} for {bet_amount} coins, emoji {final_emoji} (sequence: {sequence}, timestamp: {timestamp:.3f})"
            )

            # Process the final bet
            user_id_str = str(user.id)
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: Calling _process_bet for user {user_id_str}"
            )
            # Prefer session_id recorded with the pending reaction (if any)
            session_for_bet = bet_info.get("session_id")
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: session_for_bet={session_for_bet}"
            )
            success = await self._process_bet(
                channel=channel if isinstance(channel, discord.TextChannel) else None,
                data=data,
                user_id=user_id_str,
                amount=bet_amount,
                choice=contestant_name,
                emoji=final_emoji,
                notify_user=False,  # Don't send notification messages for reaction bets
                session_id=session_for_bet,
            )
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: _process_bet returned success={success}"
            )

            # Always clean up old reactions, but behavior depends on success
            # Mark user as in cleanup to defer any new reactions during this
            # process
            self._users_in_cleanup.add(user_id)
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: User {user_id} marked as in cleanup phase"
            )

            if success:
                self._log_reaction_debug(
                    f"🔍 PROCESS BATCH: Bet successful, removing other reactions (keeping {final_emoji})"
                )
                # Remove all OTHER betting reactions from the user, but keep the final one
                # The final emoji is already on the message from Discord, so we
                # just exclude it from removal
                await self._remove_user_betting_reactions(
                    message, user, data, exclude_emoji=final_emoji
                )
                self._log_reaction_debug(
                    f"🔍 PROCESS BATCH: Reaction cleanup complete for successful bet"
                )
            else:
                self._log_reaction_debug(
                    f"🔍 PROCESS BATCH: Bet failed, removing ALL reactions including {final_emoji}"
                )
                # If bet failed, remove ALL reactions including the final one
                await self._remove_user_betting_reactions(
                    message, user, data, exclude_emoji=None
                )
                self._log_reaction_debug(
                    f"🔍 PROCESS BATCH: Reaction cleanup complete for failed bet"
                )

            # Remove user from cleanup phase - new reactions can now be
            # processed
            self._users_in_cleanup.discard(user_id)
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: User {user_id} removed from cleanup phase"
            )

            # Process any deferred reactions for this user
            await self._process_deferred_reactions(user_id)

        except Exception as e:
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: Error processing batched reaction for user {user_id}: {e}"
            )
            # Clean up on error
            self._pending_reaction_bets.pop(user_id, None)
            self._reaction_timers.pop(user_id, None)
            # Also clean up cleanup tracking
            self._users_in_cleanup.discard(user_id)
            # Clean up any pending deferred reactions
            self._deferred_reactions.pop(user_id, None)
            self._log_reaction_debug(
                f"🔍 PROCESS BATCH: User {user_id} removed from cleanup phase (error cleanup)"
            )

    async def _delayed_reaction_processing(self, user_id: int) -> None:
        """Wait for a short delay, then process the batched reaction."""
        self._log_reaction_debug(
            f"🔍 PRIMARY TIMER: Starting delayed processing for user {user_id}"
        )
        try:
            # Wait for 1.5 seconds to allow batching of multiple rapid
            # reactions
            self._log_reaction_debug(
                f"🔍 PRIMARY TIMER: Waiting 1.5 seconds for user {user_id}"
            )
            await asyncio.sleep(1.5)
            self._log_reaction_debug(
                f"🔍 PRIMARY TIMER: Wait complete, processing batch for user {user_id}"
            )
            # Process the final batched reaction
            await self._process_batched_reaction(user_id)
            self._log_reaction_debug(
                f"🔍 PRIMARY TIMER: Batch processing complete for user {user_id}"
            )
        except asyncio.CancelledError:
            self._log_reaction_debug(
                f"🔍 PRIMARY TIMER: Timer cancelled for user {user_id}"
            )
            # Timer was cancelled due to a new reaction
            # DO NOT clean up pending bets here - the new timer needs that
            # data!
            raise
        except Exception as e:
            self._log_reaction_debug(
                f"🔍 PRIMARY TIMER: Error in delayed reaction processing for user {user_id}: {e}"
            )
            # Clean up on error
            self._pending_reaction_bets.pop(user_id, None)
            self._reaction_timers.pop(user_id, None)

    async def _backup_reaction_processing(self, user_id: int, delay: float) -> None:
        """Backup processing to ensure bets don't get lost due to timer issues."""
        self._log_reaction_debug(
            f"🔍 BACKUP TIMER: Starting backup processing for user {user_id} with {delay}s delay"
        )
        try:
            await asyncio.sleep(delay)
            self._log_reaction_debug(
                f"🔍 BACKUP TIMER: Backup delay complete for user {user_id}"
            )
            # Check if the user still has a pending bet that wasn't processed
            has_pending = user_id in self._pending_reaction_bets
            has_timer = user_id in self._reaction_timers
            self._log_reaction_debug(
                f"🔍 BACKUP TIMER: User {user_id} - has_pending={has_pending}, has_timer={has_timer}"
            )

            if has_pending and not has_timer:
                self._log_reaction_debug(
                    f"⚠️ BACKUP TIMER: Primary timer failed for user {user_id}, processing backup bet"
                )
                await self._process_batched_reaction(user_id)
            else:
                self._log_reaction_debug(
                    f"🔍 BACKUP TIMER: Primary timer handled user {user_id}, no backup needed"
                )
            # If primary timer is still running, let it handle the processing
        except Exception as e:
            self._log_reaction_debug(
                f"🔍 BACKUP TIMER: Error in backup reaction processing for user {user_id}: {e}"
            )

    async def _process_deferred_reactions(self, user_id: int) -> None:
        """Process any reactions that were deferred during cleanup phase."""
        if user_id not in self._deferred_reactions:
            self._log_reaction_debug(
                f"🔍 DEFERRED: No deferred reactions for user {user_id}"
            )
            return

        deferred = self._deferred_reactions.pop(user_id)
        self._log_reaction_debug(
            f"🔍 DEFERRED: Processing deferred reaction for user {user_id}: {
                deferred['contestant_name']} for {
                deferred['bet_amount']} coins"
        )

        try:
            # Extract the stored information
            payload = deferred["payload"]
            message = deferred["message"]
            user = deferred["user"]
            contestant_name = deferred["contestant_name"]
            bet_amount = deferred["bet_amount"]
            channel = deferred["channel"]

            # Refresh data to get current state
            current_data = load_data()

            # Re-check if betting is still open
            if not current_data["betting"]["open"]:
                self._log_reaction_debug(
                    f"🔍 DEFERRED: Betting is now closed, removing deferred reaction"
                )
                await message.remove_reaction(payload.emoji, user)
                return

            # Re-check user balance (it may have changed)
            ensure_user(current_data, str(user.id))
            current_balance = current_data["balances"][str(user.id)]
            if bet_amount > current_balance:
                self._log_reaction_debug(
                    f"🔍 DEFERRED: Insufficient balance for deferred reaction, removing"
                )
                await message.remove_reaction(payload.emoji, user)
                shortfall = bet_amount - current_balance
                embed = discord.Embed(
                    title="❌ Insufficient Funds",
                    description=f"<@{user.id}> 💰 **Your balance:** `{current_balance}` coins\n💸 **Reaction bet:** `{bet_amount}` coins\n❌ **You need:** `{shortfall}` more coins",
                    color=COLOR_ERROR,
                )
                await channel.send(embed=embed)
                return

            self._log_reaction_debug(
                f"🔍 DEFERRED: Starting batching system for deferred reaction of user {
                    user.id}"
            )

            # Now process the deferred reaction using the normal batching system
            # Cancel any existing timer for this user (shouldn't be any, but be
            # safe)
            self._cancel_user_reaction_timer(user.id)

            # Store the pending bet with sequence info from deferred reaction
            sequence = deferred.get("sequence", 0)
            timestamp = deferred.get("timestamp", 0)

            self._pending_reaction_bets[user.id] = {
                "message": message,
                "user": user,
                "data": current_data,  # Use refreshed data
                "contestant_name": contestant_name,
                "bet_amount": bet_amount,
                "emoji": str(payload.emoji),
                "channel": channel,
                "session_id": deferred.get("session_id"),
                "raw_emoji": payload.emoji,
                "sequence": sequence,
                "timestamp": timestamp,
            }

            # Start the timers
            primary_task = asyncio.create_task(
                self._delayed_reaction_processing(user.id)
            )
            # Backup task runs independently - intentionally not stored
            asyncio.create_task(self._backup_reaction_processing(user.id, 3.0))
            self._reaction_timers[user.id] = primary_task

            self._log_reaction_debug(
                f"🔍 DEFERRED: Successfully started processing for deferred reaction of user {
                    user.id}"
            )

        except Exception as e:
            self._log_reaction_debug(
                f"🔍 DEFERRED: Error processing deferred reaction for user {user_id}: {e}"
            )

    async def _check_permission(self, ctx: commands.Context, action: str) -> bool:
        """Centralized permission check for betting actions."""
        return await BettingPermissions.check_permission(ctx, action)

    async def _send_embed(
        self, ctx: commands.Context, title: str, description: str, color: discord.Color
    ) -> None:
        """Sends a consistent embed message."""
        await BettingUtils.send_embed(ctx, title, description, color)

    def _find_fuzzy_contestant(
        self, data: Data, input_name: str
    ) -> Optional[Tuple[str, str]]:
        """Find contestant with fuzzy matching for typo tolerance."""
        # Use accessor for compatibility with multi-session mode
        contestants = data.get("betting", {}).get("contestants", {})
        if not contestants:
            return None

        input_lower = input_name.lower().strip()

        # First try exact match (case insensitive)
        for contestant_id, name in contestants.items():
            if name.lower() == input_lower:
                return contestant_id, name

        # Then try partial match (starts with)
        matches = []
        for contestant_id, name in contestants.items():
            if name.lower().startswith(input_lower):
                matches.append((contestant_id, name))

        # If exactly one partial match, use it
        if len(matches) == 1:
            return matches[0]

        # Try contains match if no partial matches
        if not matches:
            for contestant_id, name in contestants.items():
                if input_lower in name.lower():
                    matches.append((contestant_id, name))

        # If exactly one contains match, use it
        if len(matches) == 1:
            return matches[0]

        # No unique match found
        return None

    def _clear_timer_state_in_data(self, data: Data) -> None:
        """Clears timer-related data. Note: Does not save data - caller must save."""
        data["timer_end_time"] = None

    async def _enforce_single_reaction_per_user(
        self, message: discord.Message, user: discord.User, data: Data, keep_emoji: str
    ) -> None:
        """Ensures user only has one betting reaction on the message - removes all others except keep_emoji"""

        self._log_reaction_debug(
            f"🔍 ENFORCE SINGLE: Cleaning up reactions for user {
                user.id}, keeping {keep_emoji}"
        )

        try:
            # Get fresh message to see current reactions
            fresh_message = await message.channel.fetch_message(message.id)

            reactions_to_remove = []
            for reaction in fresh_message.reactions:
                emoji_str = str(reaction.emoji)

                # Skip if this is the emoji we want to keep
                if emoji_str == keep_emoji:
                    self._log_reaction_debug(
                        f"🔍 ENFORCE SINGLE: Keeping reaction {emoji_str}"
                    )
                    continue

                # Check if this is a betting emoji
                contestant_id = _get_contestant_from_emoji(data, emoji_str)
                if not contestant_id:
                    continue  # Not a betting emoji, ignore

                # Check if user has reacted with this emoji
                user_has_this_reaction = False
                async for reaction_user in reaction.users():
                    if reaction_user.id == user.id:
                        user_has_this_reaction = True
                        break

                if user_has_this_reaction:
                    reactions_to_remove.append((reaction, emoji_str))
                    self._log_reaction_debug(
                        f"🔍 ENFORCE SINGLE: Will remove user reaction {emoji_str}"
                    )

            # Remove the unwanted reactions
            for reaction, emoji_str in reactions_to_remove:
                try:
                    # Mark this removal as programmatic to prevent bet refunds
                    self._mark_programmatic_removal(message.id, user.id, emoji_str)
                    await reaction.remove(user)
                    self._log_reaction_debug(
                        f"🔍 ENFORCE SINGLE: Removed user reaction {emoji_str}"
                    )
                except discord.NotFound:
                    self._log_reaction_debug(
                        f"🔍 ENFORCE SINGLE: Reaction {emoji_str} already removed"
                    )
                except discord.HTTPException as e:
                    # If we lack permissions (HTTP 403 / Missing Permissions), then
                    # the attempted programmatic removal didn't happen. Keep the
                    # programmatic mark so that any immediate on_raw_reaction_remove
                    # events are treated as programmatic and ignored. This avoids
                    # the bot mistakenly refunding bets when it couldn't remove
                    # reactions itself.
                    err_text = str(e)
                    if "Missing Permissions" in err_text or "403" in err_text:
                        self._log_reaction_debug(
                            f"🔍 ENFORCE SINGLE: Missing permissions removing reaction {emoji_str}: {e} - keeping programmatic mark"
                        )
                        # Do not clear the programmatic removal mark here; keep it
                        # until it expires to avoid processing the subsequent
                        # on_raw_reaction_remove as a user action.
                    else:
                        if "Unknown Message" in err_text or "Unknown Emoji" in err_text:
                            self._log_reaction_debug(
                                f"🔍 ENFORCE SINGLE: Reaction {emoji_str} no longer exists: {e}"
                            )
                        else:
                            self._log_reaction_debug(
                                f"🔍 ENFORCE SINGLE: Failed to remove reaction {emoji_str}: {e}"
                            )

            if reactions_to_remove:
                self._log_reaction_debug(
                    f"🔍 ENFORCE SINGLE: Cleaned up {
                        len(reactions_to_remove)} old reactions for user {
                        user.id}"
                )
            else:
                self._log_reaction_debug(
                    f"🔍 ENFORCE SINGLE: No cleanup needed for user {
                        user.id}"
                )

        except Exception as e:
            self._log_reaction_debug(
                f"🔍 ENFORCE SINGLE: Error during cleanup for user {
                    user.id}: {e}"
            )

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

        self._log_reaction_debug(
            f"🔍 PROCESS BET: Starting _process_bet for user {user_id}, amount={amount}, choice={choice}, emoji={emoji}"
        )

    # If caller provided an explicit session_id (e.g. reactions on a
    # session-specific live message), prefer that session when resolving
    # the contestant. This ensures reaction-based bets applied on
    # session messages succeed even if the global multi_session_mode flag
    # isn't enabled.

        # Ensure the user has an account and validate their balance
        ensure_user(data, user_id)
        user_balance = data["balances"][user_id]
        self._log_reaction_debug(f"🔍 PROCESS BET: User balance: {user_balance}")

        if amount <= 0:
            self._log_reaction_debug(
                f"🔍 PROCESS BET: Failed - invalid amount: {amount}"
            )
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
            self._log_reaction_debug(
                f"🔍 PROCESS BET: Failed - insufficient funds: amount={amount}, balance={user_balance}"
            )
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

        # Fallback to the normal discovery flow
        if not contestant_info:
            contestant_info = self._find_contestant_info(data, choice)
        if not contestant_info:
            self._log_reaction_debug(
                f"🔍 PROCESS BET: Failed - contestant not found: {choice}"
            )
            if notify_user and channel:
                from data_manager import is_multi_session_mode

                if is_multi_session_mode(data):
                    # Multi-session mode: show contestants from all active sessions
                    active_sessions = data.get("active_sessions", [])
                    all_contestants = []

                    for session_id in active_sessions:
                        session = data["betting_sessions"].get(session_id, {})
                        if session.get("status") == "open":
                            contestants = session.get("contestants", {})
                            for name in contestants.values():
                                all_contestants.append(
                                    f"• **{name}** (Session: {session_id})"
                                )

                    if all_contestants:
                        contestants_list = "\n".join(all_contestants)
                        example_contestant = (
                            list(
                                data["betting_sessions"][active_sessions[0]][
                                    "contestants"
                                ].values()
                            )[0]
                            if active_sessions
                            else "Contestant"
                        )
                        error_msg = MSG_UNKNOWN_CONTESTANT.format(
                            contestant_name=choice,
                            contestants_list=contestants_list,
                            example_contestant=example_contestant,
                        )
                    else:
                        error_msg = "No betting rounds are currently active."
                else:
                    # Legacy single-session mode
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

                await channel.send(
                    embed=discord.Embed(
                        title=TITLE_BETTING_ERROR,
                        description=error_msg,
                        color=COLOR_ERROR,
                    )
                )
            return False

        contestant_id, contestant_name = contestant_info

        from data_manager import is_multi_session_mode, find_session_by_contestant

        if is_multi_session_mode(data):
            # Multi-session mode: find the session for this contestant
            session_result = find_session_by_contestant(choice, data)
            if not session_result:
                self._log_reaction_debug(
                    f"🔍 PROCESS BET: Failed - no session found for contestant: {choice}"
                )
                return False

            session_id, _, _ = session_result
            session = data["betting_sessions"][session_id]

            # Check if session allows new bets
            if session.get("status") != "open":
                self._log_reaction_debug(
                    f"🔍 PROCESS BET: Failed - session {session_id} is not open (status: {session.get('status')})"
                )
                return False
            # Use centralized accessors for bets to keep storage canonical
            from data_manager import get_bets, set_bet, remove_bet

            session_bets = get_bets(data, session_id)
            existing_bet = session_bets.get(user_id)
            old_emoji = existing_bet.get("emoji") if existing_bet else None
            old_amount = existing_bet.get("amount", 0) if existing_bet else 0

            # If placing a manual bet (no emoji) after a reaction bet (has emoji),
            # remove the old reaction
            if old_emoji and not emoji:
                await self._remove_old_reaction_bet(data, user_id, old_emoji)

            # Calculate balance requirement
            required_additional = amount - old_amount
            user_balance = data["balances"][user_id]

            if required_additional > user_balance:
                self._log_reaction_debug(
                    f"🔍 PROCESS BET: Failed - insufficient funds for session bet: required={required_additional}, balance={user_balance}"
                )
                return False

            # Update user balance
            data["balances"][user_id] -= required_additional

            # Place bet using accessor
            from utils.bet_state import make_bet_info

            bet_payload = make_bet_info(amount, contestant_name, emoji)
            set_bet(data, session_id, user_id, bet_payload)
            # Persist changes immediately so live-message updater sees the new bet
            save_data(data)

            # Update contestant mapping
            data["contestant_to_session"][contestant_name.lower()] = session_id

            bet_result = True

        else:
            # Legacy single-session mode
            from data_manager import get_bets, set_bet

            existing_bet = get_bets(data).get(user_id)
            old_emoji = existing_bet.get("emoji") if existing_bet else None

            # If placing a manual bet (no emoji) after a reaction bet (has emoji),
            # remove the old reaction
            if old_emoji and not emoji:
                await self._remove_old_reaction_bet(data, user_id, old_emoji)

            # Use BetState to handle bet placement which will handle refunds and
            # balance updates. BetState operates on legacy data['betting'] so we
            # can continue to use it for legacy flow.
            bet_state = BetState(data)
            self._log_reaction_debug(
                f"🔍 PROCESS BET: Calling bet_state.place_bet({user_id}, {amount}, {contestant_name}, {emoji})"
            )
            bet_result = bet_state.place_bet(user_id, amount, contestant_name, emoji)
            self._log_reaction_debug(
                f"🔍 PROCESS BET: bet_state.place_bet returned: {bet_result}"
            )

        if not bet_result:
            self._log_reaction_debug(
                f"🔍 PROCESS BET: Failed - bet placement returned False"
            )
            logger.warning(
                f"Bet placement failed for user {user_id}: {amount} on {contestant_name}"
            )
            return False

        # Log successful bet placement
        self._log_reaction_debug(f"🔍 PROCESS BET: Bet placement successful")
        logger.info(
            f"Bet placed: User {user_id} bet {amount} coins on {contestant_name}"
        )
        performance_monitor.record_metric(
            "bet.placed", 1, {"contestant": contestant_name, "amount": str(amount)}
        )

        # Schedule live message update (batched for better performance)
        # If multi-session mode is active, schedule a session-targeted
        # update so the correct session live message is refreshed.
        from data_manager import is_multi_session_mode
        try:
            if is_multi_session_mode(data) and 'session_id' in locals() and session_id:
                # Instrumentation: log that we're scheduling a session-targeted update
                self._log_reaction_debug(
                    f"🔔 SCHEDULER: Scheduling session-targeted live message update for session {session_id}"
                )
                schedule_live_message_update_for_session(session_id)
            else:
                # Instrumentation: log that we're scheduling a global update
                self._log_reaction_debug(
                    "🔔 SCHEDULER: Scheduling global live message update"
                )
                schedule_live_message_update()
        except Exception:
            # Fall back to global scheduler on any unexpected error
            schedule_live_message_update()

        # Notify user if requested
        if notify_user and channel:
            await channel.send(
                embed=discord.Embed(
                    title=TITLE_BET_PLACED,
                    description=f"Your bet of `{amount}` coins on **{contestant_name}** has been placed!",
                    color=COLOR_SUCCESS,
                )
            )

        self._log_reaction_debug(
            f"🔍 PROCESS BET: Returning True - bet processing complete"
        )
        return True

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

    async def _add_betting_reactions(
        self, message: discord.Message, data: Data
    ) -> None:
        """Adds all configured betting reactions to a message with rate limiting protection."""
        # Prioritize most commonly used reactions first (100 and 250 coin bets)
        c1_emojis = data["contestant_1_emojis"]
        c2_emojis = data["contestant_2_emojis"]

        # Add reactions grouped by contestant for logical order
        priority_order = [
            c1_emojis[0],  # First contestant, 100 coins (🔥)
            c1_emojis[1],  # First contestant, 250 coins (⚡)
            c1_emojis[2],  # First contestant, 500 coins (💪)
            c1_emojis[3],  # First contestant, 1000 coins (🏆)
            SEPARATOR_EMOJI,  # Visual separator
            c2_emojis[0],  # Second contestant, 100 coins (🌟)
            c2_emojis[1],  # Second contestant, 250 coins (�)
            c2_emojis[2],  # Second contestant, 500 coins (🚀)
            c2_emojis[3],  # Second contestant, 1000 coins (👑)
        ]

        # Add reactions with proper spacing to avoid rate limits
        for i, emoji in enumerate(priority_order):
            await self._add_single_reaction_with_retry(message, emoji)
            # Small delay between reactions (Discord limit: ~1 per 0.25s)
            if i < len(priority_order) - 1:
                await asyncio.sleep(0.3)

    async def _add_single_reaction_with_retry(
        self, message: discord.Message, emoji: str, max_retries: int = 2
    ) -> None:
        """Add a single reaction with retry logic for rate limiting."""
        for attempt in range(max_retries + 1):
            try:
                await message.add_reaction(emoji)
                return  # Success, exit the retry loop
            except discord.HTTPException as e:
                if "rate limited" in str(e).lower() or "429" in str(e):
                    if attempt < max_retries:
                        # Exponential backoff: 0.5s, 1.5s, 3s
                        wait_time = 0.5 * (2**attempt)
                        print(
                            f"Rate limited adding reaction {emoji}, waiting {wait_time}s (attempt {
                                attempt + 1})"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        print(
                            f"Failed to add reaction {emoji} after {
                                max_retries + 1} attempts: {e}"
                        )
                        return
                else:
                    print(f"Could not add reaction {emoji} to live message: {e}")
                    return

    def _add_reactions_background(self, message: discord.Message, data: Data) -> None:
        """Start adding reactions in the background without blocking."""
        asyncio.create_task(self._add_betting_reactions(message, data))

    async def _remove_user_betting_reactions(
        self,
        message: discord.Message,
        user: discord.abc.User,
        data: Data,
        exclude_emoji: Optional[str] = None,
    ) -> None:
        """Removes all betting reactions from a specific user on a message,
        optionally excluding one emoji. Only attempts to remove reactions
        that the user actually has.
        Accepts discord.User or discord.Member (which inherits from User).
        """
        self._log_reaction_debug(
            f"🔍 REMOVE REACTIONS: Starting cleanup for user {
                user.id}, exclude_emoji={exclude_emoji}"
        )
        all_betting_emojis = data["contestant_1_emojis"] + data["contestant_2_emojis"]
        self._log_reaction_debug(
            f"🔍 REMOVE REACTIONS: All betting emojis: {all_betting_emojis}"
        )

        # Check which reactions the user actually has on this message
        # This prevents unnecessary API calls for reactions the user doesn't have
        user_reactions = set()
        for reaction in message.reactions:
            if reaction.emoji in all_betting_emojis:
                # Check if this user has reacted with this emoji
                try:
                    async for reactor in reaction.users():
                        if reactor.id == user.id:
                            user_reactions.add(reaction.emoji)
                            break
                except (discord.HTTPException, discord.Forbidden):
                    # If we can't check users, assume the reaction exists and try to remove it
                    user_reactions.add(reaction.emoji)

        self._log_reaction_debug(
            f"🔍 REMOVE REACTIONS: User {user.id} has reactions: {user_reactions}"
        )

        # Only attempt to remove reactions the user actually has
        for emoji_str in user_reactions:
            if emoji_str == exclude_emoji:
                self._log_reaction_debug(
                    f"🔍 REMOVE REACTIONS: Skipping removal of exclude_emoji: {emoji_str}"
                )
                continue  # Skip the emoji that was just added

            try:
                self._log_reaction_debug(
                    f"🔍 REMOVE REACTIONS: Removing reaction: {emoji_str}"
                )
                # Extra instrumentation: log that we're about to call the Discord API
                # to remove the reaction. This makes it easier to correlate an
                # API removal attempt with subsequent raw remove events in the
                # debug log.
                try:
                    self._log_reaction_debug(
                        f"🔍 REMOVE REACTIONS: About to call API remove_reaction for {emoji_str} (msg={message.id}, user={user.id})"
                    )
                except Exception:
                    # Defensive: don't let logging break removal
                    pass
                await message.remove_reaction(emoji_str, user)
                # Only mark as programmatic if the API call succeeded
                self._mark_programmatic_removal(message.id, user.id, emoji_str)
                self._log_reaction_debug(
                    f"🔍 REMOVE REACTIONS: Successfully removed reaction: {emoji_str}"
                )
            except discord.NotFound:
                self._log_reaction_debug(
                    f"🔍 REMOVE REACTIONS: Reaction {emoji_str} not found for user {
                        user.name}, skipping"
                )
                # Remove the mark since the removal didn't happen
                self._is_programmatic_removal(message.id, user.id, emoji_str)
            except discord.HTTPException as e:
                err_text = str(e)
                # If we lack permissions, we couldn't remove the reaction. Keep
                # the programmatic mark so that the subsequent on_raw_reaction_remove
                # event will be treated as programmatic (and ignored). For other
                # failures, don't leave a stale programmatic mark.
                if "Missing Permissions" in err_text or "403" in err_text:
                    # Mark as programmatic pre-emptively so the eventual raw
                    # removal event is ignored (we couldn't remove it ourselves).
                    self._mark_programmatic_removal(message.id, user.id, emoji_str)
                    self._log_reaction_debug(
                        f"🔍 REMOVE REACTIONS: Failed to remove reaction {emoji_str} from user {user.name}: {e} - missing permissions, keeping programmatic mark"
                    )
                else:
                    # Other errors: ensure we don't leave a stale mark
                    self._is_programmatic_removal(message.id, user.id, emoji_str)
                    self._log_reaction_debug(
                        f"🔍 REMOVE REACTIONS: Failed to remove reaction {emoji_str} from user {user.name}: {e} - clearing programmatic mark"
                    )

        self._log_reaction_debug(
            f"🔍 REMOVE REACTIONS: Cleanup complete for user {
                user.id}"
        )

    async def _remove_old_reaction_bet(
        self, data: Data, user_id: str, old_emoji: str
    ) -> None:
        """Remove a user's old reaction bet from live message(s) when they place a manual bet."""
        try:
            user = await self.bot.fetch_user(int(user_id))
        except (discord.NotFound, discord.HTTPException, ValueError) as e:
            print(f"ERROR: Could not fetch user {user_id} to remove old reaction: {e}")
            return

        # Get live message info and remove reaction from both main and
        # secondary messages
        main_msg_id, main_chan_id = get_live_message_info(data)
        secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

        # Remove from main message
        if main_msg_id and main_chan_id:
            await self._remove_reaction_from_message(
                main_chan_id, main_msg_id, user, old_emoji
            )

        # Remove from secondary message
        if secondary_msg_id and secondary_chan_id:
            await self._remove_reaction_from_message(
                secondary_chan_id, secondary_msg_id, user, old_emoji
            )

    async def _remove_reaction_from_message(
        self, channel_id: int, message_id: int, user: discord.abc.User, emoji: str
    ) -> None:
        """Helper method to remove a specific reaction from a specific message."""
        try:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                return

            message = await channel.fetch_message(message_id)
            # Instrumentation: log before calling the API to remove the reaction
            try:
                self._log_reaction_debug(
                    f"🔍 REMOVE REACTION FROM MSG: About to call API remove_reaction for {emoji} (msg={message_id}, user={user.id})"
                )
            except Exception:
                pass
            await message.remove_reaction(emoji, user)
            print(
                f"DEBUG: Removed reaction {emoji} from user {user.name} on message {message_id}"
            )
        except discord.NotFound:
            # Message or reaction not found, that's fine
            pass
        except discord.HTTPException as e:
            print(
                f"ERROR: Failed to remove reaction {emoji} from user {
                    user.name} on message {message_id}: {e}"
            )

    async def _create_payout_summary(
        self, winner_info: WinnerInfo, user_names: Dict[str, str]
    ) -> str:
        """Create a detailed summary of payouts for all users."""
        user_results = winner_info.get("user_results", {})
        if not user_results:
            return "No bets were placed in this round."

        # Separate winners and losers
        winners = []
        losers = []

        for user_id, result in user_results.items():
            user_name = user_names.get(user_id, f"Unknown User ({user_id})")
            net_change = result["net_change"]
            winnings = result["winnings"]
            bet_amount = result["bet_amount"]

            if net_change > 0:
                # Winner: show their winnings
                winners.append(
                    f"🏆 **{user_name}**: Bet `{bet_amount}` → Won `{winnings}` (Net: +`{net_change}`)"
                )
            elif net_change == 0:
                # Broke even (rare case)
                winners.append(f"⚖️ **{user_name}**: Bet `{bet_amount}` → Broke even")
            else:
                # Loser: show their loss
                losers.append(f"💸 **{user_name}**: Lost `{bet_amount}` coins")

        # Build the summary
        summary_parts = []

        if winners:
            if len(winners) == 1:
                summary_parts.append("### 🎉 Winner")
            else:
                summary_parts.append("### 🎉 Winners")
            summary_parts.extend(winners)

        if losers:
            if winners:
                summary_parts.append("")  # Add spacing
            if len(losers) == 1:
                summary_parts.append("### 💔 Unlucky Bettor")
            else:
                summary_parts.append("### 💔 Unlucky Bettors")
            summary_parts.extend(losers)

        return "\n".join(summary_parts)

    # Re-implemented _process_winner_declaration logic
    async def _process_winner_declaration(
        self, ctx: commands.Context, data: Data, winner_name: str
    ) -> None:
        """Handles the logic for declaring a winner, distributing coins, and resetting the bet state.

        This function is now session-aware: if a session is found for the winner
        (via contestant name lookup in multi-session mode), the SessionBetState
        wrapper is used to calculate results and declare the winner for that
        session. Otherwise, the legacy BetState behavior is preserved.
        """

        # Attempt to resolve a session for the given winner (multi-session mode)
        from data_manager import find_session_by_contestant

        session_tuple = find_session_by_contestant(winner_name, data)
        if session_tuple:
            # Multi-session path: operate on the resolved session dict
            session_id = session_tuple[0]
            session = data.get("betting_sessions", {}).get(session_id, {})

            # Ensure contestants exist in session
            contestants = session.get("contestants", {})
            if not contestants:
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ERROR,
                    f"Contestant '{winner_name}' not found in session.",
                    COLOR_ERROR,
                )
                return

            # Check if there are any bets in this session
            session_bets = session.get("bets", {})
            if not session_bets:
                await self._send_embed(
                    ctx,
                    "Round Complete",
                    f"No bets were placed in this session. Declared winner: {winner_name} (no payouts).",
                    COLOR_SUCCESS,
                )
                # Reset session state even with no bets
                from typing import cast
                from utils.bet_state import BettingSession as _BettingSession

                sbs = SessionBetState(data, cast(_BettingSession, session))
                sbs.declare_winner(winner_name)
                return

            # Calculate statistics BEFORE processing winner (which clears bet data)
            total_bettors = len(session_bets)
            total_pot = sum(bet["amount"] for bet in session_bets.values())
            bets_on_winner = sum(
                1
                for bet in session_bets.values()
                if bet["choice"].lower() == winner_name.lower()
            )

            # Process winner through SessionBetState
            from typing import cast
            from utils.bet_state import BettingSession as _BettingSession

            sbs = SessionBetState(data, cast(_BettingSession, session))
            winner_info = sbs.declare_winner(winner_name)

        else:
            # Legacy single-session path (unchanged behavior)
            contestants = data["betting"].get("contestants", {})

            # Find the winner's ID (e.g., "1" or "2") based on name
            winner_id: Optional[str] = None
            for c_id, c_name in contestants.items():
                if c_name.lower() == winner_name.lower():
                    winner_id = c_id
                    break

            if winner_id is None:
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ERROR,
                    f"Contestant '{winner_name}' not found.",
                    COLOR_ERROR,
                )
                return

            # Check if there are any bets before proceeding
            if not get_bets(data):
                await self._send_embed(
                    ctx,
                    "Round Complete",
                    f"No bets were placed in this round. Declared winner: {winner_name} (no payouts).",
                    COLOR_SUCCESS,
                )
                # Reset betting state even with no bets
                self.bet_state.update_data(data)
                self.bet_state.declare_winner(winner_name)
                return

            # Calculate statistics BEFORE processing winner (which clears bet data)
            total_bettors = len(get_bets(data))
            total_pot = sum(bet["amount"] for bet in get_bets(data).values())
            bets_on_winner = sum(
                1
                for bet in get_bets(data).values()
                if bet["choice"].lower() == winner_name.lower()
            )

            # Process winner through BetState
            self.bet_state.update_data(data)
            winner_info = self.bet_state.declare_winner(winner_name)

        # Log winner declaration
        logger.info(
            f"Winner declared: {winner_name} - Total pot: {total_pot} coins, {total_bettors} bettors"
        )
        performance_monitor.record_metric(
            "betting.winner_declared",
            1,
            {
                "winner": winner_name,
                "total_pot": str(total_pot),
                "total_bettors": str(total_bettors),
            },
        )

        # Get user names for detailed payout message
        user_names = {}
        for user_id in winner_info["user_results"].keys():
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_names[user_id] = user.display_name
            except (discord.NotFound, ValueError):
                user_names[user_id] = f"Unknown User ({user_id})"
            except Exception:
                user_names[user_id] = f"User ({user_id})"

        # Create detailed payout summary
        payout_details = await self._create_payout_summary(winner_info, user_names)

        # Send comprehensive results message
        if bets_on_winner == 0:
            # No one bet on the winner
            embed_title = "💸 Round Complete - House Wins!"
            embed_description = (
                f"**{winner_name}** wins the contest!\n\n"
                f"� **Round Summary:**\n"
                f"• Total Pot: `{total_pot}` coins\n"
                f"• Total Players: `{total_bettors}`\n"
                f"• Bets on Winner: `0`\n"
                f"• Result: All coins lost to the house\n\n"
                f"{payout_details}"
            )
            embed_color = COLOR_WARNING
        else:
            # Someone bet on the winner
            embed_title = f"🏆 Round Complete - {winner_name} Wins!"
            if bets_on_winner == 1:
                embed_description = (
                    f"**{winner_name}** wins the contest!\n\n"
                    f"📊 **Round Summary:**\n"
                    f"• Total Pot: `{total_pot}` coins\n"
                    f"• Total Players: `{total_bettors}`\n"
                    f"• Winner Takes All: `{total_pot}` coins\n\n"
                    f"{payout_details}"
                )
            else:
                embed_description = (
                    f"**{winner_name}** wins the contest!\n\n"
                    f"📊 **Round Summary:**\n"
                    f"• Total Pot: `{total_pot}` coins\n"
                    f"• Total Players: `{total_bettors}`\n"
                    f"• Winners: `{bets_on_winner}` players\n"
                    f"• Pot Shared Among Winners\n\n"
                    f"{payout_details}"
                )
            embed_color = COLOR_SUCCESS

        await self._send_embed(ctx, embed_title, embed_description, embed_color)

        # Try to locate the session for this winner (multi-session) and update
        # the session-specific live message if present. Fall back to legacy
        # behavior if no session found.
        from data_manager import find_session_by_contestant
        from utils.live_message import suppress_next_batched_update, schedule_live_message_update_for_session

        session_tuple = find_session_by_contestant(winner_name, data)
        session_id_for_update = session_tuple[0] if session_tuple else None

        # Update immediate live message for the session or legacy messages
        await update_live_message(
            self.bot,
            data,
            winner_declared=True,
            winner_info=winner_info,
            session_id=session_id_for_update,
        )

        # Also schedule batched update for consistency and any pending changes
        # Ensure the batched update doesn't immediately overwrite this
        # special immediate update.
        suppress_next_batched_update()
        # Schedule a session-specific batched update if we have a session id
        if session_id_for_update:
            schedule_live_message_update_for_session(session_id_for_update)
        else:
            # Fall back to global scheduler
            schedule_live_message_update()

    # END _process_winner_declaration

    # --- Timer Management ---

    def _cancel_bet_timer(self):
        """Cancels the active betting timer task if it exists and clears its data."""
        self.timer.cancel_timer()

        data = load_data()
        if data.get("timer_end_time") is not None:
            self._clear_timer_state_in_data(data)

    async def _handle_timer_expired(self, ctx: commands.Context):
        """Handle when the betting timer expires."""
        await self._lock_bets_internal(ctx, timer_expired=True)

    async def _lock_bets_internal(
        self,
        ctx: commands.Context,
        timer_expired: bool = False,
        silent_lock: bool = False,
        session_id: Optional[str] = None,
    ) -> None:
        """Internal logic to lock bets, callable by command or timer."""
        data = load_data()

        if not data["betting"]["open"]:
            msg = (
                "⚠️ Betting is **already locked**."
                if data["betting"]["locked"]
                else MSG_NO_ACTIVE_BET + " to lock."
            )
            await self._send_embed(ctx, TITLE_CANNOT_LOCK_BETS, msg, COLOR_ERROR)
            return

        data["betting"]["open"] = False
        data["betting"]["locked"] = True
        self._clear_timer_state_in_data(
            data
        )  # Clear timer_end_time when bets are locked
        save_data(data)

        lock_summary = MSG_BETTING_LOCKED_SUMMARY
        if timer_expired:
            lock_summary = MSG_BETTING_TIMER_EXPIRED_SUMMARY

        # Re-added functionality: Clear reactions from the relevant live
        # message(s) when bets are locked. If a session_id is provided, only
        # clear that session's messages; otherwise fall back to legacy global
        # messages.
        from utils.live_message import (
            get_live_message_info,
            get_secondary_live_message_info,
            get_session_live_message_info,
        )

        messages_to_clear_reactions = []
        if session_id:
            sess_msg_id, sess_chan_id = get_session_live_message_info(data, session_id)
            if sess_msg_id and sess_chan_id:
                messages_to_clear_reactions.append((sess_msg_id, sess_chan_id))
        else:
            main_msg_id, main_chan_id = get_live_message_info(data)
            secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)
            if main_msg_id and main_chan_id:
                messages_to_clear_reactions.append((main_msg_id, main_chan_id))
            if secondary_msg_id and secondary_chan_id:
                messages_to_clear_reactions.append((secondary_msg_id, secondary_chan_id))

        for msg_id, chan_id in messages_to_clear_reactions:
            channel = self.bot.get_channel(chan_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(msg_id)
                    await message.clear_reactions()
                    print(
                        f"Cleared all reactions from live message {msg_id} in channel {chan_id}."
                    )
                except discord.NotFound:
                    print(
                        f"Live message {msg_id} not found when trying to clear reactions."
                    )
                except discord.HTTPException as e:
                    print(f"Error clearing reactions from live message {msg_id}: {e}")
        # End re-added functionality

        # Determine session id (if this legacy betting round corresponds to a
        # created multi-session) and update session-specific live message when
        # possible.
        from data_manager import find_session_by_contestant
        from utils.live_message import suppress_next_batched_update, schedule_live_message_update_for_session

        # Pick first contestant name from legacy betting structure to find session
        contestants = data["betting"].get("contestants", {})
        contestant_name = None
        if contestants:
            # find any display name
            for v in contestants.values():
                contestant_name = v
                break

        session_tuple = find_session_by_contestant(contestant_name, data) if contestant_name else None
        session_id_for_update = session_tuple[0] if session_tuple is not None else None

        # Update live message immediately to show locked state
        await update_live_message(
            self.bot, data, betting_closed=True, close_summary=lock_summary, session_id=session_id_for_update
        )

        # Also schedule a batched update to handle any last-moment bets that
        # might be pending. Ensure the batched update doesn't immediately
        # overwrite this special immediate update.
        suppress_next_batched_update()
        if session_id_for_update:
            schedule_live_message_update_for_session(session_id_for_update)
        else:
            schedule_live_message_update()

        if not silent_lock:  # Only send the locked message if not a silent lock
            await self._send_embed(
                ctx, TITLE_BETS_LOCKED, lock_summary, COLOR_DARK_ORANGE
            )

    # --- Discord Commands ---

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

        # Import here to avoid circular import at module load time
        from data_manager import is_multi_session_mode

        # Ensure multi-session mode is enabled and create a new session derived
        # from the two contestant names. This makes `!openbet` the primary
        # way to open sessions without requiring an explicit session ID.
        if not is_multi_session_mode(data):
            data["betting_sessions"] = {}
            data["active_sessions"] = []
            data["contestant_to_session"] = {}
            data["multi_session_mode"] = True

        # Check for contestant name conflicts across existing (non-closed)
        # sessions. Closed sessions may be kept for audit but should not block
        # reusing contestant names.
        for existing_session in data.get("betting_sessions", {}).values():
            if existing_session.get("status") == "closed":
                continue
            for contestant_name in existing_session.get("contestants", {}).values():
                if contestant_name.lower() in (name1.lower(), name2.lower()):
                    await self._send_embed(
                        ctx,
                        TITLE_BETTING_ERROR,
                        f"**Contestant '{contestant_name}' already exists in another session.**\nContestant names must be unique across all active sessions.",
                        COLOR_ERROR,
                    )
                    return

        # Generate a numeric session ID (1, 2, 3, ...) for implicit sessions.
        # Store and bump `next_session_id` in the persistent data so IDs are
        # stable and incrementing across restarts.
        # Use a simple numeric counter persisted in the data store to produce
        # human-friendly numeric session ids. Cast to dict to avoid TypedDict
        # restrictions when adding the field.
        from typing import MutableMapping, cast

        mutable_data = cast(MutableMapping, data)
        if "next_session_id" not in mutable_data:
            mutable_data["next_session_id"] = 1

        # Find the next available numeric id that isn't already used.
        candidate = str(mutable_data["next_session_id"])
        while candidate in data.get("betting_sessions", {}):
            mutable_data["next_session_id"] = int(mutable_data["next_session_id"]) + 1
            candidate = str(mutable_data["next_session_id"])

        session_id = candidate
        # Prepare next id for the future
        mutable_data["next_session_id"] = int(session_id) + 1

        new_session: MultiBettingSession = {
            "id": session_id,
            "title": f"{name1} vs {name2}",
            "status": "open",
            "contestants": {"c1": name1, "c2": name2},
            "bets": {},
            "timer_config": {
                "enabled": data["settings"].get("enable_bet_timer", True),
                "duration": BET_TIMER_DURATION,
                "lock_duration": None,
                "close_duration": None,
                "update_interval": 60,
                "auto_lock_at": None,
                "auto_close_at": (time.time() + BET_TIMER_DURATION)
                if data["settings"].get("enable_bet_timer", True)
                else None,
            },
            "created_at": time.time(),
            "creator_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "lock_time": None,
            "close_time": None,
            "live_message_id": None,
            "last_update": time.time(),
            "total_pot": 0,
            "total_bettors": 0,
            "winner": None,
            "closed_at": None,
            "closed_by": None,
        }

        # Register session in data and update contestant mapping
        data["betting_sessions"][session_id] = new_session
        data["active_sessions"].append(session_id)
        data["contestant_to_session"][name1.lower()] = session_id
        data["contestant_to_session"][name2.lower()] = session_id

        # For backward compatibility with legacy live-message updater, also
        # populate the legacy single-session `betting` structure so existing
        # live-message code continues to function until per-session live
        # message wiring is implemented.
        data["betting"] = {
            "open": True,
            "locked": False,
            "bets": {},
            "contestants": {"1": name1, "2": name2},
        }
        if data["settings"]["enable_bet_timer"]:
            data["timer_end_time"] = time.time() + BET_TIMER_DURATION
        else:
            data["timer_end_time"] = None

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

        main_chan_id = get_saved_bet_channel_id(data)
        target_channel: Optional[discord.TextChannel] = None

        if main_chan_id:
            channel_obj = self.bot.get_channel(main_chan_id)
            if isinstance(channel_obj, discord.TextChannel):
                target_channel = channel_obj

        # If no valid saved text channel, try to use the context channel if
        # it's a text channel
        if target_channel is None and isinstance(ctx.channel, discord.TextChannel):
            target_channel = ctx.channel

        # If still no target_channel (e.g., ctx.channel is a DMChannel and no
        # saved channel)
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
            # target_channel is now guaranteed to be a discord.TextChannel
            main_live_msg = await target_channel.send(
                embed=discord.Embed(
                    title=TITLE_LIVE_BETTING_ROUND,
                    description=initial_embed_description,
                    color=COLOR_GOLD,
                )
            )
                # If multi-session mode is active and we created a session_id above,
                # store the live message info on the session. Otherwise fall back to
                # legacy global live message behavior.
            from data_manager import is_multi_session_mode
            from utils.live_message import set_session_live_message_info

            if is_multi_session_mode(data) and "session_id" in locals():
                set_session_live_message_info(data, session_id, main_live_msg.id, target_channel.id)
            else:
                set_live_message_info(data, main_live_msg.id, target_channel.id)

            # update_live_message will now calculate remaining_time if not
            # passed
            await update_live_message(self.bot, data, session_id=session_id)
            # Call update_live_message here to populate the embed
        except Exception as e:
            print(f"Error sending main live message: {e}")
            set_live_message_info(data, None, None)
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_FAILED_SEND_LIVE_MESSAGE, COLOR_ERROR
            )
            return

        if main_live_msg:
            # Add reactions in the background to avoid blocking the betting
            # round opening
            self._add_reactions_background(main_live_msg, data)

        # Only send a secondary message if no saved bet channel exists and
        # the invoking channel is different from the target channel. If a
        # saved bet channel was configured via `!setbetchannel`, prefer that
        # channel exclusively for live messages and do not post a secondary
        # duplicate in the invoking channel.
        if (
            main_chan_id is None
            and isinstance(ctx.channel, discord.TextChannel)
            and ctx.channel.id != target_channel.id
        ):
            try:
                secondary_live_msg = await ctx.channel.send(
                    embed=discord.Embed(
                        title=TITLE_LIVE_BETTING_ROUND,
                        description=initial_embed_description,
                        color=COLOR_GOLD,
                    )
                )
                set_secondary_live_message_info(
                    data, secondary_live_msg.id, ctx.channel.id
                )
            except Exception as e:
                print(f"Error sending secondary live message: {e}")
                set_secondary_live_message_info(data, None, None)

        # Always send a short confirmation containing the Session ID so admins
        # have an easy reference. If the invoking channel differs from the
        # target/live channel, include the usual detailed note as well.
        session_note = f"\n\nSession ID: `{session_id}`"
        # Detailed message when invoking channel is different
        if (
            isinstance(ctx.channel, discord.TextChannel)
            and ctx.channel.id != target_channel.id
        ):
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
        else:
            # Minimal confirmation in invoking channel when same as target
            await self._send_embed(
                ctx,
                TITLE_BETTING_ROUND_OPENED,
                f"Betting round opened for **{name1}** vs **{name2}**.{session_note}",
                COLOR_SUCCESS,
            )

        # Schedule the betting timer if enabled (moved here, after live message
        # is set up)
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
        from data_manager import is_multi_session_mode, find_session_by_contestant

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

        await self._lock_bets_internal(ctx, session_id=session_id)

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
        await self._process_winner_declaration(ctx, data, winner)

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
        from data_manager import is_multi_session_mode

        if is_multi_session_mode(data) and target in data.get("betting_sessions", {}):
            # Optional winner can be provided as second arg
            winner_arg = args[1] if len(args) > 1 else None
            await self._close_session(ctx, target, winner_arg)
            return

        # Otherwise fallback to legacy behavior: treat first arg as winner name
        winner = target

        # Attempt to resolve a session id for multi-session mode before locking
        session_id: Optional[str] = None
        from data_manager import find_session_by_contestant

        if is_multi_session_mode(data):
            # Try to resolve by winner name first (unique contestant names)
            tuple_found = find_session_by_contestant(winner, data)
            if tuple_found:
                session_id = tuple_found[0]

        if data["betting"]["open"]:
            await self._lock_bets_internal(ctx, silent_lock=True, session_id=session_id)
        data = load_data()

        self._cancel_bet_timer()
        # Declare winner using the existing flow
        await self._process_winner_declaration(ctx, data, winner)

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
        await self._close_session(ctx, session_id, winner)

    async def _close_session(self, ctx: commands.Context, session_id: str, winner_name: Optional[str] = None) -> None:
        """Close a session by id and optionally declare a winner. Extracted helper
        used by close_bet and close_session wrapper.
        """
        d = load_data()
        session = d.get("betting_sessions", {}).get(session_id)
        if not session:
            await self._send_embed(ctx, TITLE_BETTING_ERROR, f"Session '{session_id}' not found.", COLOR_ERROR)
            return

        contestants = session.get("contestants", {})
        bets = session.get("bets", {})

        # If winner specified, validate and process payouts
        if winner_name:
            winner_found = False
            for contestant_name in contestants.values():
                if contestant_name.lower() == winner_name.lower():
                    winner = contestant_name
                    winner_found = True
                    break
            if not winner_found:
                contestants_list = ", ".join(contestants.values())
                await self._send_embed(ctx, TITLE_BETTING_ERROR, f"**Winner '{winner_name}' not found in session '{session_id}'.**\n\nValid contestants: {contestants_list}", COLOR_ERROR)
                return

            # Calculate payouts if bets exist
            if bets:
                total_pot = sum(bet["amount"] for bet in bets.values())
                winning_bets = [bet for bet in bets.values() if bet["choice"] == winner_name.lower()]
                winning_pot = sum(bet["amount"] for bet in winning_bets)
                if winning_bets and winning_pot > 0:
                    for user_id, bet in session.get("bets", {}).items():
                        if bet["choice"] == winner_name.lower():
                            winnings = int((bet["amount"] / winning_pot) * total_pot)
                            d["balances"][user_id] = d.get("balances", {}).get(user_id, 0) + winnings

        # Remove session from active list and update mappings
        if session_id in d.get("active_sessions", []):
            d.get("active_sessions", []).remove(session_id)

        for contestant_name in contestants.values():
            d.get("contestant_to_session", {}).pop(contestant_name.lower(), None)

        session["status"] = "closed"
        if winner_name:
            session["winner"] = winner_name
        session["closed_at"] = time.time()
        session["closed_by"] = str(ctx.author.id)

        save_data(d)

        # Send results
        if winner_name and bets:
            total_pot = sum(bet["amount"] for bet in bets.values())
            winners_count = len([b for b in bets.values() if b["choice"] == winner_name.lower()])
            results_text = [
                f"🏆 **{winner_name}** wins!",
                f"📊 **Round Summary:**",
                f"• Total Pot: `{total_pot}` coins",
                f"• Total Bettors: `{len(bets)}`",
                f"• Winners: `{winners_count}`",
            ]
            await self._send_embed(ctx, f"🏆 Session '{session_id}' Complete", "\n".join(results_text), COLOR_SUCCESS)
        elif winner_name:
            await self._send_embed(ctx, f"🏆 Session '{session_id}' Complete", f"**{winner_name}** wins!\n\nNo bets were placed in this session.", COLOR_SUCCESS)
        else:
            await self._send_embed(ctx, f"🔒 Session '{session_id}' Closed", f"Session '{session_id}' closed without declaring a winner.", COLOR_INFO)

        # Update live message
        from utils.live_message import suppress_next_batched_update, schedule_live_message_update_for_session
        await update_live_message(self.bot, d, betting_closed=True, close_summary="Session closed", winner_declared=bool(winner_name), winner_info=None, session_id=session_id)
        suppress_next_batched_update()
        schedule_live_message_update_for_session(session_id)

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
            # Incorrect number of arguments (this block is now only reached if
            # len(args) is not 0 or 2)
            await self._send_embed(
                ctx, TITLE_INVALID_BET_FORMAT, MSG_INVALID_BET_FORMAT, COLOR_ERROR
            )
            return

        # Ensure the user has an account
        ensure_user(data, str(ctx.author.id))  # Fix: Convert to string

        # Check if the amount is positive
        if amount <= 0:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_AMOUNT_POSITIVE, COLOR_ERROR
            )
            return

        contestant_info = self._find_contestant_info(data, choice)
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

        success = await self._process_bet(
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

    @place_bet.error
    async def place_bet_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        data = load_data()
        is_missing_or_bad_arg = isinstance(
            error, commands.MissingRequiredArgument
        ) or isinstance(error, commands.BadArgument)

        if not data["betting"]["open"] and is_missing_or_bad_arg:
            await self._send_embed(
                ctx,
                TITLE_NO_OPEN_BETTING_ROUND,
                MSG_NO_ACTIVE_BET_AND_MISSING_ARGS,
                COLOR_ERROR,
            )
            return
        elif not data["betting"]["open"]:
            await self._send_embed(
                ctx, TITLE_NO_OPEN_BETTING_ROUND, MSG_NO_ACTIVE_BET, COLOR_ERROR
            )
            return

        if is_missing_or_bad_arg:
            await self._send_embed(
                ctx, TITLE_INVALID_BET_FORMAT, MSG_INVALID_BET_FORMAT, COLOR_ERROR
            )
        else:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                f"An unexpected error occurred: {error}",
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
        success = await self._process_bet(
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
                contestant_info = self._find_contestant_info(data, bet["choice"])
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
            contestant_info = self._find_contestant_info(data, bet["choice"])
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

        contestant_info = self._find_contestant_info(data, choice)
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

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        # Ignore bot's own reactions (defensive helper)
        if self._is_own_reaction_user(payload.user_id):
            return

        # Quick check: if betting is not open, don't process any reaction additions
        # However, if the reaction is on the live betting messages, remove it
        # so users don't get stuck with reaction indicators. This is a best-effort
        # removal and will silently ignore any errors.
        data = load_data()

        # Determine if this reaction targets a session-specific live message
        session_id_for_msg = None
        for sid, sess in data.get("betting_sessions", {}).items():
            if sess.get("live_message_id") == payload.message_id and sess.get("channel_id") == payload.channel_id:
                session_id_for_msg = sid
                break

        # If legacy single-session isn't open, allow processing only for
        # live messages: either the legacy main/secondary messages or a
        # session-specific live message that belongs to an active session.
        if not data["betting"]["open"]:
            main_msg_id, main_chan_id = get_live_message_info(data)
            secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

            is_legacy_live_msg = (
                payload.message_id == main_msg_id and payload.channel_id == main_chan_id
            ) or (
                payload.message_id == secondary_msg_id and payload.channel_id == secondary_chan_id
            )

            # If this is neither a legacy live message nor a session message,
            # ignore the reaction.
            if not is_legacy_live_msg and session_id_for_msg is None:
                return

            # If this is a session message but the session is closed, remove
            # the reaction (best-effort) and return.
            if session_id_for_msg is not None:
                session = data.get("betting_sessions", {}).get(session_id_for_msg, {})
                if session.get("status") != "open":
                    try:
                        import inspect

                        channel = self.bot.get_channel(payload.channel_id)
                        if channel is None:
                            return
                        fetch_message = getattr(channel, "fetch_message", None)
                        if not callable(fetch_message):
                            return
                        fetch_result = fetch_message(payload.message_id)
                        if inspect.isawaitable(fetch_result):
                            message = await fetch_result
                        else:
                            message = fetch_result
                        user = await self.bot.fetch_user(payload.user_id)
                        remove_reaction = getattr(message, "remove_reaction", None)
                        if callable(remove_reaction):
                            remove_result = remove_reaction(payload.emoji, user)
                            if inspect.isawaitable(remove_result):
                                await remove_result
                    except Exception:
                        pass
                    return

            # If it's a legacy live message and betting is closed, try to
            # remove the reaction to avoid stuck reactions on the message.
            if is_legacy_live_msg:
                try:
                    import inspect

                    channel = self.bot.get_channel(payload.channel_id)
                    if channel is None:
                        return
                    fetch_message = getattr(channel, "fetch_message", None)
                    if not callable(fetch_message):
                        return
                    fetch_result = fetch_message(payload.message_id)
                    if inspect.isawaitable(fetch_result):
                        message = await fetch_result
                    else:
                        message = fetch_result
                    user = await self.bot.fetch_user(payload.user_id)
                    remove_reaction = getattr(message, "remove_reaction", None)
                    if callable(remove_reaction):
                        remove_result = remove_reaction(payload.emoji, user)
                        if inspect.isawaitable(remove_result):
                            await remove_result
                except Exception:
                    pass
                return

        self._log_reaction_debug(
            f"🔍 REACTION ADD: user_id={
                payload.user_id}, emoji={
                payload.emoji}, msg_id={
                payload.message_id}"
        )

        # Determine if this reaction is tied to a session-specific live message
        session_id_for_msg = None
        # Dump session mapping debug info to help detect type mismatches
        try:
            session_dump = {
                sid: (sess.get("live_message_id"), sess.get("channel_id"))
                for sid, sess in data.get("betting_sessions", {}).items()
            }
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Session live_message mapping: {session_dump}"
            )
        except Exception:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Failed to dump session mapping for debug"
            )

        for sid, sess in data.get("betting_sessions", {}).items():
            # Be defensive about type: payload.message_id may be int or str depending on source
            sess_msg_id = sess.get("live_message_id")
            sess_chan_id = sess.get("channel_id")
            try:
                if sess_msg_id == payload.message_id and sess_chan_id == payload.channel_id:
                    session_id_for_msg = sid
                    break
            except Exception:
                # Try string comparison as a fallback
                if str(sess_msg_id) == str(payload.message_id) and str(sess_chan_id) == str(payload.channel_id):
                    session_id_for_msg = sid
                    break

        # Fallback: race condition mitigation. If we didn't find a session mapping yet
        # (session_id_for_msg is None) but we're in multi-session mode, try to fetch
        # the message and parse the embed footer for a "Session ID" marker. This
        # handles the case where reactions arrive before `set_session_live_message_info`
        # persisted the mapping during `openbet`.
        if session_id_for_msg is None:
            try:
                from data_manager import is_multi_session_mode
                from utils.live_message import set_session_live_message_info

                if is_multi_session_mode(data):
                    channel = self.bot.get_channel(payload.channel_id)
                    # Only TextChannel guarantees fetch_message exists
                    if channel and isinstance(channel, discord.TextChannel):
                        try:
                            message = await channel.fetch_message(payload.message_id)
                            embeds = getattr(message, "embeds", []) or []
                            if embeds:
                                footer = getattr(embeds[0], "footer", None)
                                footer_text = getattr(footer, "text", "") if footer else ""
                                # Try to find a session id in the footer like 'Session ID: 10' or 'Session ID: `10`'
                                m = re.search(r"Session ID:?\s*`?(\d+)`?", footer_text)
                                if m:
                                    candidate_sid = m.group(1)
                                    # Persist the mapping so subsequent reactions will match
                                    set_session_live_message_info(data, candidate_sid, payload.message_id, payload.channel_id)
                                    session_id_for_msg = candidate_sid
                                    self._log_reaction_debug(
                                        f"🔍 REACTION ADD: Parsed Session ID from embed footer: {candidate_sid} and persisted mapping"
                                    )
                        except Exception:
                            # If fetching or parsing fails, just ignore this fallback
                            pass
            except Exception:
                # Defensive: don't allow any fallback errors to break reaction handling
                pass

        main_msg_id, main_chan_id = get_live_message_info(data)
        secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

        self._log_reaction_debug(
            f"🔍 REACTION ADD: session_msg={session_id_for_msg}, main_msg={main_msg_id}, main_chan={main_chan_id}"
        )

        # Check if the reaction is on one of the live betting messages
        is_main_message = (
            payload.message_id == main_msg_id and payload.channel_id == main_chan_id
        )
        is_secondary_message = (
            payload.message_id == secondary_msg_id
            and payload.channel_id == secondary_chan_id
        )
        is_session_message = session_id_for_msg is not None

        self._log_reaction_debug(
            f"🔍 REACTION ADD: is_main_message={is_main_message}, is_secondary_message={is_secondary_message}"
        )
        # Include session-specific live messages in the acceptance criteria
        self._log_reaction_debug(
            f"🔍 REACTION ADD: is_session_message={is_session_message}"
        )

        if not (is_main_message or is_secondary_message or is_session_message):
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Not a betting message reaction, ignoring"
            )
            return  # Not a reaction on a live betting message

        self._log_reaction_debug(
            f"🔍 REACTION ADD: Valid betting message reaction detected"
        )

        # Get message and user objects
        self._log_reaction_debug(
            f"🔍 REACTION ADD: Getting channel and message objects"
        )
        channel = self.bot.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Channel is not a TextChannel: {
                    type(channel)}"
            )
            return

        try:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Fetching message and user from Discord API"
            )
            message = await channel.fetch_message(payload.message_id)
            user = await self.bot.fetch_user(payload.user_id)
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Successfully fetched message and user"
            )
        except discord.NotFound:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Message or user not found for reaction payload: {payload}"
            )
            return
        except discord.HTTPException as e:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: HTTPException fetching message or user: {e}"
            )
            return
        except Exception as e:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Unexpected error fetching message or user: {e}"
            )
            return

        # Determine contestant from emoji
        contestant_id = _get_contestant_from_emoji(data, str(payload.emoji))
        self._log_reaction_debug(
            f"🔍 REACTION ADD: emoji={
                payload.emoji} -> contestant_id={contestant_id}"
        )

        if not contestant_id:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Not a betting emoji, removing reaction"
            )
            # Not a betting emoji, remove reaction
            await message.remove_reaction(payload.emoji, user)
            return

        # Resolve contestant name from session if this is a session message.
        # Sessions store contestants as keys like 'c1'/'c2' while legacy
        # single-session storage uses '1'/'2'. Try both forms to be robust
        # against either structure (fixes contestant_name=None cases).
        if is_session_message:
            session = data.get("betting_sessions", {}).get(session_id_for_msg, {})
            contestants = session.get("contestants", {})
            contestant_name = contestants.get(contestant_id) or contestants.get(f"c{contestant_id}")
        else:
            contestants = data["betting"].get("contestants", {})
            contestant_name = contestants.get(contestant_id) or contestants.get(f"c{contestant_id}")
        self._log_reaction_debug(
            f"🔍 REACTION ADD: contestant_id={contestant_id} -> contestant_name={contestant_name}"
        )

        if not contestant_name:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Contestant name not found for ID {contestant_id}"
            )
            await message.remove_reaction(payload.emoji, user)
            return

        # Get bet amount from reaction emoji
        bet_amount = data["reaction_bet_amounts"].get(str(payload.emoji))
        self._log_reaction_debug(
            f"🔍 REACTION ADD: emoji={
                payload.emoji} -> bet_amount={bet_amount}"
        )

        if bet_amount is None:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: No bet amount configured for emoji {
                    payload.emoji}"
            )
            await message.remove_reaction(payload.emoji, user)
            return

        # Ensure user has an account and sufficient balance
        ensure_user(data, str(user.id))
        user_balance = data["balances"][str(user.id)]
        self._log_reaction_debug(
            f"🔍 REACTION ADD: user_balance={user_balance}, bet_amount={bet_amount}"
        )

        if bet_amount > user_balance:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: Insufficient balance, removing reaction and sending error"
            )
            # Insufficient balance, remove reaction and inform user in the
            # channel
            await message.remove_reaction(payload.emoji, user)
            shortfall = bet_amount - user_balance
            embed = discord.Embed(
                title="❌ Insufficient Funds",
                description=f"<@{user.id}> 💰 **Your balance:** `{user_balance}` coins\n💸 **Reaction bet:** `{bet_amount}` coins\n❌ **You need:** `{shortfall}` more coins",
                color=COLOR_ERROR,
            )
            await channel.send(embed=embed)
            return

        # Check if user is currently in cleanup phase - if so, defer this
        # reaction
        if user.id in self._users_in_cleanup:
            self._log_reaction_debug(
                f"🔍 REACTION ADD: User {
                    user.id} is in cleanup phase, storing deferred reaction"
            )

            # Get sequence and timestamp for deferred reaction
            self._reaction_sequence += 1
            deferred_sequence = self._reaction_sequence
            import time

            deferred_timestamp = time.time()

            # Store this reaction to process after cleanup completes
            # Only keep the latest reaction per user (check sequence)
            should_defer = True
            if user.id in self._deferred_reactions:
                existing_deferred_sequence = self._deferred_reactions[user.id].get(
                    "sequence", 0
                )
                if deferred_sequence <= existing_deferred_sequence:
                    should_defer = False
                    self._log_reaction_debug(
                        f"🔍 REACTION ADD: Ignoring out-of-order deferred reaction (sequence {deferred_sequence} <= {existing_deferred_sequence})"
                    )

            if should_defer:
                self._deferred_reactions[user.id] = {
                    "payload": payload,
                    "message": message,
                    "user": user,
                    "contestant_name": contestant_name,
                    "bet_amount": bet_amount,
                    "channel": channel,
                    "data": data,
                    "session_id": session_id_for_msg,
                    "sequence": deferred_sequence,
                    "timestamp": deferred_timestamp,
                }
                self._log_reaction_debug(
                    f"🔍 REACTION ADD: Stored deferred reaction for user {
                        user.id}: {contestant_name} for {bet_amount} coins (sequence: {deferred_sequence})"
                )

            return

        self._log_reaction_debug(
            f"🔍 REACTION ADD: Starting batching system for user {
                user.id}"
        )

        # GLOBAL ENFORCEMENT: Remove any existing betting reactions from this user
        # This ensures each user only has 1 active reaction at a time
        # But skip if user is already in cleanup phase to avoid conflicts
        if user.id not in self._users_in_cleanup:
            self._log_reaction_debug(f"🔍 REACTION ADD: Enforcing single reaction per user")
            await self._enforce_single_reaction_per_user(message, user, data, str(payload.emoji))
        else:
            self._log_reaction_debug(f"🔍 REACTION ADD: Skipping enforcement - user {user.id} already in cleanup phase")

        # Use batching system to handle multiple rapid reactions
        # Cancel any existing timer for this user
        self._log_reaction_debug(
            f"🔍 REACTION ADD: Cancelling existing timer for user {
                user.id}"
        )
        self._cancel_user_reaction_timer(user.id)

        # Store the pending bet information with sequence-based ordering
        # Only store if this reaction is newer than any existing pending bet
        emoji_str = str(payload.emoji)

        # Increment sequence counter and get timestamp
        self._reaction_sequence += 1
        current_sequence = self._reaction_sequence
        import time

        current_timestamp = time.time()

        # Check if we should store this reaction (only if newer than existing)
        should_store = True
        if user.id in self._pending_reaction_bets:
            existing_sequence = self._pending_reaction_bets[user.id].get("sequence", 0)
            existing_timestamp = self._pending_reaction_bets[user.id].get(
                "timestamp", 0
            )

            # Only store if this reaction has a higher sequence number (more
            # recent)
            if current_sequence <= existing_sequence:
                should_store = False
                self._log_reaction_debug(
                    f"🔍 REACTION ADD: Ignoring out-of-order reaction: {contestant_name} for {bet_amount} coins (sequence {current_sequence} <= {existing_sequence})"
                )

        if should_store:
            self._pending_reaction_bets[user.id] = {
                "message": message,
                "user": user,
                "data": data,
                "contestant_name": contestant_name,
                "bet_amount": bet_amount,
                "emoji": emoji_str,
                "channel": channel,
                "session_id": session_id_for_msg,
                "sequence": current_sequence,
                "timestamp": current_timestamp,
            }

            # If a session message, persist a fast mapping for contestant -> session
            # so later resolution (e.g., in _process_bet) can find the session.
            if session_id_for_msg and contestant_name:
                data.setdefault("contestant_to_session", {})[contestant_name.lower()] = session_id_for_msg
                save_data(data)

            self._log_reaction_debug(
                f"🔍 REACTION ADD: Stored pending bet: {contestant_name} for {bet_amount} coins, emoji {emoji_str} (sequence: {current_sequence}, timestamp: {current_timestamp:.3f})"
            )
        else:
            # Don't restart timers if we're ignoring this reaction
            return

        # Start a new timer to process this bet after a short delay
        # This allows multiple rapid reactions to be batched together
        timer_task = asyncio.create_task(self._delayed_reaction_processing(user.id))
        self._reaction_timers[user.id] = timer_task
        self._log_reaction_debug(
            f"🔍 REACTION ADD: Started primary timer for user {
                user.id}"
        )

        # Add a safety mechanism: also schedule a backup processing in case the primary fails
        # This is a failsafe to ensure bets get processed even if there are
        # timer issues
        asyncio.create_task(self._backup_reaction_processing(user.id, 3.0))
        self._log_reaction_debug(
            f"🔍 REACTION ADD: Started backup timer for user {
                user.id}"
        )

        self._log_reaction_debug(
            f"🔍 REACTION ADD: Current pending bets: {
                list(
                    self._pending_reaction_bets.keys())}"
        )
        self._log_reaction_debug(
            f"🔍 REACTION ADD: Current active timers: {
                list(
                    self._reaction_timers.keys())}"
        )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        # Ignore bot's own reactions (defensive helper)
        if self._is_own_reaction_user(payload.user_id):
            return

        # Quick check: if betting is not open, don't process any reaction removals
        data = load_data()
        if not data["betting"]["open"]:
            return  # Cannot unbet if betting is not open

        # Check if this is a programmatic removal (to prevent race conditions)
        programmatic = self._is_programmatic_removal(
            payload.message_id, payload.user_id, str(payload.emoji)
        )
        self._log_reaction_debug(
            f"🔍 REACTION REMOVE: programmatic_check={programmatic}, msg={payload.message_id}, user={payload.user_id}, emoji={payload.emoji}"
        )
        # Additional instrumentation: record whether there's a pending batched
        # reaction for this user and whether a matching bet currently exists.
        try:
            import time as _time

            now_ts = _time.time()
            pending = self._pending_reaction_bets.get(payload.user_id)
            pending_exists = bool(pending)
            pending_msg = None
            pending_ts = None
            if pending:
                pm = pending.get("message")
                if pm:
                    pending_msg = getattr(pm, "id", None)
                pending_ts = pending.get("timestamp")

            # Quick check for an existing bet on this message (session or legacy)
            session_match = None
            for sid, sess in data.get("betting_sessions", {}).items():
                if sess.get("live_message_id") == payload.message_id and sess.get("channel_id") == payload.channel_id:
                    session_match = sid
                    break

            existing_bet = False
            if session_match:
                sess_bets = data.get("betting_sessions", {}).get(session_match, {}).get("bets", {})
                existing_bet = str(payload.user_id) in sess_bets
            else:
                legacy_bets = data.get("betting", {}).get("bets", {})
                existing_bet = str(payload.user_id) in legacy_bets

            self._log_reaction_debug(
                f"🔍 REACTION REMOVE: debug now={now_ts:.3f}, pending_exists={pending_exists}, pending_msg={pending_msg}, pending_ts={pending_ts}, existing_bet={existing_bet}, session_match={session_match}"
            )
        except Exception as _:
            # Don't let debug logging affect normal behavior
            pass
        if programmatic:
            return  # This was a programmatic removal, don't process it as user action

        main_msg_id, main_chan_id = get_live_message_info(data)
        secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

        # Check if the reaction is on one of the live betting messages or a session message
        is_main_message = (
            payload.message_id == main_msg_id and payload.channel_id == main_chan_id
        )
        is_secondary_message = (
            payload.message_id == secondary_msg_id
            and payload.channel_id == secondary_chan_id
        )

        # Detect session-specific live message
        session_id_for_msg = None
        for sid, sess in data.get("betting_sessions", {}).items():
            if sess.get("live_message_id") == payload.message_id and sess.get("channel_id") == payload.channel_id:
                session_id_for_msg = sid
                break

        if not (is_main_message or is_secondary_message or session_id_for_msg):
            return  # Not a reaction on a live betting message

        # Get user object
        try:
            user = await self.bot.fetch_user(payload.user_id)
        except discord.NotFound:
            print(f"User not found for reaction remove payload: {payload}")
            return
        except discord.HTTPException as e:
            print(f"Error fetching user for reaction remove: {e}")
            return

        # Determine contestant from emoji
        contestant_id = _get_contestant_from_emoji(data, str(payload.emoji))
        if not contestant_id:
            return  # Not a betting emoji

        user_id_str = str(user.id)

        # If this is a session-specific message, operate on that session's bets
        if session_id_for_msg:
            session = data.get("betting_sessions", {}).get(session_id_for_msg, {})
            session_bets = session.get("bets", {})
            # session contestants may use 'c1'/'c2' keys; try both
            contestants = session.get("contestants", {})
            contestant_name = contestants.get(contestant_id) or contestants.get(f"c{contestant_id}")
            if user_id_str in session_bets:
                bet_info = session_bets[user_id_str]
                if contestant_name and bet_info.get("choice") == contestant_name.lower():
                    refund_amount = bet_info.get("amount", 0)
                    # Instrumentation: log whether we'll refund due to reaction removal
                    try:
                        self._log_reaction_debug(
                            f"🔍 REACTION REMOVE: will_refund=True (session={session_id_for_msg}, user={user_id_str}, amount={refund_amount})"
                        )
                    except Exception:
                        pass
                    data["balances"][user_id_str] = data["balances"].get(user_id_str, 0) + refund_amount
                    # Use remove_bet accessor to keep storage access centralized
                    from data_manager import remove_bet

                    remove_bet(data, session_id_for_msg, user_id_str)
                    # Persist removal so live-message updater sees the refund immediately
                    save_data(data)
                    schedule_live_message_update_for_session(session_id_for_msg)
                    return

        # Fallback to legacy bets
        # Legacy single-session contestants may be keyed '1'/'2' while
        # session-scoped contestants use 'c1'/'c2'. Try both when falling
        # back to legacy storage.
        legacy_contestants = data.get("betting", {}).get("contestants", {})
        contestant_name = legacy_contestants.get(contestant_id) or legacy_contestants.get(f"c{contestant_id}")
        from data_manager import get_bets, remove_bet

        legacy_bets = get_bets(data)
        if user_id_str in legacy_bets:
            bet_info = legacy_bets[user_id_str]
            if contestant_name and bet_info.get("choice") == contestant_name.lower():
                # When removing a bet, just process the refund and cleanup
                refund_amount = bet_info.get("amount", 0)
                # Instrumentation: log whether we'll refund due to reaction removal
                try:
                    self._log_reaction_debug(
                        f"🔍 REACTION REMOVE: will_refund=True (legacy, user={user_id_str}, amount={refund_amount})"
                    )
                except Exception:
                    pass
                data["balances"][user_id_str] = data["balances"].get(user_id_str, 0) + refund_amount
                remove_bet(data, None, user_id_str)
                save_data(data)
                schedule_live_message_update()  # Schedule batched update

    # =============================================================================
    # PHASE 3: SESSION MANAGEMENT COMMANDS
    # =============================================================================

    

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

    


async def setup(bot: commands.Bot):
    """Set up the Betting cog."""
    await bot.add_cog(Betting(bot))
