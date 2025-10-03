import discord
import discord.utils
from discord.ext import commands
from typing import Optional, Tuple, Dict, Any
import asyncio
import time

# Add enhanced logging
from utils.logger import logger
from utils.performance_monitor import performance_monitor, performance_timer
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
    BET_TIMER_UPDATE_INTERVAL,
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
    ROLE_BETBOY,
    TITLE_LIVE_BETTING_ROUND,
    TITLE_POT_LOST,
    MSG_NO_ACTIVE_BET_AND_MISSING_ARGS,
    TITLE_NO_OPEN_BETTING_ROUND,
    MSG_PLACE_MANUAL_BET_INSTRUCTIONS,
    MSG_INVALID_OPENBET_FORMAT,
    MSG_BET_CHANGED,
    MSG_BET_LOCKED_WITH_LIVE_LINK,
    TITLE_INSUFFICIENT_FUNDS,
)
from data_manager import load_data, save_data, ensure_user, Data
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
    initialize_live_message_scheduler,
)
from utils.bet_state import BetState
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
        
        # Track pending reaction bets for batching multiple rapid reactions
        self._pending_reaction_bets: Dict[int, Dict[str, Any]] = {}  # user_id -> pending bet info
        self._reaction_timers: Dict[int, asyncio.Task] = {}  # user_id -> timer task

    # --- Helper Methods for Deduplication ---
    
    def _create_removal_key(self, message_id: int, user_id: int, emoji: str) -> str:
        """Create a unique key for tracking programmatic reaction removals."""
        return f"{message_id}:{user_id}:{emoji}"
    
    def _mark_programmatic_removal(self, message_id: int, user_id: int, emoji: str) -> None:
        """Mark a reaction removal as programmatic to avoid processing it as user-initiated."""
        key = self._create_removal_key(message_id, user_id, emoji)
        current_time = time.time()
        self._programmatic_removals.add(key)
        self._programmatic_removals_timestamps[key] = current_time
        
        # Clean up old entries (older than 30 seconds)
        cutoff_time = current_time - 30
        old_keys = [k for k, t in self._programmatic_removals_timestamps.items() if t < cutoff_time]
        for old_key in old_keys:
            self._programmatic_removals.discard(old_key)
            self._programmatic_removals_timestamps.pop(old_key, None)
    
    def _is_programmatic_removal(self, message_id: int, user_id: int, emoji: str) -> bool:
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
            task = self._reaction_timers[user_id]
            if not task.done():
                task.cancel()
            del self._reaction_timers[user_id]
    
    async def _process_batched_reaction(self, user_id: int) -> None:
        """Process the final batched reaction after the delay period."""
        try:
            # Remove the timer from tracking
            self._reaction_timers.pop(user_id, None)
            
            # Get the pending bet info
            if user_id not in self._pending_reaction_bets:
                return  # No pending bet, nothing to do
            
            bet_info = self._pending_reaction_bets.pop(user_id)
            
            # Extract the bet information
            message = bet_info["message"]
            user = bet_info["user"]
            data = bet_info["data"]
            contestant_name = bet_info["contestant_name"]
            bet_amount = bet_info["bet_amount"]
            final_emoji = bet_info["emoji"]
            channel = bet_info["channel"]
            
            # Process the final bet
            user_id_str = str(user.id)
            success = await self._process_bet(
                channel=channel if isinstance(channel, discord.TextChannel) else None,
                data=data,
                user_id=user_id_str,
                amount=bet_amount,
                choice=contestant_name,
                emoji=final_emoji,
                notify_user=False,  # Don't send notification messages for reaction bets
            )
            
            if success:
                # Remove ALL betting reactions from the user, then add back the final one
                await self._remove_user_betting_reactions(
                    message, user, data, exclude_emoji=None  # Remove ALL reactions first
                )
                
                # Add back the final emoji
                try:
                    await message.add_reaction(final_emoji)
                except discord.HTTPException as e:
                    print(f"Error adding final reaction {final_emoji}: {e}")
            else:
                # If bet failed, remove all reactions including the final one
                await self._remove_user_betting_reactions(
                    message, user, data, exclude_emoji=None
                )
                
        except Exception as e:
            print(f"Error processing batched reaction for user {user_id}: {e}")
            # Clean up on error
            self._pending_reaction_bets.pop(user_id, None)
            self._reaction_timers.pop(user_id, None)
    
    async def _delayed_reaction_processing(self, user_id: int) -> None:
        """Wait for a short delay, then process the batched reaction."""
        try:
            # Wait for 1 second to allow batching of multiple rapid reactions
            await asyncio.sleep(1.0)
            # Process the final batched reaction
            await self._process_batched_reaction(user_id)
        except asyncio.CancelledError:
            # Timer was cancelled due to a new reaction, clean up
            self._pending_reaction_bets.pop(user_id, None)
            raise
        except Exception as e:
            print(f"Error in delayed reaction processing for user {user_id}: {e}")
            # Clean up on error
            self._pending_reaction_bets.pop(user_id, None)
            self._reaction_timers.pop(user_id, None)

    async def _check_permission(self, ctx: commands.Context, action: str) -> bool:
        """Centralized permission check for betting actions."""
        return await BettingPermissions.check_permission(ctx, action)

    async def _send_embed(
        self, ctx: commands.Context, title: str, description: str, color: discord.Color
    ) -> None:
        """Sends a consistent embed message."""
        await BettingUtils.send_embed(ctx, title, description, color)

    def _find_fuzzy_contestant(self, data: Data, input_name: str) -> Optional[Tuple[str, str]]:
        """Find contestant with fuzzy matching for typo tolerance."""
        contestants = data["betting"].get("contestants", {})
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

        # Find and validate contestant
        contestant_info = self._find_contestant_info(data, choice)
        if not contestant_info:
            if notify_user and channel:
                # Generate helpful error message with available contestants
                contestants = data["betting"].get("contestants", {})
                if contestants:
                    contestants_list = "\n".join([f"• **{name}**" for name in contestants.values()])
                    example_contestant = list(contestants.values())[0]
                    error_msg = MSG_UNKNOWN_CONTESTANT.format(
                        contestant_name=choice,
                        contestants_list=contestants_list,
                        example_contestant=example_contestant
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

        # Check if user has an existing bet with an emoji (reaction bet) and this is a manual bet
        existing_bet = data["betting"]["bets"].get(user_id)
        old_emoji = existing_bet.get("emoji") if existing_bet else None
        
        # If placing a manual bet (no emoji) after a reaction bet (has emoji), remove the old reaction
        if old_emoji and not emoji:
            await self._remove_old_reaction_bet(data, user_id, old_emoji)

        # Use BetState to handle bet placement which will handle refunds and balance updates
        bet_state = BetState(data)
        if not bet_state.place_bet(user_id, amount, contestant_name, emoji):
            logger.warning(f"Bet placement failed for user {user_id}: {amount} on {contestant_name}")
            return False

        # Log successful bet placement
        logger.info(f"Bet placed: User {user_id} bet {amount} coins on {contestant_name}")
        performance_monitor.record_metric('bet.placed', 1, {
            'contestant': contestant_name,
            'amount': str(amount)
        })

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

        return True

    def _find_contestant_info(
        self, data: Data, choice_input: str
    ) -> Optional[Tuple[str, str]]:
        """Finds a contestant ID and name based on fuzzy matching for typo tolerance."""
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
                        wait_time = 0.5 * (2 ** attempt)
                        print(f"Rate limited adding reaction {emoji}, waiting {wait_time}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"Failed to add reaction {emoji} after {max_retries + 1} attempts: {e}")
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
        # print(f"DEBUG: Attempting to remove reactions for user {user.name} (ID: {user.id}) on message {message.id}")
        all_betting_emojis = data["contestant_1_emojis"] + data["contestant_2_emojis"]
        # print(f"DEBUG: All configured betting emojis: {all_betting_emojis}")
        for emoji_str in all_betting_emojis:
            if emoji_str == exclude_emoji:
                # print(f"DEBUG: Skipping removal of exclude_emoji: {emoji_str}")
                continue  # Skip the emoji that was just added

            try:
                # Mark this removal as programmatic to prevent race condition
                self._mark_programmatic_removal(message.id, user.id, emoji_str)
                # print(f"DEBUG: Removing reaction: {emoji_str}")
                await message.remove_reaction(emoji_str, user)
                # print(f"DEBUG: Successfully removed reaction: {emoji_str}")
            except discord.NotFound:
                # print(f"DEBUG: Reaction {emoji_str} not found for user {user.name}, skipping.")
                # Remove the mark since the removal didn't happen
                self._is_programmatic_removal(message.id, user.id, emoji_str)
                pass
            except discord.HTTPException as e:
                # Remove the mark since the removal failed
                self._is_programmatic_removal(message.id, user.id, emoji_str)
                print(
                    f"ERROR: Failed to remove reaction {emoji_str} from user {user.name}: {e}"
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

        # Get live message info and remove reaction from both main and secondary messages
        main_msg_id, main_chan_id = get_live_message_info(data)
        secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

        # Remove from main message
        if main_msg_id and main_chan_id:
            await self._remove_reaction_from_message(main_chan_id, main_msg_id, user, old_emoji)

        # Remove from secondary message
        if secondary_msg_id and secondary_chan_id:
            await self._remove_reaction_from_message(secondary_chan_id, secondary_msg_id, user, old_emoji)

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
            print(f"DEBUG: Removed reaction {emoji} from user {user.name} on message {message_id}")
        except discord.NotFound:
            # Message or reaction not found, that's fine
            pass
        except discord.HTTPException as e:
            print(f"ERROR: Failed to remove reaction {emoji} from user {user.name} on message {message_id}: {e}")

    async def _create_payout_summary(self, winner_info: WinnerInfo, user_names: Dict[str, str]) -> str:
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
                winners.append(f"🏆 **{user_name}**: Bet `{bet_amount}` → Won `{winnings}` (Net: +`{net_change}`)")
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
        """Handles the logic for declaring a winner, distributing coins, and resetting the bet state."""
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
        if not data["betting"]["bets"]:
            await self._send_embed(
                ctx,
                "Round Complete",
                f"No bets were placed in this round. {winner_name} wins by default!",
                COLOR_SUCCESS,
            )
            # Reset betting state even with no bets
            self.bet_state.declare_winner(winner_name)
            return

        # Calculate statistics BEFORE processing winner (which clears bet data)
        total_bettors = len(data["betting"]["bets"])
        total_pot = sum(bet["amount"] for bet in data["betting"]["bets"].values())
        bets_on_winner = sum(1 for bet in data["betting"]["bets"].values() 
                           if bet["choice"].lower() == winner_name.lower())
        
        # Process winner through BetState
        winner_info = self.bet_state.declare_winner(winner_name)
        
        # Log winner declaration
        logger.info(f"Winner declared: {winner_name} - Total pot: {total_pot} coins, {total_bettors} bettors")
        performance_monitor.record_metric('betting.winner_declared', 1, {
            'winner': winner_name,
            'total_pot': str(total_pot),
            'total_bettors': str(total_bettors)
        })
        
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

        # Update live message with detailed results
        await update_live_message(
            self.bot,
            data,
            winner_declared=True,
            winner_info=winner_info
        )
        
        # Also schedule batched update for consistency and any pending changes
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

        # Re-added functionality: Clear all reactions from live messages when bets are locked
        main_msg_id, main_chan_id = get_live_message_info(data)
        secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

        messages_to_clear_reactions = []
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

        # Update live message immediately to show locked state
        await update_live_message(
            self.bot, data, betting_closed=True, close_summary=lock_summary
        )
        
        # Also schedule a batched update to handle any last-moment bets that might be pending
        schedule_live_message_update()
        if not silent_lock:  # Only send the locked message if not a silent lock
            await self._send_embed(
                ctx, TITLE_BETS_LOCKED, lock_summary, COLOR_DARK_ORANGE
            )

    # --- Discord Commands ---

    @commands.command(name="openbet", aliases=["ob"])
    async def openbet(self, ctx: commands.Context, name1: Optional[str] = None, name2: Optional[str] = None) -> None:
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
                COLOR_ERROR
            )
            return
            
        # Check if contestant names are too long (Discord embed field limit considerations)
        if len(name1) > 50 or len(name2) > 50:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                "**Contestant names are too long.**\nPlease keep contestant names under 50 characters each.\nExample: `!openbet Alice Bob`",
                COLOR_ERROR
            )
            return

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

        # Log betting round opened
        logger.info(f"Betting round opened: {name1} vs {name2} by user {ctx.author}")
        performance_monitor.record_metric('betting.round_opened', 1, {
            'contestant1': name1,
            'contestant2': name2
        })

        main_chan_id = get_saved_bet_channel_id(data)
        target_channel: Optional[discord.TextChannel] = None

        if main_chan_id:
            channel_obj = self.bot.get_channel(main_chan_id)
            if isinstance(channel_obj, discord.TextChannel):
                target_channel = channel_obj

        # If no valid saved text channel, try to use the context channel if it's a text channel
        if target_channel is None and isinstance(ctx.channel, discord.TextChannel):
            target_channel = ctx.channel

        # If still no target_channel (e.g., ctx.channel is a DMChannel and no saved channel)
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
            set_live_message_info(data, main_live_msg.id, target_channel.id)

            # update_live_message will now calculate remaining_time if not passed
            await update_live_message(
                self.bot, data
            )  # Call update_live_message here to populate the embed
        except Exception as e:
            print(f"Error sending main live message: {e}")
            set_live_message_info(data, None, None)
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_FAILED_SEND_LIVE_MESSAGE, COLOR_ERROR
            )
            return

        if main_live_msg:
            # Add reactions in the background to avoid blocking the betting round opening
            self._add_reactions_background(main_live_msg, data)

        # Only send a secondary message if ctx.channel is a TextChannel and different from target_channel
        if (
            isinstance(ctx.channel, discord.TextChannel)
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
            if data["settings"]["enable_bet_timer"]:
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ROUND_OPENED,
                    f"Betting round opened for **{name1}** vs **{name2}**! Bets will automatically lock in `{BET_TIMER_DURATION}` seconds.",
                    COLOR_SUCCESS,
                )
            else:
                await self._send_embed(
                    ctx,
                    TITLE_BETTING_ROUND_OPENED,
                    f"Betting round opened for **{name1}** vs **{name2}**! Use `!lockbets` to close.",
                    COLOR_SUCCESS,
                )
        # If opened in the set bet channel, no additional message needed - live message provides all info

        # Schedule the betting timer if enabled (moved here, after live message is set up)
        if data["settings"]["enable_bet_timer"]:
            await self.timer.start_timer(ctx, BET_TIMER_DURATION, self._handle_timer_expired)

    @commands.command(name="lockbets", aliases=["lb"])
    async def lock_bets(self, ctx: commands.Context) -> None:
        if not await self._check_permission(ctx, "close betting rounds"):
            return

        await self._lock_bets_internal(ctx)

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
        await self._process_winner_declaration(ctx, data, winner)  # Updated call

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

        if data["betting"]["open"]:
            await self._lock_bets_internal(
                ctx, silent_lock=True
            )  # This will set data["betting"]["locked"] = True, silently
        data = load_data()  # Reload data after locking

        self._cancel_bet_timer()
        await self._process_winner_declaration(ctx, data, winner)  # Updated call

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
        performance_monitor.record_metric('betting.timer_toggled', 1, {
            'status': status,
            'user': str(ctx.author)
        })
        
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
                    self.bot, data, data["betting"]["open"] or data["betting"]["locked"]
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
                    self.bot, data, True  # Show live message link since bets are locked
                )
                if live_message_link:
                    await self._send_embed(
                        ctx, 
                        TITLE_BETTING_ERROR, 
                        MSG_BET_LOCKED_WITH_LIVE_LINK.format(live_link=live_message_link), 
                        COLOR_ERROR
                    )
                else:
                    await self._send_embed(
                        ctx, TITLE_BETTING_ERROR, MSG_BET_LOCKED_NO_NEW_BETS, COLOR_ERROR
                    )
            else:
                await self._send_embed(
                    ctx, TITLE_NO_OPEN_BETTING_ROUND, MSG_NO_ACTIVE_BET, COLOR_ERROR
                )
            return

        # Existing checks for active/locked bet when arguments are provided
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
            # Incorrect number of arguments (this block is now only reached if len(args) is not 0 or 2)
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
                contestants_list = "\n".join([f"• **{name}**" for name in contestants.values()])
                example_contestant = list(contestants.values())[0]
                error_msg = MSG_UNKNOWN_CONTESTANT.format(
                    contestant_name=choice,
                    contestants_list=contestants_list,
                    example_contestant=example_contestant
                )
            else:
                error_msg = "No betting round is currently active."
            
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, error_msg, COLOR_ERROR
            )
            return

        contestant_id, contestant_name = contestant_info

        # Check if user is changing an existing bet
        user_id_str = str(ctx.author.id)
        existing_bet = data["betting"]["bets"].get(user_id_str)
        old_contestant = existing_bet.get("choice") if existing_bet else None
        old_amount = existing_bet.get("amount", 0) if existing_bet else 0

        # Use BetState for proper balance validation (accounts for existing bet refunds)
        bet_state = BetState(data)
        user_balance = bet_state.economy.get_balance(user_id_str)
        required_additional = amount - old_amount

        if required_additional > user_balance:
            current_bet_info = f"\n🎯 **Current bet:** `{old_amount}` coins on **{old_contestant}**" if existing_bet else ""
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
        is_bet_change = existing_bet and old_contestant and old_contestant.lower() != contestant_name.lower()
        
        success = await self._process_bet(
            channel, data, user_id_str, amount, contestant_name, notify_user=False
        )
        
        if success:
            # Send appropriate success message
            if is_bet_change:
                amount_change = amount - old_amount
                change_indicator = f" (net change: {'+'if amount_change > 0 else ''}{amount_change} coins)" if amount_change != 0 else ""
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
    async def bet_all(self, ctx: commands.Context, *, contestant: Optional[str] = None) -> None:
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
                        MSG_BET_LOCKED_WITH_LIVE_LINK.format(live_link=live_message_link), 
                        COLOR_ERROR
                    )
                else:
                    await self._send_embed(
                        ctx, TITLE_BETTING_ERROR, MSG_BET_LOCKED_NO_NEW_BETS, COLOR_ERROR
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
                        MSG_BET_LOCKED_WITH_LIVE_LINK.format(live_link=live_message_link), 
                        COLOR_ERROR
                    )
                else:
                    await self._send_embed(
                        ctx, TITLE_BETTING_ERROR, MSG_BET_LOCKED_NO_NEW_BETS, COLOR_ERROR
                    )
            else:
                # No betting round at all
                await self._send_embed(
                    ctx, TITLE_BETTING_ERROR, MSG_NO_ACTIVE_BET, COLOR_ERROR
                )
            return

        # Ensure the user has an account
        ensure_user(data, str(ctx.author.id))  # Fix: Convert to string

        user_bet = data["betting"]["bets"].get(str(ctx.author.id))
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
        bet_percentage = (user_bet['amount'] / (user_balance + user_bet['amount'])) * 100 if (user_balance + user_bet['amount']) > 0 else 0
        
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
                bet_info.append(f"⏱️ **Time Remaining:** {remaining_time}s to modify bet")
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
                # Betting round exists but is locked - show current betting info
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
                    "\n".join(locked_info) + (
                        f"\n\n**Live Message:** [View Current Bets]({live_message_link})"
                        if live_message_link else ""
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
    @commands.has_permissions(manage_guild=True)  # Added permission check for manualbet
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

        # Place the bet
        data["betting"]["bets"][str(user.id)] = {
            "amount": amount,
            "choice": contestant_name.lower(),
            "emoji": None,  # Manual bets do not have an associated emoji
        }
        data["balances"][str(user.id)] -= amount
        save_data(data)

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
        debug_info = f"Betting Open: {data['betting']['open']}\nBets Locked: {data['betting']['locked']}\nTotal Bets: {len(data['betting']['bets'])}"
        await ctx.send(f"```\n{debug_info}\n```")

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
            "contestants": {}
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
            discord.Color.green()
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        # Ignore bot's own reactions
        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        data = load_data()
        main_msg_id, main_chan_id = get_live_message_info(data)
        secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

        # Check if the reaction is on one of the live betting messages
        is_main_message = (
            payload.message_id == main_msg_id and payload.channel_id == main_chan_id
        )
        is_secondary_message = (
            payload.message_id == secondary_msg_id
            and payload.channel_id == secondary_chan_id
        )

        if not (is_main_message or is_secondary_message):
            return  # Not a reaction on a live betting message

        # Ensure betting is open
        if not data["betting"]["open"]:
            # If betting is locked, remove the reaction and inform the user (optional, but good UX)
            channel = self.bot.get_channel(payload.channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(payload.message_id)
                    user = await self.bot.fetch_user(payload.user_id)
                    await message.remove_reaction(payload.emoji, user)
                    # await self._send_embed(channel, TITLE_BETTING_ERROR, MSG_BET_LOCKED_NO_NEW_BETS, COLOR_ERROR) # Can't use ctx here
                except discord.NotFound:
                    pass
                except discord.HTTPException as e:
                    print(f"Error removing reaction or sending message: {e}")
            return

        # Get message and user objects
        channel = self.bot.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
            user = await self.bot.fetch_user(payload.user_id)
        except discord.NotFound:
            print(f"Message or user not found for reaction payload: {payload}")
            return
        except discord.HTTPException as e:
            print(f"Error fetching message or user for reaction: {e}")
            return

        # Determine contestant from emoji
        contestant_id = _get_contestant_from_emoji(data, str(payload.emoji))
        if not contestant_id:
            # Not a betting emoji, remove reaction
            await message.remove_reaction(payload.emoji, user)
            return

        contestant_name = data["betting"]["contestants"].get(contestant_id)
        if not contestant_name:
            print(f"Contestant name not found for ID {contestant_id}")
            await message.remove_reaction(payload.emoji, user)
            return

        # Get bet amount from reaction emoji
        bet_amount = data["reaction_bet_amounts"].get(str(payload.emoji))
        if bet_amount is None:
            print(f"No bet amount configured for emoji {payload.emoji}")
            await message.remove_reaction(payload.emoji, user)
            return

        # Ensure user has an account and sufficient balance
        ensure_user(data, str(user.id))
        user_balance = data["balances"][str(user.id)]

        if bet_amount > user_balance:
            # Insufficient balance, remove reaction and inform user in the channel
            await message.remove_reaction(payload.emoji, user)
            shortfall = bet_amount - user_balance
            embed = discord.Embed(
                title="❌ Insufficient Funds",
                description=f"<@{user.id}> 💰 **Your balance:** `{user_balance}` coins\n💸 **Reaction bet:** `{bet_amount}` coins\n❌ **You need:** `{shortfall}` more coins",
                color=COLOR_ERROR,
            )
            await channel.send(embed=embed)
            return

        # Use batching system to handle multiple rapid reactions
        # Cancel any existing timer for this user
        self._cancel_user_reaction_timer(user.id)
        
        # Store the pending bet information (this will overwrite any previous pending bet)
        self._pending_reaction_bets[user.id] = {
            "message": message,
            "user": user,
            "data": data,
            "contestant_name": contestant_name,
            "bet_amount": bet_amount,
            "emoji": str(payload.emoji),
            "channel": channel
        }
        
        # Start a new timer to process this bet after a short delay
        # This allows multiple rapid reactions to be batched together
        self._reaction_timers[user.id] = asyncio.create_task(
            self._delayed_reaction_processing(user.id)
        )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        # Ignore bot's own reactions
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        
        # Check if this is a programmatic removal (to prevent race conditions)
        if self._is_programmatic_removal(payload.message_id, payload.user_id, str(payload.emoji)):
            return  # This was a programmatic removal, don't process it as user action

        data = load_data()
        main_msg_id, main_chan_id = get_live_message_info(data)
        secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

        # Check if the reaction is on one of the live betting messages
        is_main_message = (
            payload.message_id == main_msg_id and payload.channel_id == main_chan_id
        )
        is_secondary_message = (
            payload.message_id == secondary_msg_id
            and payload.channel_id == secondary_chan_id
        )

        if not (is_main_message or is_secondary_message):
            return  # Not a reaction on a live betting message

        # Ensure betting is open
        if not data["betting"]["open"]:
            return  # Cannot unbet if betting is not open

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
        if user_id_str in data["betting"]["bets"]:
            bet_info = data["betting"]["bets"][user_id_str]
            contestant_name = data["betting"]["contestants"].get(contestant_id)

            if contestant_name and bet_info["choice"] == contestant_name.lower():
                # When removing a bet, just process the refund and cleanup
                refund_amount = bet_info["amount"]
                data["balances"][user_id_str] += refund_amount
                del data["betting"]["bets"][user_id_str]
                save_data(data)
                schedule_live_message_update()  # Schedule batched update


async def setup(bot: commands.Bot):
    await bot.add_cog(Betting(bot))
