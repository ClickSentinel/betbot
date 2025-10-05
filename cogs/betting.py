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

        # Track last enforcement time per user to prevent spam
        self._last_enforcement: Dict[int, float] = {}  # user_id -> timestamp

        # Toggle for extensive reaction debug logging. Default comes from config.
        # If runtime toggling is disabled via config, the command will not allow
        # changing this value.
        self.enable_reaction_debug_logging = bool(REACTION_DEBUG_LOGGING_ENABLED)

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
            success = await self._process_bet(
                channel=channel if isinstance(channel, discord.TextChannel) else None,
                data=data,
                user_id=user_id_str,
                amount=bet_amount,
                choice=contestant_name,
                emoji=final_emoji,
                notify_user=False,  # Don't send notification messages for reaction bets
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

        # Rate limit enforcement to prevent spam (max once per 2 seconds per
        # user)
        import time

        current_time = time.time()
        last_enforcement = self._last_enforcement.get(user.id, 0)

        if current_time - last_enforcement < 2.0:
            self._log_reaction_debug(
                f"🔍 ENFORCE SINGLE: Rate limited for user {
                    user.id} (last: {
                    current_time -
                    last_enforcement:.1f}s ago)"
            )
            return

        self._last_enforcement[user.id] = current_time
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
                    await reaction.remove(user)
                    self._log_reaction_debug(
                        f"🔍 ENFORCE SINGLE: Removed user reaction {emoji_str}"
                    )
                except discord.NotFound:
                    self._log_reaction_debug(
                        f"🔍 ENFORCE SINGLE: Reaction {emoji_str} already removed"
                    )
                except discord.HTTPException as e:
                    if "Unknown Message" in str(e) or "Unknown Emoji" in str(e):
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
    ) -> bool:
        """Centralized bet processing logic.
        Returns True if bet was successful, False otherwise."""

        self._log_reaction_debug(
            f"🔍 PROCESS BET: Starting _process_bet for user {user_id}, amount={amount}, choice={choice}, emoji={emoji}"
        )

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
        optionally excluding one emoji.
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

        for emoji_str in all_betting_emojis:
            if emoji_str == exclude_emoji:
                self._log_reaction_debug(
                    f"🔍 REMOVE REACTIONS: Skipping removal of exclude_emoji: {emoji_str}"
                )
                continue  # Skip the emoji that was just added

            try:
                # Mark this removal as programmatic to prevent race condition
                self._mark_programmatic_removal(message.id, user.id, emoji_str)
                self._log_reaction_debug(
                    f"🔍 REMOVE REACTIONS: Removing reaction: {emoji_str}"
                )
                await message.remove_reaction(emoji_str, user)
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
                # Remove the mark since the removal failed
                self._is_programmatic_removal(message.id, user.id, emoji_str)
                self._log_reaction_debug(
                    f"🔍 REMOVE REACTIONS: Failed to remove reaction {emoji_str} from user {
                        user.name}: {e}"
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
            await message.remove_reaction(emoji, user)
            print(
                f"DEBUG: Removed reaction {emoji} from user {
                    user.name} on message {message_id}"
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
        session_id_for_update = session_tuple[0] if session_tuple else None

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

        # Check for contestant name conflicts across existing sessions
        for existing_session in data.get("betting_sessions", {}).values():
            for contestant_name in existing_session.get("contestants", {}).values():
                if contestant_name.lower() in (name1.lower(), name2.lower()):
                    await self._send_embed(
                        ctx,
                        TITLE_BETTING_ERROR,
                        f"**Contestant '{contestant_name}' already exists in another session.**\nContestant names must be unique across all sessions.",
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

        # Conditional sending of the final confirmation message
        # target_channel is guaranteed to be a TextChannel here
        if (
            isinstance(ctx.channel, discord.TextChannel)
            and ctx.channel.id != target_channel.id
        ):  # Only send the detailed message if not the main betting channel
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
        # If opened in the set bet channel, no additional message needed - live
        # message provides all info

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
    async def close_bet(self, ctx: commands.Context, winner: str) -> None:
        data = load_data()

        if not await self._check_permission(ctx, "close betting rounds"):
            return
        if not data["betting"]["open"] and not data["betting"]["locked"]:
            await self._send_embed(
                ctx, TITLE_CANNOT_CLOSE_BETS, MSG_NO_BETS_TO_CLOSE, COLOR_ERROR
            )
            return

        # Attempt to resolve a session id for multi-session mode before locking
        session_id: Optional[str] = None
        from data_manager import is_multi_session_mode, find_session_by_contestant

        if is_multi_session_mode(data):
            # Try to resolve by winner name first (unique contestant names)
            tuple_found = find_session_by_contestant(winner, data)
            if tuple_found:
                session_id = tuple_found[0]

        if data["betting"]["open"]:
            await self._lock_bets_internal(
                ctx, silent_lock=True, session_id=session_id
            )  # This will set data["betting"]["locked"] = True, silently
        data = load_data()  # Reload data after locking

        self._cancel_bet_timer()
        # Updated call
        await self._process_winner_declaration(ctx, data, winner)

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
        data = load_data()
        if not data["betting"]["open"]:
            if data["betting"]["locked"]:
                # Betting round exists but is locked
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
                # No betting round at all
                await self._send_embed(
                    ctx, TITLE_BETTING_ERROR, MSG_NO_ACTIVE_BET, COLOR_ERROR
                )
            return

        # Ensure the user has an account
        ensure_user(data, str(ctx.author.id))  # Fix: Convert to string

        user_bet = get_bets(data).get(str(ctx.author.id))
        if not user_bet:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "You have not placed any bets in the current round.",
                COLOR_ERROR,
            )
            return

        contestant_info = self._find_contestant_info(data, user_bet["choice"])
        contestant_name = contestant_info[1] if contestant_info else "Unknown"

        # Get user's current balance for context
        user_balance = data.get("balances", {}).get(str(ctx.author.id), 0)

        # Calculate betting percentage
        bet_percentage = (
            (user_bet["amount"] / (user_balance + user_bet["amount"])) * 100
            if (user_balance + user_bet["amount"]) > 0
            else 0
        )

        # Enhanced mybet display
        bet_info = [
            f"🎯 **Current Bet:** `{user_bet['amount']}` coins on **{contestant_name}**",
            f"💰 **Remaining Balance:** `{user_balance}` coins",
            f"📊 **Bet Size:** {bet_percentage:.0f}% of your total funds",
        ]

        # Add betting status context
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
            "🎰 Your Current Bet",
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

        # Schedule live message update (batched for better performance)
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
        # Ignore bot's own reactions first (cheapest check)
        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        # Quick check: if betting is not open, don't process any reaction additions
        # However, if the reaction is on the live betting messages, remove it
        # so users don't get stuck with reaction indicators. This is a best-effort
        # removal and will silently ignore any errors.
        data = load_data()
        if not data["betting"]["open"]:
            main_msg_id, main_chan_id = get_live_message_info(data)
            secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

            is_live_msg = (
                payload.message_id == main_msg_id and payload.channel_id == main_chan_id
            ) or (
                payload.message_id == secondary_msg_id
                and payload.channel_id == secondary_chan_id
            )

            if not is_live_msg:
                return  # Not a live betting message, nothing to do

            # Best-effort: try to fetch channel/message/user and remove reaction
            try:
                import inspect

                channel = self.bot.get_channel(payload.channel_id)
                if channel is None:
                    # Nothing we can do
                    return

                # Use getattr to avoid static attribute-access assumptions
                fetch_message = getattr(channel, "fetch_message", None)
                if not callable(fetch_message):
                    # Channel type doesn't support fetching messages
                    return

                # Some tests/mocks return async mocks for channels - call the method dynamically
                fetch_result = fetch_message(payload.message_id)
                if inspect.isawaitable(fetch_result):
                    message = await fetch_result
                else:
                    message = fetch_result

                user = await self.bot.fetch_user(payload.user_id)

                # Remove reaction if the message exposes that method
                remove_reaction = getattr(message, "remove_reaction", None)
                if callable(remove_reaction):
                    remove_result = remove_reaction(payload.emoji, user)
                    if inspect.isawaitable(remove_result):
                        await remove_result
            except Exception:
                # Ignore any errors (e.g., channel/message not found, permissions)
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
        for sid, sess in data.get("betting_sessions", {}).items():
            if sess.get("live_message_id") == payload.message_id and sess.get("channel_id") == payload.channel_id:
                session_id_for_msg = sid
                break

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

        if not (is_main_message or is_secondary_message):
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

        # Resolve contestant name from session if this is a session message
        if is_session_message:
            session = data.get("betting_sessions", {}).get(session_id_for_msg, {})
            contestant_name = session.get("contestants", {}).get(contestant_id)
        else:
            contestant_name = data["betting"].get("contestants", {}).get(contestant_id)
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
        # TEMPORARILY DISABLED - Rate limiting interferes with rapid testing
        self._log_reaction_debug(
            f"🔍 REACTION ADD: Global enforcement temporarily disabled for testing"
        )
        # if user.id not in self._users_in_cleanup:
        #     self._log_reaction_debug(f"🔍 REACTION ADD: Enforcing single reaction per user")
        #     await self._enforce_single_reaction_per_user(message, user, data, str(payload.emoji))
        # else:
        #     self._log_reaction_debug(f"🔍 REACTION ADD: Skipping enforcement - user {user.id} already in cleanup phase")

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
        # Ignore bot's own reactions
        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        # Quick check: if betting is not open, don't process any reaction removals
        data = load_data()
        if not data["betting"]["open"]:
            return  # Cannot unbet if betting is not open

        # Check if this is a programmatic removal (to prevent race conditions)
        if self._is_programmatic_removal(
            payload.message_id, payload.user_id, str(payload.emoji)
        ):
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
            contestant_name = session.get("contestants", {}).get(contestant_id)
            if user_id_str in session_bets:
                bet_info = session_bets[user_id_str]
                if contestant_name and bet_info.get("choice") == contestant_name.lower():
                    refund_amount = bet_info.get("amount", 0)
                    data["balances"][user_id_str] = data["balances"].get(user_id_str, 0) + refund_amount
                    # Use remove_bet accessor to keep storage access centralized
                    from data_manager import remove_bet

                    remove_bet(data, session_id_for_msg, user_id_str)
                    schedule_live_message_update_for_session(session_id_for_msg)
                    return

        # Fallback to legacy bets
        contestant_name = data.get("betting", {}).get("contestants", {}).get(contestant_id)
        from data_manager import get_bets, remove_bet

        legacy_bets = get_bets(data)
        if user_id_str in legacy_bets:
            bet_info = legacy_bets[user_id_str]
            if contestant_name and bet_info.get("choice") == contestant_name.lower():
                # When removing a bet, just process the refund and cleanup
                refund_amount = bet_info.get("amount", 0)
                data["balances"][user_id_str] = data["balances"].get(user_id_str, 0) + refund_amount
                remove_bet(data, None, user_id_str)
                save_data(data)
                schedule_live_message_update()  # Schedule batched update

    # =============================================================================
    # PHASE 3: SESSION MANAGEMENT COMMANDS
    # =============================================================================

    @commands.command(name="opensession", aliases=["os"])
    async def open_session(
        self,
        ctx: commands.Context,
        session_id: str,
        contestant1: str,
        contestant2: str,
        timer_duration: Optional[int] = 300,
    ) -> None:
        """Create and open a new betting session.

        Usage: !opensession <session_id> <contestant1> <contestant2> [timer_duration]
        Example: !opensession nfl_patriots_cowboys "New England Patriots" "Dallas Cowboys" 600
        """
        if not await self._check_permission(ctx, "manage betting sessions"):
            return

        from data_manager import is_multi_session_mode

        data = load_data()

        # Initialize multi-session mode if not already enabled
        if not is_multi_session_mode(data):
            # Convert to multi-session mode
            data["betting_sessions"] = {}
            data["active_sessions"] = []
            data["contestant_to_session"] = {}
            data["multi_session_mode"] = True

        # Validate session ID
        if not session_id or len(session_id) > 50:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Invalid session ID.**\nSession ID must be 1-50 characters long.\nExample: `nfl_game`, `lakers_vs_warriors`",
                COLOR_ERROR,
            )
            return

        # Check if session already exists
        if session_id in data.get("betting_sessions", {}):
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                f"**Session '{session_id}' already exists.**\nUse `!sessioninfo {session_id}` to view details or choose a different session ID.",
                COLOR_ERROR,
            )
            return

        # If the provided session_id is numeric, ensure next_session_id is
        # advanced to avoid collisions with future implicit numeric ids.
        from typing import MutableMapping, cast
        mutable_data = cast(MutableMapping, data)
        try:
            numeric = int(session_id)
            if "next_session_id" not in mutable_data:
                mutable_data["next_session_id"] = numeric + 1
            else:
                if int(mutable_data.get("next_session_id", 1)) <= numeric:
                    mutable_data["next_session_id"] = numeric + 1
        except ValueError:
            # not numeric — nothing to do
            pass

        # Validate contestant names
        contestant1 = contestant1.strip()
        contestant2 = contestant2.strip()

        if not contestant1 or not contestant2:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Contestant names cannot be empty.**\nExample: `!opensession nfl_game Patriots Cowboys`",
                COLOR_ERROR,
            )
            return

        if contestant1.lower() == contestant2.lower():
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Contestant names must be different.**\nExample: `!opensession nfl_game Patriots Cowboys`",
                COLOR_ERROR,
            )
            return

        if len(contestant1) > 50 or len(contestant2) > 50:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Contestant names are too long.**\nPlease keep names under 50 characters each.",
                COLOR_ERROR,
            )
            return

        # Check for contestant name conflicts across sessions
        existing_contestants = set()
        for existing_session in data.get("betting_sessions", {}).values():
            for contestant_name in existing_session.get("contestants", {}).values():
                existing_contestants.add(contestant_name.lower())

        if contestant1.lower() in existing_contestants:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                f"**Contestant '{contestant1}' already exists in another session.**\nContestant names must be unique across all sessions.",
                COLOR_ERROR,
            )
            return

        if contestant2.lower() in existing_contestants:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                f"**Contestant '{contestant2}' already exists in another session.**\nContestant names must be unique across all sessions.",
                COLOR_ERROR,
            )
            return

        # Validate timer duration
        if timer_duration is not None and (
            timer_duration < 30 or timer_duration > 3600
        ):
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Invalid timer duration.**\nTimer must be between 30 and 3600 seconds (1 hour).",
                COLOR_ERROR,
            )
            return

        # Create the new session
        new_session: MultiBettingSession = {
            "id": session_id,
            "title": f"{contestant1} vs {contestant2}",
            "status": "open",
            "contestants": {"c1": contestant1, "c2": contestant2},
            "bets": {},
            "timer_config": {
                "enabled": True,
                "duration": timer_duration or 300,
                "lock_duration": None,
                "close_duration": None,
                "update_interval": 60,
                "auto_lock_at": None,
                "auto_close_at": time.time() + (timer_duration or 300),
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

        # Add session to data
        data["betting_sessions"][session_id] = new_session
        data["active_sessions"].append(session_id)

        # Update contestant mapping
        data["contestant_to_session"][contestant1.lower()] = session_id
        data["contestant_to_session"][contestant2.lower()] = session_id

        save_data(data)

        # Log session creation
        logger.info(
            f"New betting session created: {session_id} ({contestant1} vs {contestant2}) by {ctx.author}"
        )

        await self._send_embed(
            ctx,
            f"🎯 Session '{session_id}' Created",
            f"**Contestants:** {contestant1} vs {contestant2}\n"
            f"**Timer:** {timer_duration or 300} seconds\n"
            f"**Status:** Open for betting\n\n"
            f"💡 **Users can now bet:** `!bet {contestant1} 100`\n"
            f"📊 **View sessions:** `!listsessions`",
            COLOR_SUCCESS,
        )

    @commands.command(name="listsessions", aliases=["ls"])
    async def list_sessions(self, ctx: commands.Context) -> None:
        """List all active betting sessions."""
        from data_manager import is_multi_session_mode

        data = load_data()

        if not is_multi_session_mode(data):
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
                    f"💡 Use `!opensession` to enable multi-session betting",
                    COLOR_INFO,
                )
            else:
                await self._send_embed(
                    ctx,
                    "📋 No Active Sessions",
                    "No betting sessions are currently active.\n\n"
                    f"🎯 **Start a session:** `!opensession session_name Contestant1 Contestant2`\n"
                    f"📊 **Legacy betting:** `!openbet Contestant1 Contestant2`",
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
                f"🎯 **Start a session:** `!opensession session_name Contestant1 Contestant2`",
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

    @commands.command(name="closesession", aliases=["cs"])
    async def close_session(
        self, ctx: commands.Context, session_id: str, winner: Optional[str] = None
    ) -> None:
        """Close a specific session and optionally declare a winner.

        Usage: !closesession <session_id> [winner_name]
        Example: !closesession nfl_game Patriots
        """
        if not await self._check_permission(ctx, "close betting sessions"):
            return

        from data_manager import is_multi_session_mode

        data = load_data()

        if not is_multi_session_mode(data):
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "Multi-session mode is not active.\nUse `!closebet` for legacy session management.",
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

        contestants = session.get("contestants", {})
        bets = session.get("bets", {})

        # If winner is specified, validate it
        if winner:
            winner_found = False
            for contestant_name in contestants.values():
                if contestant_name.lower() == winner.lower():
                    winner = contestant_name  # Use exact case from session
                    winner_found = True
                    break

            if not winner_found:
                contestants_list = ", ".join(contestants.values())
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ERROR,
                    f"**Winner '{winner}' not found in session '{session_id}'.**\n\nValid contestants: {contestants_list}",
                    COLOR_ERROR,
                )
                return

        # Initialize results text
        results_text = []

        # Calculate payouts if there's a winner and bets exist
        if winner and bets:
            total_pot = sum(bet["amount"] for bet in bets.values())
            winning_bets = [
                bet for bet in bets.values() if bet["choice"] == winner.lower()
            ]
            winning_pot = sum(bet["amount"] for bet in winning_bets)

            # Process payouts
            if winning_bets:
                # Distribute winnings proportionally
                for user_id, bet in bets.items():
                    if bet["choice"] == winner.lower():
                        # Winner gets their share of the total pot
                        winnings = int((bet["amount"] / winning_pot) * total_pot)
                        data["balances"][user_id] += winnings

            # Create results summary
            total_bettors = len(bets)
            winners_count = len(winning_bets)

            results_text = [
                f"🏆 **{winner}** wins!",
                f"📊 **Round Summary:**",
                f"• Total Pot: `{total_pot}` coins",
                f"• Total Bettors: `{total_bettors}`",
                f"• Winners: `{winners_count}` {'player' if winners_count == 1 else 'players'}",
            ]

            if winners_count == 0:
                results_text.append("• Result: All coins lost to the house")
            elif winners_count == 1:
                results_text.append(f"• Winner takes all: `{total_pot}` coins")
            else:
                results_text.append("• Pot shared among winners")

        # Remove session from active list and update mappings
        if session_id in data.get("active_sessions", []):
            data["active_sessions"].remove(session_id)

        # Remove contestants from mapping
        for contestant_name in contestants.values():
            data.get("contestant_to_session", {}).pop(contestant_name.lower(), None)

        # Mark session as closed
        session["status"] = "closed"
        if winner:
            session["winner"] = winner
        session["closed_at"] = time.time()
        session["closed_by"] = str(ctx.author.id)

        save_data(data)

        # Send results
        if winner and bets:
            await self._send_embed(
                ctx,
                f"🏆 Session '{session_id}' Complete",
                "\n".join(results_text),
                COLOR_SUCCESS,
            )
        elif winner:
            await self._send_embed(
                ctx,
                f"🏆 Session '{session_id}' Complete",
                f"**{winner}** wins!\n\nNo bets were placed in this session.",
                COLOR_SUCCESS,
            )
        else:
            await self._send_embed(
                ctx,
                f"🔒 Session '{session_id}' Closed",
                f"Session closed without declaring a winner.\n\n"
                f"If you want to declare a winner later, you'll need to handle payouts manually.",
                COLOR_INFO,
            )

        # Log session closure
        logger.info(
            f"Session closed: {session_id} (winner: {winner or 'None'}) by {ctx.author}"
        )
        # Update the session-specific live message so the final embed shows
        # the closed/winner summary and isn't overwritten by a batched update.
        from utils.live_message import (
            suppress_next_batched_update,
            schedule_live_message_update_for_session,
        )

        await update_live_message(
            self.bot, data, betting_closed=True, close_summary="Session closed", winner_declared=bool(winner), winner_info=None, session_id=session_id
        )

        suppress_next_batched_update()
        schedule_live_message_update_for_session(session_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Betting(bot))
