import discord
from discord.ext import commands
import math
import time
from typing import Optional, Tuple, Dict, Any, cast, List

from data_manager import save_data, Data
from config import (
    LIVE_MESSAGE_KEY, LIVE_CHANNEL_KEY, LIVE_SECONDARY_KEY, LIVE_SECONDARY_CHANNEL_KEY,
    CONTESTANT_EMOJIS,
    COLOR_GOLD, COLOR_DARK_ORANGE, COLOR_DARK_GRAY,
    BET_TIMER_DURATION, TITLE_LIVE_BETTING_ROUND,
    MSG_A_WINNER_DECLARED_SOON, MSG_BET_LOCKED_NO_NEW_BETS,
    MSG_PLACE_MANUAL_BET_INSTRUCTIONS, MSG_NO_ACTIVE_BET, MSG_WAIT_FOR_ADMIN_TO_START,
    TITLE_BETS_LOCKED, TITLE_NO_ACTIVE_BETTING_ROUND, MSG_NO_BETS_PLACED_YET
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

def set_live_message_info(data: Data, message_id: Optional[int], channel_id: Optional[int]) -> None:
    """Sets the main live message ID and channel ID."""
    data[LIVE_MESSAGE_KEY] = message_id
    data[LIVE_CHANNEL_KEY] = channel_id
    save_data(data)

def set_secondary_live_message_info(data: Data, message_id: Optional[int], channel_id: Optional[int]) -> None:
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
            guild_id = bot.guilds[0].id # Using the first guild the bot is in
            return f"[Go to Live Betting Message](https://discord.com/channels/{guild_id}/{chan_id}/{msg_id})"
    return ""

async def _get_message_and_user(bot: discord.Client, payload: discord.RawReactionActionEvent) -> Tuple[Optional[discord.Message], Optional[discord.User]]:
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

def _get_contestant_from_emoji(data: Data, emoji: str) -> Optional[str]:
    """Determines the contestant ID (1 or 2) from a reaction emoji."""
    if emoji in data["contestant_1_emojis"]:
        return "1"
    if emoji in data["contestant_2_emojis"]:
        return "2"
    return None

async def _remove_all_betting_reactions(message: discord.Message, user: discord.abc.User, data: Data) -> None:
    """Removes all betting-related reactions from a specific user on a message."""
    all_betting_emojis = data["contestant_1_emojis"] + data["contestant_2_emojis"]
    for emoji_str in all_betting_emojis:
        try:
            await message.remove_reaction(emoji_str, user)
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            print(f"Error removing reaction {emoji_str} from user {user.name}: {e}")

def _generate_timer_display(remaining_time: int, total_duration: int) -> str:
    """Generates the timer display string with progress bar."""
    # Ensure remaining_time doesn't go negative for display purposes
    display_remaining_time = max(0, remaining_time)

    minutes = display_remaining_time // 60
    seconds = display_remaining_time % 60
    
    # Calculate elapsed time percentage for the bar to fill from left to right
    # If total_duration is 0 (shouldn't happen for timer), avoid division by zero
    if total_duration <= 0:
        progress_bar = "░" * 10 # Default empty bar
    else:
        elapsed_time = total_duration - display_remaining_time
        elapsed_percentage = (elapsed_time / total_duration) * 100
        num_blocks = math.floor(elapsed_percentage / 10) 
        progress_bar = "█" * num_blocks + "░" * (10 - num_blocks)

    return f"**Time Remaining:** `{minutes:02d}:{seconds:02d}` [{progress_bar}]"

# NEW HELPER: Generate a progress bar for contestant bets
def _generate_bet_progress_bar(current_amount: int, total_pot: int, bar_length: int = 10) -> str:
    """Generates a visual progress bar for a contestant's bet amount relative to the total pot."""
    if total_pot == 0:
        return "░" * bar_length
    
    percentage = (current_amount / total_pot) * 100
    num_blocks = math.ceil(percentage / (100 / bar_length)) # Calculate blocks based on bar_length
    return "█" * num_blocks + "░" * (bar_length - num_blocks)

def _get_condensed_bet_summary(data: Data, include_reaction_info: bool = False) -> str:
    """Generates a condensed summary of current bets, including contestant bet bars."""
    contestants = data["betting"].get("contestants", {})
    bets = data["betting"].get("bets", {})

    summary = ""
    total_pot = sum(bet["amount"] for bet in bets.values())
    
    if total_pot > 0:
        summary += f"**Total Pot:** `{total_pot}` coins\n"

    # Group bets by contestant
    contestant_bets: Dict[str, List[Dict[str, Any]]] = {c_id: [] for c_id in contestants}
    for user_id, bet_info in bets.items():
        for c_id, c_name in contestants.items():
            if bet_info["choice"] == c_name.lower():
                contestant_bets[c_id].append(bet_info) # type: ignore
                break
    
    for c_id, c_name in contestants.items():
        total_for_contestant = sum(b["amount"] for b in contestant_bets[c_id])
        num_bettors = len(contestant_bets[c_id])
        
        # NEW: Add contestant bet bar
        bet_bar = _generate_bet_progress_bar(total_for_contestant, total_pot)
        summary += f"> {CONTESTANT_EMOJIS[int(c_id)-1]} **{c_name}:** `{total_for_contestant}` coins from `{num_bettors}` bettors [{bet_bar}]\n"

    if not bets:
        # Only show "No bets placed yet." if the betting round is open
        if data["betting"]["open"]:
            summary += MSG_NO_BETS_PLACED_YET + "\n" # Moved this here to appear after total pot if 0

    if include_reaction_info and data["betting"]["open"]:
        reaction_options_text = "\n**Place your bet using reactions:**\n"
        c1_emojis = data["contestant_1_emojis"]
        c2_emojis = data["contestant_2_emojis"]
        reaction_bet_amounts = data["reaction_bet_amounts"]

        # Display C1 options
        reaction_options_text += f"{CONTESTANT_EMOJIS[0]} {contestants.get('1', 'Contestant 1')}: "
        reaction_options_text += " ".join([f"{emoji} `{reaction_bet_amounts.get(emoji, 0)}`" for emoji in c1_emojis])
        reaction_options_text += "\n"

        # Display C2 options
        reaction_options_text += f"{CONTESTANT_EMOJIS[1]} {contestants.get('2', 'Contestant 2')}: "
        reaction_options_text += " ".join([f"{emoji} `{reaction_bet_amounts.get(emoji, 0)}`" for emoji in c2_emojis])
        reaction_options_text += "\n"
        summary += reaction_options_text

    return summary

# NEW HELPER: Generate a detailed list of individual user bets
async def _get_detailed_bet_list(bot: discord.Client, data: Data, winnings_info: Optional[Dict[str, int]] = None) -> str:
    """Generates a detailed list of each user's bet, including winnings if provided."""
    bets = data["betting"].get("bets", {})
    contestants = data["betting"].get("contestants", {})

    if not bets:
        return ""

    detailed_list_parts: List[str] = ["\n**Individual Bets:**\n"]
    
    # Sort bets by amount (descending)
    sorted_bets = sorted(bets.items(), key=lambda item: item[1]["amount"], reverse=True)

    for user_id, bet_info in sorted_bets:
        try:
            user = await bot.fetch_user(int(user_id))
            user_name = user.display_name
        except discord.NotFound:
            user_name = f"Unknown User ({user_id})"
        except Exception:
            user_name = f"User ({user_id})"

        contestant_name = bet_info["choice"].capitalize()
        
        # Find the emoji for the chosen contestant
        contestant_emoji = ""
        for c_id, c_name in contestants.items():
            if c_name.lower() == bet_info["choice"]:
                contestant_emoji = CONTESTANT_EMOJIS[int(c_id)-1]
                break

        bet_line = f"> {user_name}: {contestant_emoji} **{contestant_name}** - `{bet_info['amount']}` coins"
        if winnings_info and user_id in winnings_info:
            bet_line += f" (Won: `{winnings_info[user_id]}` coins)"
        detailed_list_parts.append(f"{bet_line}\n") # type: ignore
    
    return "".join(detailed_list_parts)


async def update_live_message(bot: discord.Client, data: Data,
                              betting_closed: bool = False, close_summary: Optional[str] = None,
                              winner_declared: bool = False, winner_name: Optional[str] = None,
                              current_time: Optional[float] = None, winnings_info: Optional[Dict[str, int]] = None) -> None:
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

    contestants = data["betting"].get("contestants", {})
    bets = data["betting"].get("bets", {})
    open_bet = data["betting"]["open"]
    locked_bet = data["betting"]["locked"]

    # Always calculate timer info internally if enabled and bet is open
    current_remaining_time: Optional[int] = None
    current_total_duration: Optional[int] = None

    if data["settings"]["enable_bet_timer"] and open_bet and data.get("timer_end_time") is not None:
        timer_end_time_val = cast(float, data["timer_end_time"])
        # Use passed current_time or get a fresh one if not provided
        actual_current_time = current_time if current_time is not None else time.time()
        current_remaining_time = int(timer_end_time_val - actual_current_time)
        if current_remaining_time < 0:
            current_remaining_time = 0 # Ensure it doesn't go negative
        current_total_duration = BET_TIMER_DURATION # Assuming BET_TIMER_DURATION is the total duration

    embed_title = TITLE_LIVE_BETTING_ROUND
    embed_color = COLOR_GOLD

    description_parts: List[str] = []

    if winner_declared and winner_name:
        embed_title = f"🏆 {winner_name} Wins! - Final Results"
        embed_color = COLOR_GOLD
        description_parts.append(f"**{winner_name}** has been declared the winner!\n\n")
        description_parts.append(_get_condensed_bet_summary(data)) # Show final bets
        description_parts.append(await _get_detailed_bet_list(bot, data, winnings_info=winnings_info)) # NEW: Add detailed bet list with winnings
        description_parts.append("\nBalances have been updated.")
    elif betting_closed and close_summary:
        embed_title = TITLE_BETS_LOCKED
        embed_color = COLOR_DARK_ORANGE
        if contestants:
            description_parts.append(f"**Contestants:**\n> {CONTESTANT_EMOJIS[0]} **{contestants.get('1', 'Contestant 1')}**\n> {CONTESTANT_EMOJIS[1]} **{contestants.get('2', 'Contestant 2')}**\n\n")
        description_parts.append(close_summary)
        description_parts.append("\n\n")
        description_parts.append(_get_condensed_bet_summary(data))
        description_parts.append(await _get_detailed_bet_list(bot, data)) # NEW: Add detailed bet list
    elif open_bet:
        if contestants:
            description_parts.append(f"**Contestants:**\n> {CONTESTANT_EMOJIS[0]} **{contestants.get('1', 'Contestant 1')}**\n> {CONTESTANT_EMOJIS[1]} **{contestants.get('2', 'Contestant 2')}**\n\n")
        
        if current_remaining_time is not None and current_total_duration is not None and data["settings"]["enable_bet_timer"]:
            description_parts.append(_generate_timer_display(current_remaining_time, current_total_duration))
            description_parts.append("\n\n")
        
        description_parts.append(_get_condensed_bet_summary(data, include_reaction_info=True))
        description_parts.append(f"\n\n{MSG_PLACE_MANUAL_BET_INSTRUCTIONS}")
        description_parts.append(await _get_detailed_bet_list(bot, data)) # NEW: Add detailed bet list
    elif locked_bet:
        embed_title = TITLE_BETS_LOCKED
        embed_color = COLOR_DARK_ORANGE
        if contestants:
            description_parts.append(f"**Contestants:**\n> {CONTESTANT_EMOJIS[0]} **{contestants.get('1', 'Contestant 1')}**\n> {CONTESTANT_EMOJIS[1]} **{contestants.get('2', 'Contestant 2')}**\n\n")
        description_parts.append(f"{MSG_BET_LOCKED_NO_NEW_BETS}\n{MSG_A_WINNER_DECLARED_SOON}\n\n")
        description_parts.append(_get_condensed_bet_summary(data))
        description_parts.append(await _get_detailed_bet_list(bot, data)) # NEW: Add detailed bet list
    else: # No active bet
        embed_title = TITLE_NO_ACTIVE_BETTING_ROUND
        embed_color = COLOR_DARK_GRAY
        description_parts.append(f"{MSG_NO_ACTIVE_BET}.\n\n")
        description_parts.append(MSG_WAIT_FOR_ADMIN_TO_START)

    new_embed = discord.Embed(
        title=embed_title,
        description="".join(description_parts),
        color=embed_color
    )

    for msg_id, chan_id in messages_to_update:
        if msg_id and chan_id:
            channel = bot.get_channel(chan_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(msg_id)
                    await message.edit(embed=new_embed)
                except discord.NotFound:
                    print(f"Live message {msg_id} not found in channel {chan_id}. Clearing info.")
                    if msg_id == main_msg_id:
                        data[LIVE_MESSAGE_KEY] = None
                        data[LIVE_CHANNEL_KEY] = None
                    elif msg_id == secondary_msg_id:
                        data[LIVE_SECONDARY_KEY] = None
                        data[LIVE_SECONDARY_CHANNEL_KEY] = None
                    save_data(data)
                except discord.HTTPException as e:
                    print(f"Error updating live message {msg_id} in channel {chan_id}: {e}")