import discord
from .state_converter import (
    convert_to_betting_session,
    create_timer_info,
    get_emoji_config,
    get_reaction_bet_amounts
)
import math
import time
from typing import Optional, Tuple, Dict, Any, cast, List

from data_manager import save_data, Data
from .message_formatter import MessageFormatter
from .message_types import WinnerInfo

from config import (
    LIVE_MESSAGE_KEY,
    LIVE_CHANNEL_KEY,
    LIVE_SECONDARY_KEY,
    LIVE_SECONDARY_CHANNEL_KEY,
    BET_TIMER_DURATION,
)


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
            print(f"Error removing reaction {emoji_str} from user {user.name}: {e}")


async def update_live_message(
    bot: discord.Client,
    data: Data,
    betting_closed: bool = False,
    close_summary: Optional[str] = None,
    winner_declared: bool = False,
    winner_info: Optional[WinnerInfo] = None,
    current_time: Optional[float] = None,
) -> None:
    """Updates the live betting message(s) in Discord."""
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
