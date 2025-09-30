import discord
from discord.ext import commands
from typing import Optional, Tuple
import asyncio

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
    TITLE_BETTING_LOCKED_OVERVIEW,
    TITLE_LIVE_BETTING_ROUND,
    TITLE_POT_LOST,
    MSG_NO_ACTIVE_BET_AND_MISSING_ARGS,
    TITLE_NO_OPEN_BETTING_ROUND,
    MSG_BET_CHANGED,
    MSG_PLACE_MANUAL_BET_INSTRUCTIONS,
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
)


class Betting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bet_timer_task: Optional[asyncio.Task] = None

    # --- Helper Methods for Deduplication ---

    async def _send_embed(
        self, ctx: commands.Context, title: str, description: str, color: discord.Color
    ) -> None:
        """Sends a consistent embed message."""
        embed = discord.Embed(title=title, description=description, color=color)
        await ctx.send(embed=embed)

    def _clear_timer_state_in_data(self, data: Data) -> None:
        """Clears timer-related data."""
        data["timer_end_time"] = None
        save_data(data)

    def _find_contestant_info(
        self, data: Data, choice_input: str
    ) -> Optional[Tuple[str, str]]:
        """Finds a contestant ID and name based on partial input."""
        contestants = data["betting"].get("contestants", {})
        choice_lower = choice_input.lower()

        for c_id, c_name in contestants.items():
            if c_name.lower().startswith(choice_lower):
                return c_id, c_name
        return None

    async def _add_betting_reactions(
        self, message: discord.Message, data: Data
    ) -> None:
        """Adds all configured betting reactions to a message."""
        all_emojis_to_add = (
            data["contestant_1_emojis"]
            + [SEPARATOR_EMOJI]
            + data["contestant_2_emojis"]
        )
        for emoji in all_emojis_to_add:
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException as e:
                print(f"Could not add reaction {emoji} to live message: {e}")

    async def _remove_user_betting_reactions(
        self, message: discord.Message, user: discord.abc.User, data: Data
    ) -> None:
        """Removes all betting reactions from a specific user on a message.
        Accepts discord.User or discord.Member (which inherits from User).
        """
        all_betting_emojis = data["contestant_1_emojis"] + data["contestant_2_emojis"]
        for emoji_str in all_betting_emojis:
            try:
                await message.remove_reaction(emoji_str, user)
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                print(f"Error removing reaction {emoji_str} from user {user.name}: {e}")

    # Re-implemented _process_winner_declaration logic
    async def _process_winner_declaration(
        self, ctx: commands.Context, data: Data, winner_name: str
    ) -> None:
        """Handles the logic for declaring a winner, distributing coins, and resetting the bet state."""
        contestants = data["betting"].get("contestants", {})
        bets = data["betting"].get("bets", {})

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

        total_pot = sum(bet["amount"] for bet in bets.values())
        winning_bets = {
            uid: bet
            for uid, bet in bets.items()
            if bet["choice"] == winner_name.lower()
        }
        total_winning_bet_amount = sum(bet["amount"] for bet in winning_bets.values())

        if total_winning_bet_amount == 0:
            # No one bet on the winner, pot is lost
            await self._send_embed(
                ctx,
                TITLE_POT_LOST,
                f"No one bet on **{winner_name}**. The entire pot of `{total_pot}` coins is lost!",
                COLOR_WARNING,
            )
            winnings_info = {}
        else:
            winnings_info = {}
            for user_id, bet_info in winning_bets.items():
                winnings = int(
                    (bet_info["amount"] / total_winning_bet_amount) * total_pot
                )
                data["balances"][user_id] += winnings
                winnings_info[user_id] = winnings

            await self._send_embed(
                ctx,
                TITLE_BETTING_ROUND_OPENED,
                f"**{winner_name}** wins! `{total_pot}` coins distributed among `{len(winning_bets)}` winners.",
                COLOR_SUCCESS,
            )

        # Clear betting state
        data["betting"] = {
            "open": False,
            "locked": False,
            "bets": {},
            "contestants": {},
        }
        self._clear_timer_state_in_data(data)
        save_data(data)

        # Update live message to show final results
        await update_live_message(
            self.bot,
            data,
            winner_declared=True,
            winner_name=winner_name,
            winnings_info=winnings_info,
        )

    # END _process_winner_declaration

    # --- Timer Management ---

    def _cancel_bet_timer(self):
        """Cancels the active betting timer task if it exists and clears its data."""
        if self.bet_timer_task and not self.bet_timer_task.done():
            self.bet_timer_task.cancel()
            self.bet_timer_task = None
            print("Betting timer cancelled.")

        data = load_data()
        if data.get("timer_end_time") is not None:
            self._clear_timer_state_in_data(data)

    async def _run_bet_timer(self, ctx: commands.Context, total_duration: int):
        """Manages the countdown and automatically locks bets."""
        data = load_data()
        end_time = data.get("timer_end_time")
        if end_time is None:  # Fallback if not set, though openbet should set it
            end_time = self.bot.loop.time() + total_duration
            data["timer_end_time"] = end_time
            save_data(data)

        try:
            while True:
                current_time = self.bot.loop.time()
                remaining_time = int(end_time - current_time)
                if remaining_time <= 0:
                    break

                data = load_data()
                if not data["betting"]["open"]:
                    print("Timer detected bet is no longer open, stopping.")
                    break

                # Call update_live_message without remaining_time/total_duration, it will calculate internally
                await update_live_message(self.bot, data, current_time=current_time)
                await asyncio.sleep(BET_TIMER_UPDATE_INTERVAL)

            data = load_data()
            if data["betting"]["open"]:
                print("Timer expired, attempting to lock bets...")
                await self._lock_bets_internal(ctx, timer_expired=True)

        except asyncio.CancelledError:
            print("Betting timer task was cancelled.")
        except Exception as e:
            print(f"Error in bet timer: {e}")
        finally:
            self.bet_timer_task = None
            data = load_data()
            if data.get("timer_end_time") is not None:
                self._clear_timer_state_in_data(data)

    async def _lock_bets_internal(
        self, ctx: commands.Context, timer_expired: bool = False
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

        await update_live_message(
            self.bot, data, betting_closed=True, close_summary=lock_summary
        )
        await self._send_embed(ctx, TITLE_BETS_LOCKED, lock_summary, COLOR_DARK_ORANGE)

    # --- Discord Commands ---

    @commands.command(name="openbet", aliases=["ob"])
    @commands.has_permissions(manage_guild=True)
    async def openbet(self, ctx: commands.Context, name1: str, name2: str) -> None:
        data = load_data()
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
            data["timer_end_time"] = self.bot.loop.time() + BET_TIMER_DURATION
        else:
            data["timer_end_time"] = None
        save_data(data)

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
            await self._add_betting_reactions(main_live_msg, data)

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
        else:
            # Send a brief confirmation if opened in the set bet channel
            await self._send_embed(
                ctx,
                "✅ Betting Round Opened",
                f"Betting round for **{name1}** vs **{name2}** started in this channel.",
                COLOR_SUCCESS,
            )

        # Schedule the betting timer if enabled (moved here, after live message is set up)
        if data["settings"]["enable_bet_timer"]:
            self.bet_timer_task = self.bot.loop.create_task(
                self._run_bet_timer(ctx, BET_TIMER_DURATION)
            )

    @commands.command(name="lockbets", aliases=["lb"])
    @commands.has_permissions(manage_guild=True)
    async def lock_bets(self, ctx: commands.Context) -> None:
        await self._lock_bets_internal(ctx)

    @commands.command(name="declarewinner", aliases=["dw"])
    @commands.has_permissions(manage_guild=True)
    async def declare_winner(self, ctx: commands.Context, winner: str) -> None:
        data = load_data()
        if not data["betting"]["locked"]:
            await self._send_embed(
                ctx, TITLE_CANNOT_CLOSE_BETS, MSG_INTERNAL_ERROR_LOCKED, COLOR_ERROR
            )
            return

        self._cancel_bet_timer()
        await self._process_winner_declaration(ctx, data, winner)  # Updated call

    @commands.command(name="closebet", aliases=["cb"])
    @commands.has_permissions(manage_guild=True)
    async def close_bet(self, ctx: commands.Context, winner: str) -> None:
        data = load_data()
        if not data["betting"]["open"] and not data["betting"]["locked"]:
            await self._send_embed(
                ctx, TITLE_CANNOT_CLOSE_BETS, MSG_NO_BETS_TO_CLOSE, COLOR_ERROR
            )
            return

        if data["betting"]["open"]:
            await self._lock_bets_internal(
                ctx
            )  # This will set data["betting"]["locked"] = True
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
    @commands.has_permissions(manage_guild=True)
    async def toggle_bet_timer(self, ctx: commands.Context) -> None:
        data = load_data()
        data["settings"]["enable_bet_timer"] = not data["settings"]["enable_bet_timer"]
        save_data(data)

        status = "enabled" if data["settings"]["enable_bet_timer"] else "disabled"
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
                    f"**How to bet:** {MSG_PLACE_MANUAL_BET_INSTRUCTIONS}"
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
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_INVALID_BET_FORMAT, COLOR_ERROR
            )
            return

        contestant_id, contestant_name = contestant_info

        # Deduct the bet amount from the user's balance
        user_balance = data["balances"][str(ctx.author.id)]
        if amount > user_balance:
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                f"Insufficient balance! Your current balance is `{user_balance}` coins.",
                COLOR_ERROR,
            )
            return

        # Place the bet
        data["betting"]["bets"][str(ctx.author.id)] = {
            "amount": amount,
            "choice": contestant_name.lower(),
            "emoji": None,  # Manual bets do not have an associated emoji
        }
        data["balances"][str(ctx.author.id)] -= amount
        save_data(data)

        # Update the live message with the new bet
        await update_live_message(self.bot, data)

        await self._send_embed(
            ctx,
            TITLE_BET_PLACED,
            f"Your bet of `{amount}` coins on **{contestant_name}** has been placed!",
            COLOR_SUCCESS,
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

    @commands.command(name="mybet")
    async def mybet(self, ctx: commands.Context) -> None:
        data = load_data()
        if not data["betting"]["open"]:
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

        await self._send_embed(
            ctx,
            TITLE_CURRENT_BETS_OVERVIEW,
            f"Your current bet:\n- Amount: `{user_bet['amount']}` coins\n- Choice: **{contestant_name}**",
            COLOR_INFO,
        )

    @commands.command(name="bettinginfo")
    async def bettinginfo(self, ctx: commands.Context) -> None:
        data = load_data()
        if not data["betting"]["open"]:
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

    @commands.command(name="forcewinner")
    @commands.has_permissions(manage_guild=True)
    async def forcewinner(self, ctx: commands.Context, *, winner_name: str) -> None:
        data = load_data()
        if not data["betting"]["open"]:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_NO_ACTIVE_BET, COLOR_ERROR
            )
            return

        await self._process_winner_declaration(ctx, data, winner_name)

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

    @commands.command(name="bettingsummary")
    async def betting_summary(self, ctx: commands.Context) -> None:
        data = load_data()
        if not data["betting"]["open"]:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_NO_ACTIVE_BET, COLOR_ERROR
            )
            return

        total_bets = len(data["betting"]["bets"])
        contestant1_bets = sum(
            1
            for bet in data["betting"]["bets"].values()
            if bet["choice"] == "contestant_1"
        )
        contestant2_bets = sum(
            1
            for bet in data["betting"]["bets"].values()
            if bet["choice"] == "contestant_2"
        )

        await self._send_embed(
            ctx,
            TITLE_BETTING_LOCKED_OVERVIEW,
            f"Total Bets: `{total_bets}`\nBets on Contestant 1: `{contestant1_bets}`\nBets on Contestant 2: `{contestant2_bets}`",
            COLOR_INFO,
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
            await self._send_embed(
                ctx,
                TITLE_BETTING_ERROR,
                f"Insufficient balance! User's current balance is `{user_balance}` coins.",
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

        # Update the live message with the new bet
        await update_live_message(self.bot, data)

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
            # No direct message, inform in channel
            embed = discord.Embed(
                title=TITLE_BETTING_ERROR,
                description=f"<@{user.id}>, insufficient balance! Your current balance is `{user_balance}` coins.",
                color=COLOR_ERROR,
            )
            await channel.send(embed=embed)
            return

        # Process the bet
        user_id_str = str(user.id)
        previous_bet_info = data["betting"]["bets"].get(user_id_str)

        if previous_bet_info:
            # Refund previous bet and remove old reaction
            previous_amount = previous_bet_info["amount"]
            previous_emoji = previous_bet_info.get(
                "emoji"
            )  # Get the emoji from the stored bet
            old_contestant_name = previous_bet_info["choice"]
            data["balances"][user_id_str] += previous_amount

            if previous_emoji:
                try:
                    await message.remove_reaction(previous_emoji, user)
                except discord.NotFound:
                    pass  # Reaction already removed
                except discord.HTTPException as e:
                    print(
                        f"Error removing previous reaction {previous_emoji} from user {user.name}: {e}"
                    )

            # Send bet changed message
            channel = self.bot.get_channel(payload.channel_id)
            if isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title="🔄 Bet Changed",
                    description=MSG_BET_CHANGED.format(
                        user_id=user.id,
                        amount=bet_amount,
                        old_contestant=old_contestant_name.capitalize(),
                        new_contestant=contestant_name.capitalize(),
                    ),
                    color=COLOR_INFO,
                )
                await channel.send(embed=embed)

        data["balances"][user_id_str] -= bet_amount
        data["betting"]["bets"][user_id_str] = {
            "amount": bet_amount,
            "choice": contestant_name.lower(),
            "emoji": str(payload.emoji),  # Store the emoji used for this bet
        }
        save_data(data)

        # No longer remove user's reaction here, it stays to indicate active bet
        # await self._remove_user_betting_reactions(message, user, data)

        # Update live message
        await update_live_message(self.bot, data, current_time=self.bot.loop.time())

        # No direct message, just update live message
        # embed = discord.Embed(title=TITLE_BET_PLACED, description=f"<@{user.id}>, your bet of `{bet_amount}` coins on **{contestant_name}** has been placed via reaction!", color=COLOR_SUCCESS)
        # await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
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
                # User is removing a bet they previously placed with this emoji
                refund_amount = bet_info["amount"]
                data["balances"][user_id_str] += refund_amount
                del data["betting"]["bets"][user_id_str]
                save_data(data)

                # Update live message
                await update_live_message(self.bot, data)

                # Inform user of successful unbet in the channel (removed as per instructions)
                # channel = self.bot.get_channel(payload.channel_id)
                # if isinstance(channel, discord.TextChannel):
                #     embed = discord.Embed(title="✅ Bet Removed", description=f"<@{user.id}>, your bet of `{refund_amount}` coins on **{contestant_name}** has been removed.", color=COLOR_INFO)
                #     await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Betting(bot))
