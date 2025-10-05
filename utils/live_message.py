from config import (
    LIVE_MESSAGE_KEY,
    LIVE_CHANNEL_KEY,
    LIVE_SECONDARY_KEY,
    LIVE_SECONDARY_CHANNEL_KEY,
    BET_TIMER_DURATION,
)
import discord
import time
import asyncio
from typing import Optional, Tuple, Dict, Any, cast, List, Set

from data_manager import save_data, Data
from .message_formatter import MessageFormatter
from .bet_state import WinnerInfo, BettingSession, TimerInfo


class LiveMessageScheduler:
    """Batches live message updates on a 5-second schedule to reduce API calls."""

    def __init__(self):
        # Set of session ids (or 'default') needing updates
        self.pending_updates: Set[str] = set()
        # Skip batched update until this timestamp (epoch seconds). Used to
        # avoid overwriting immediate special embeds (winner/locked) with a
        # subsequent batched update.
        self.skip_until: float = 0.0
        self.update_task: Optional[asyncio.Task] = None
        self.bot: Optional[discord.Client] = None
        self.is_running = False

    def set_bot(self, bot: discord.Client) -> None:
        """Set the bot instance for making Discord API calls."""
        self.bot = bot

    def schedule_update(self, data_identifier: str = "default") -> None:
        """Schedule a live message update. Multiple calls within 5 seconds are batched."""
        if not self.bot:
            return

        self.pending_updates.add(data_identifier)
        # No additional params are stored for batched updates. If callers need
        # to prevent the batched update from overwriting a special immediate
        # update, they should call `suppress_next_batched_update`.

        # Start the update loop if not already running
        if not self.is_running:
            self.is_running = True
            if self.update_task:
                self.update_task.cancel()
            self.update_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self) -> None:
        """Process batched updates every 5 seconds."""
        try:
            while self.pending_updates and self.bot:
                await asyncio.sleep(5.0)  # 5-second batch window

                if self.pending_updates:
                    # Process all pending updates in one batch
                    updates_to_process = self.pending_updates.copy()
                    self.pending_updates.clear()

                    # Load current data once
                    from data_manager import load_data

                    data = load_data()

                    # If a recent immediate special update (winner/close) was
                    # performed, skip calling update_live_message here so we do
                    # not overwrite the special embed. Clear pending updates
                    # and continue.
                    import time as _time

                    if _time.time() < self.skip_until:
                        # Clear any pending markers and continue to next loop
                        self.pending_updates.difference_update(updates_to_process)
                        continue

                    # If exactly one specific session is pending, update only
                    # that session. Otherwise (multiple sessions or the legacy
                    # default), perform a single global update to preserve the
                    # previous batching behavior and reduce API calls.
                    if len(updates_to_process) == 1 and next(iter(updates_to_process)) != "default":
                        identifier = next(iter(updates_to_process))
                        try:
                            await update_live_message(self.bot, data, session_id=identifier)
                        except Exception as e:
                            print(f"Error updating live message for {identifier}: {e}")
                    else:
                        try:
                            await update_live_message(self.bot, data)
                        except Exception as e:
                            print(f"Error updating global live message: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in live message update loop: {e}")
        finally:
            self.is_running = False

    def stop(self) -> None:
        """Stop the update scheduler."""
        self.is_running = False
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None


# Global scheduler instance
live_message_scheduler = LiveMessageScheduler()


# State conversion utilities (moved from state_converter.py)
def convert_to_betting_session(data: Data) -> BettingSession:
    """Converts raw data dict to a BettingSession object."""
    betting_data = data["betting"]
    return {
        "contestants": betting_data.get("contestants", {}),
        "bets": betting_data.get("bets", {}),
        "open": betting_data.get("open", False),
        "locked": betting_data.get("locked", False),
    }


def create_winner_info(
    winner_name: Optional[str], winnings_info: Optional[Dict[str, int]] = None
) -> Optional[WinnerInfo]:
    """Legacy function for backward compatibility. Now uses BetState."""
    if not winner_name:
        return None

    if winnings_info is None:
        winnings_info = {}

    # Create a minimal bet state with just the necessary data
    from .bet_state import BetState
    from typing import TypedDict

    class UserBet(TypedDict):
        amount: int
        choice: str
        emoji: Optional[str]

    data = cast(
        Data,
        {
            "betting": {
                "bets": {
                    user_id: {
                        "amount": abs(winnings) if winnings <= 0 else winnings // 2,
                        "choice": winner_name.lower() if winnings > 0 else "other",
                        "emoji": None,
                    }
                    for user_id, winnings in winnings_info.items()
                },
                "open": False,
                "locked": True,
                "contestants": {},
            },
            "balances": {},
            "settings": {},
            "reaction_bet_amounts": {},
            "contestant_1_emojis": [],
            "contestant_2_emojis": [],
            "live_message": None,
            "live_channel": None,
            "live_secondary_message": None,
            "live_secondary_channel": None,
            "timer_end_time": None,
        },
    )

    # Use the centralized calculation
    bet_state = BetState(data)
    results = bet_state.calculate_round_results(winner_name)

    return {
        "name": winner_name,
        "total_pot": results["total_pot"],
        "winning_pot": results["winning_pot"],
        "user_results": results["user_results"],
    }


def create_timer_info(
    current_remaining_time: Optional[int], current_total_duration: Optional[int]
) -> Optional[TimerInfo]:
    """Creates a TimerInfo object from timer data."""
    if current_remaining_time is None or current_total_duration is None:
        return None

    return {"remaining": current_remaining_time, "total": current_total_duration}


def get_emoji_config(data: Data) -> Dict[str, Any]:
    """Gets reaction emoji configuration from data."""
    return {
        "contestant_1_emojis": data.get("contestant_1_emojis", []),
        "contestant_2_emojis": data.get("contestant_2_emojis", []),
    }


def get_reaction_bet_amounts(data: Data) -> Dict[str, int]:
    """Gets reaction bet amounts configuration from data."""
    return data.get("reaction_bet_amounts", {})


def get_live_message_info(data: Data) -> Tuple[Optional[int], Optional[int]]:
    """Retrieves the main live message ID and channel ID."""
    return data.get(LIVE_MESSAGE_KEY), data.get(LIVE_CHANNEL_KEY)


def get_secondary_live_message_info(data: Data) -> Tuple[Optional[int], Optional[int]]:
    """Retrieves the secondary live message ID and channel ID."""
    return data.get(LIVE_SECONDARY_KEY), data.get(LIVE_SECONDARY_CHANNEL_KEY)


def get_saved_bet_channel_id(data: Data) -> Optional[int]:
    """Retrieves the configured main betting channel ID."""
    return data.get(LIVE_CHANNEL_KEY)


def set_live_message_info(
    data: Data, message_id: Optional[int], channel_id: Optional[int]
) -> None:
    """Sets the main live message ID and channel ID."""
    data[LIVE_MESSAGE_KEY] = message_id
    data[LIVE_CHANNEL_KEY] = channel_id
    save_data(data)


def set_secondary_live_message_info(
    data: Data, message_id: Optional[int], channel_id: Optional[int]
) -> None:
    """Sets the secondary live message ID and channel ID."""
    data[LIVE_SECONDARY_KEY] = message_id
    data[LIVE_SECONDARY_CHANNEL_KEY] = channel_id
    save_data(data)


def clear_live_message_info(data: Data) -> None:
    """Clears all live message information."""
    data[LIVE_MESSAGE_KEY] = None
    data[LIVE_CHANNEL_KEY] = None
    data[LIVE_SECONDARY_KEY] = None
    data[LIVE_SECONDARY_CHANNEL_KEY] = None
    save_data(data)


def get_live_message_link(bot: discord.Client, data: Data, is_active: bool) -> str:
    """Generates a link to the live betting message if it exists."""
    msg_id, chan_id = get_live_message_info(data)
    if msg_id and chan_id:
        # Safely get guild ID, assuming the bot is in at least one guild
        if bot.guilds:
            guild_id = bot.guilds[0].id  # Using the first guild the bot is in
            return f"[Go to Live Betting Message](https://discord.com/channels/{guild_id}/{chan_id}/{msg_id})"
    return ""


def get_session_live_message_info(data: Data, session_id: str) -> Tuple[Optional[int], Optional[int]]:
    """Retrieve the live message id and channel id for a given session."""
    session = data.get("betting_sessions", {}).get(session_id)
    if not session:
        return None, None
    return session.get("live_message_id"), session.get("channel_id")


def set_session_live_message_info(data: Data, session_id: str, message_id: Optional[int], channel_id: Optional[int]) -> None:
    """Set session-specific live message info."""
    session = data.get("betting_sessions", {}).get(session_id)
    if not session:
        return
    session["live_message_id"] = message_id
    # channel_id is already stored as session.channel_id when created; only
    # overwrite if provided
    if channel_id is not None:
        session["channel_id"] = channel_id
    save_data(data)


async def _get_message_and_user(
    bot: discord.Client, payload: discord.RawReactionActionEvent
) -> Tuple[Optional[discord.Message], Optional[discord.User]]:
    """Fetches the message and user from a raw reaction payload."""
    channel = bot.get_channel(payload.channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None, None
    try:
        message = await channel.fetch_message(payload.message_id)
        user = await bot.fetch_user(payload.user_id)
        return message, user
    except discord.NotFound:
        return None, None
    except discord.HTTPException as e:
        print(f"Error fetching message or user: {e}")
        return None, None


# Helper for reaction handling
def _get_contestant_from_emoji(data: Data, emoji: str) -> Optional[str]:
    """Determines the contestant ID (1 or 2) from a reaction emoji."""
    if emoji in data["contestant_1_emojis"]:
        return "1"
    if emoji in data["contestant_2_emojis"]:
        return "2"
    return None


async def _remove_all_betting_reactions(
    message: discord.Message, user: discord.abc.User, data: Data
) -> None:
    """Removes all betting-related reactions from a specific user on a message."""
    all_betting_emojis = data["contestant_1_emojis"] + data["contestant_2_emojis"]
    for emoji_str in all_betting_emojis:
        try:
            await message.remove_reaction(emoji_str, user)
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            print(
                f"Error removing reaction {emoji_str} from user {
                    user.name}: {e}"
            )


async def update_live_message(
    bot: discord.Client,
    data: Data,
    betting_closed: bool = False,
    close_summary: Optional[str] = None,
    winner_declared: bool = False,
    winner_info: Optional[WinnerInfo] = None,
    current_time: Optional[float] = None,
    session_id: Optional[str] = None,
) -> None:
    """Updates the live betting message(s) in Discord.

    If `session_id` is provided, update only that session's dedicated live
    message (if present). Otherwise, update the legacy global main/secondary
    live messages.
    """

    # Helper: update a single message id/channel with an embed
    async def _edit_message(msg_id: int, chan_id: int, embed: discord.Embed):
        channel = bot.get_channel(chan_id)
        if channel and isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(msg_id)
                await message.edit(embed=embed)
                return True
            except discord.NotFound:
                return False
            except discord.HTTPException as e:
                print(f"Error updating live message {msg_id} in channel {chan_id}: {e}")
                return False

    # Build the betting_session representation depending on whether this is
    # session-scoped or the legacy top-level session.
    if session_id:
        session = data.get("betting_sessions", {}).get(session_id)
        if not session:
            return

        # Determine message and channel IDs from session
        msg_id = session.get("live_message_id")
        chan_id = session.get("channel_id")

        # Normalize contestant keys ('c1'/'c2' -> '1'/'2') for MessageFormatter
        raw_contestants = session.get("contestants", {})
        normalized_contestants = {}
        for k, v in raw_contestants.items():
            if isinstance(k, str) and k.startswith("c") and k[1:].isdigit():
                normalized_contestants[k[1:]] = v
            else:
                normalized_contestants[k] = v

        # Build betting_session compatible dict for MessageFormatter
        betting_session = cast(BettingSession, {
            "contestants": normalized_contestants,
            "bets": session.get("bets", {}),
            "open": session.get("status") == "open",
            "locked": session.get("status") == "locked",
        })

        # User names lookup
        user_names = {}
        for user_id in betting_session["bets"].keys():
            try:
                user = await bot.fetch_user(int(user_id))
                user_names[user_id] = user.display_name
            except discord.NotFound:
                user_names[user_id] = f"Unknown User ({user_id})"
            except Exception:
                user_names[user_id] = f"User ({user_id})"

        # Timer info: if session has a timer_config and an auto close/lock
        timer_info = None
        tc = session.get("timer_config")
        if tc and tc.get("enabled"):
            auto_close = tc.get("auto_close_at")
            duration = tc.get("duration")
            if auto_close and duration:
                actual_current_time = current_time if current_time is not None else time.time()
                remaining = int(auto_close - actual_current_time)
                timer_info = create_timer_info(max(0, remaining), int(duration))

        new_embed = await MessageFormatter.create_live_message_embed(
            betting_session=betting_session,
            emoji_config=get_emoji_config(data),
            reaction_amounts=get_reaction_bet_amounts(data),
            user_names=user_names,
            current_time=current_time,
            timer_info=timer_info,
            betting_closed=betting_closed,
            close_summary=close_summary,
            winner_info=winner_info if winner_declared else None,
        )

        # Add session id to the embed footer so it's visible in the live
        # message itself (helps admins reference the session without a
        # separate confirmation message).
        try:
            new_embed.set_footer(text=f"Session ID: {session_id}")
        except Exception:
            # If embed modification fails for any reason, continue silently
            pass

        if msg_id and chan_id:
            ok = await _edit_message(msg_id, chan_id, new_embed)
            if not ok:
                # Clear session live message info if message no longer exists
                session["live_message_id"] = None
                save_data(data)
        return

    # Legacy top-level behavior
    main_msg_id, main_chan_id = get_live_message_info(data)
    secondary_msg_id, secondary_chan_id = get_secondary_live_message_info(data)

    messages_to_update: List[Tuple[Optional[int], Optional[int]]] = []
    if main_msg_id and main_chan_id:
        messages_to_update.append((main_msg_id, main_chan_id))
    if secondary_msg_id and secondary_chan_id:
        messages_to_update.append((secondary_msg_id, secondary_chan_id))

    if not messages_to_update:
        return

    betting_session = convert_to_betting_session(data)
    betting_session = cast(BettingSession, betting_session)

    # Get user names for the bets
    user_names = {}
    for user_id in betting_session["bets"].keys():
        try:
            user = await bot.fetch_user(int(user_id))
            user_names[user_id] = user.display_name
        except discord.NotFound:
            user_names[user_id] = f"Unknown User ({user_id})"
        except Exception:
            user_names[user_id] = f"User ({user_id})"

    # Calculate timer info if betting is open and timer is enabled
    timer_info = None
    if betting_session["open"] and data.get("timer_end_time") is not None:
        timer_end_time_val = cast(float, data["timer_end_time"])
        # Use passed current_time or get a fresh one if not provided
        actual_current_time = current_time if current_time is not None else time.time()
        remaining_time = int(timer_end_time_val - actual_current_time)
        timer_info = create_timer_info(max(0, remaining_time), BET_TIMER_DURATION)

    new_embed = await MessageFormatter.create_live_message_embed(
        betting_session=betting_session,
        emoji_config=get_emoji_config(data),
        reaction_amounts=get_reaction_bet_amounts(data),
        user_names=user_names,
        current_time=current_time,
        timer_info=timer_info,
        betting_closed=betting_closed,
        close_summary=close_summary,
        winner_info=winner_info if winner_declared else None,
    )

    for msg_id, chan_id in messages_to_update:
        if msg_id and chan_id:
            channel = bot.get_channel(chan_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(msg_id)
                    await message.edit(embed=new_embed)
                except discord.NotFound:
                    print(
                        f"Live message {msg_id} not found in channel {chan_id}. Clearing info."
                    )
                    if msg_id == main_msg_id:
                        data[LIVE_MESSAGE_KEY] = None
                        data[LIVE_CHANNEL_KEY] = None
                    elif msg_id == secondary_msg_id:
                        data[LIVE_SECONDARY_KEY] = None
                        data[LIVE_SECONDARY_CHANNEL_KEY] = None
                    save_data(data)
                except discord.HTTPException as e:
                    print(
                        f"Error updating live message {msg_id} in channel {chan_id}: {e}"
                    )


def schedule_live_message_update() -> None:
    """Schedule a batched live message update. Multiple calls within 5 seconds are batched together.
    This is a lightweight trigger for the global scheduler. Use
    `suppress_next_batched_update` if you need to prevent the batched
    update from overwriting a recent immediate special update.
    """
    live_message_scheduler.schedule_update()


def schedule_live_message_update_for_session(session_id: Optional[str] = None) -> None:
    """Schedule a batched update targeted at a specific session. If
    session_id is None, schedule a legacy/global update."""
    identifier = session_id if session_id is not None else "default"
    live_message_scheduler.schedule_update(identifier)


def suppress_next_batched_update(seconds: float = 6.0) -> None:
    """Prevent the next batched update from running for `seconds` seconds.

    This is used to avoid the batched update overwriting a special immediate
    update (for example, winner or locked embeds) that was just posted.
    """
    import time
    from config import LIVE_MESSAGE_SUPPRESSION_SECONDS

    # If caller didn't provide a value, use the configured default
    if seconds is None:
        seconds = LIVE_MESSAGE_SUPPRESSION_SECONDS

    live_message_scheduler.skip_until = time.time() + seconds


def initialize_live_message_scheduler(bot: discord.Client) -> None:
    """Initialize the live message scheduler with the bot instance."""
    live_message_scheduler.set_bot(bot)


def stop_live_message_scheduler() -> None:
    """Stop the live message scheduler."""
    live_message_scheduler.stop()
