import discord
from discord.ext import commands
from typing import Dict, Optional, List, Any
import time
import math

from .bet_state import BetUIState, WinnerInfo, TimerInfo
from .bet_state import BetState
from config import (
    TITLE_LIVE_BETTING_ROUND,
    TITLE_BETTING_LOCKED_OVERVIEW,
    TITLE_NO_ACTIVE_BETTING_ROUND,
    TITLE_POT_LOST,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_ERROR,
    BET_TIMER_DURATION
)


class BetUI:
    """Unified UI handling for betting interactions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _format_bet_list(self, state: BetUIState, show_detailed: bool = True) -> str:
        """Format the list of current bets."""
        if not state["bet_session"]["bets"]:
            return "No bets placed yet."

        total_pot = sum(bet["amount"] for bet in state["bet_session"]["bets"].values())
        lines = [f"Total Pot: {total_pot} coins"]

        # Group bets by contestant
        bets_by_contestant: Dict[str, List[Dict[str, Any]]] = {}
        for user_id, bet in state["bet_session"]["bets"].items():
            if bet["choice"] not in bets_by_contestant:
                bets_by_contestant[bet["choice"]] = []
            bets_by_contestant[bet["choice"]].append({
                "user_id": user_id,
                "amount": bet["amount"],
                "emoji": bet["emoji"]
            })

        # Format each contestant's bets
        for contestant in state["bet_session"]["contestants"].values():
            contestant_bets = bets_by_contestant.get(contestant.lower(), [])
            if contestant_bets:
                total = sum(b["amount"] for b in contestant_bets)
                lines.append(f"\n**{contestant}** - Total: {total} coins")
                if show_detailed:
                    for bet in sorted(contestant_bets, key=lambda x: x["amount"], reverse=True):
                        user = self.bot.get_user(int(bet["user_id"]))
                        username = user.display_name if user else "Unknown User"
                        emoji = bet["emoji"] or ""
                        lines.append(f"・{username}: {bet['amount']} coins {emoji}")

        return "\n".join(lines)

    def _format_timer(self, timer_info: Optional[TimerInfo]) -> str:
        """Format timer information."""
        if not timer_info:
            return ""

        remaining = timer_info["remaining"]
        total = timer_info["total"]
        progress = 1 - (remaining / total)
        bar_length = 20
        filled = math.floor(bar_length * progress)
        empty = bar_length - filled

        progress_bar = "█" * filled + "░" * empty
        minutes = remaining // 60
        seconds = remaining % 60
        
        return f"\nTime Remaining: {minutes:02d}:{seconds:02d}\n{progress_bar}"

    def _format_winner_section(self, winner_info: WinnerInfo) -> str:
        """Format the winner section of messages."""
        lines = []
        total_pot = winner_info["total_pot"]
        
        if not winner_info["name"]:
            lines.append(f"Total Pot: {total_pot} coins was lost!")
            return "\n".join(lines)
            
        lines.append(f"**{winner_info['name']}** is the Winner!")
        lines.append(f"Total Pot: {total_pot} coins")
        
        # Add winner details
        for user_id, result in winner_info["user_results"].items():
            if result["winnings"] > 0:
                user = self.bot.get_user(int(user_id))
                username = user.display_name if user else "Unknown User"
                lines.append(f"・{username} won {result['winnings']} coins!")
                
        return "\n".join(lines)

    async def update_live_message(
        self,
        bet_state: BetState,
        betting_closed: bool = False,
        winner_info: Optional[WinnerInfo] = None
    ) -> None:
        """Update the live betting message."""
        # Get message and channel IDs
        msg_id = bet_state.data.get("live_message")
        chan_id = bet_state.data.get("live_channel")
        if not (msg_id and chan_id):
            return

        # Get channel and message
        channel = self.bot.get_channel(chan_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
            
        try:
            message = await channel.fetch_message(msg_id)
        except discord.NotFound:
            return

        # Build UI state
        ui_state: BetUIState = {
            "bet_session": bet_state.get_betting_session(),
            "emoji_config": bet_state.get_emoji_config(),
            "reaction_amounts": bet_state.get_reaction_amounts(),
            "timer_info": {
                "remaining": bet_state.get_remaining_time() or 0,
                "total": BET_TIMER_DURATION
            } if bet_state.has_active_timer else None,
            "winner_info": winner_info
        }

        # Create embed
        embed = discord.Embed(color=COLOR_INFO)
        
        if not ui_state["bet_session"]["open"]:
            embed.title = TITLE_NO_ACTIVE_BETTING_ROUND
            embed.description = "No active betting round. Use !openbet to start one."
            
        elif betting_closed:
            embed.title = TITLE_BETTING_LOCKED_OVERVIEW
            if winner_info:
                if winner_info["name"]:
                    embed.color = COLOR_SUCCESS
                else:
                    embed.title = TITLE_POT_LOST
                    embed.color = COLOR_ERROR
                embed.description = self._format_winner_section(winner_info)
            else:
                embed.description = self._format_bet_list(ui_state)
                
        else:
            embed.title = TITLE_LIVE_BETTING_ROUND
            embed.description = (
                f"**Betting on:** {' vs '.join(ui_state['bet_session']['contestants'].values())}\n\n"
                + self._format_bet_list(ui_state)
            )
            
            if ui_state["timer_info"]:
                embed.description += self._format_timer(ui_state["timer_info"])

        await message.edit(embed=embed)