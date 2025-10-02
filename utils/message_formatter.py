from typing import List, Dict, Optional, Any, Mapping
import discord
import math
import time
from .bet_state import BetInfo, WinnerInfo, BettingSession, TimerInfo
from config import (
    CONTESTANT_EMOJIS,
    MSG_NO_BETS_PLACED_YET,
    MSG_PLACE_MANUAL_BET_INSTRUCTIONS,
    MSG_NO_ACTIVE_BET,
    MSG_WAIT_FOR_ADMIN_TO_START,
    MSG_BET_LOCKED_NO_NEW_BETS,
    MSG_A_WINNER_DECLARED_SOON,
    TITLE_LIVE_BETTING_ROUND,
    TITLE_BETS_LOCKED,
    TITLE_NO_ACTIVE_BETTING_ROUND,
    COLOR_GOLD,
    COLOR_DARK_ORANGE,
    COLOR_DARK_GRAY,
)


class MessageFormatter:
    """Handles formatting of live betting messages."""

    @staticmethod
    def _generate_bet_progress_bar(
        current_amount: int, total_pot: int, bar_length: int = 10
    ) -> str:
        """Generates an enhanced visual progress bar for a contestant's bet proportion."""
        if total_pot == 0:
            return "░" * bar_length

        percentage = (current_amount / total_pot) * 100
        num_blocks = math.ceil(percentage / (100 / bar_length))
        return "▓" * num_blocks + "░" * (bar_length - num_blocks)

    @staticmethod
    def _generate_timer_display(remaining_time: int, total_duration: int) -> str:
        """Generates enhanced timer display with better visual design."""
        display_remaining_time = max(0, remaining_time)
        minutes = display_remaining_time // 60
        seconds = display_remaining_time % 60

        if total_duration <= 0:
            progress_bar = "░░░░░░░░░░"
        else:
            elapsed_time = total_duration - display_remaining_time
            elapsed_percentage = (elapsed_time / total_duration) * 100
            num_blocks = math.floor(elapsed_percentage / 10)
            progress_bar = "▓" * num_blocks + "░" * (10 - num_blocks)

        # Enhanced timer with more prominent display
        if display_remaining_time > 60:
            time_icon = "⏰"
        elif display_remaining_time > 30:
            time_icon = "⚠️"
        else:
            time_icon = "🚨"
            
        return f"{time_icon} **{minutes:02d}:{seconds:02d}** remaining  [{progress_bar}]"

    @staticmethod
    def format_bet_summary(
        contestants: Dict[str, str],
        bets: Mapping[str, BetInfo],
        user_names: Dict[str, str],
        include_reaction_info: bool = False,
        reaction_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Formats the betting summary section."""
        summary = []
        total_pot = sum(bet["amount"] for bet in bets.values())

        if total_pot > 0:
            summary.append(f"💰 **{total_pot}** coins total\n\n")

        contestant_bets: Dict[str, List[BetInfo]] = {c_id: [] for c_id in contestants}
        for user_id, bet_info in bets.items():
            for c_id, c_name in contestants.items():
                if bet_info["choice"] == c_name.lower():
                    contestant_bets[c_id].append(bet_info)
                    break

        for c_id, c_name in contestants.items():
            total_for_contestant = sum(b["amount"] for b in contestant_bets[c_id])
            num_bettors = len(contestant_bets[c_id])
            bet_bar = MessageFormatter._generate_bet_progress_bar(
                total_for_contestant, total_pot
            )
            
            # Calculate percentage and average bet
            percentage = (total_for_contestant / total_pot * 100) if total_pot > 0 else 0
            avg_bet = (total_for_contestant // num_bettors) if num_bettors > 0 else 0
            
            # Enhanced contestant display with stats
            summary.append(
                f"{CONTESTANT_EMOJIS[int(c_id)-1]} **{c_name}** ({percentage:.0f}%) {bet_bar} `{total_for_contestant}` coins\n"
            )
            
            if num_bettors > 0:
                summary.append(f"   👥 {num_bettors} bet{'s' if num_bettors != 1 else ''}  •  💵 Avg: `{avg_bet}`")
                
                # Show individual bets in compact format (max 3, then "and X more")
                sorted_bets = sorted(
                    contestant_bets[c_id], key=lambda x: x["amount"], reverse=True
                )
                shown_bets = sorted_bets[:3]
                for bet_info in shown_bets:
                    user_id = next(uid for uid, b in bets.items() if b == bet_info)
                    user_name = user_names.get(user_id, f"Unknown User ({user_id})")
                    summary.append(f"  •  **{user_name}** `{bet_info['amount']}`")
                
                if len(sorted_bets) > 3:
                    summary.append(f"  •  *and {len(sorted_bets) - 3} more...*")
                    
                summary.append("\n")
            
            summary.append("\n")  # Add space between contestants

        if not bets:
            summary.append(MSG_NO_BETS_PLACED_YET + "\n")

        if include_reaction_info and reaction_config:
            summary.extend(
                MessageFormatter.format_reaction_options(
                    contestants, reaction_config["emojis"], reaction_config["amounts"]
                )
            )

        return "".join(summary)

    @staticmethod
    def format_reaction_options(
        contestants: Dict[str, str],
        emoji_config: Dict[str, List[str]],
        amounts: Dict[str, int],
    ) -> List[str]:
        """Formats the reaction betting options section with clear contestant grouping."""
        options = ["\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"]
        options.append("🎯 **Quick Bet:**\n")

        # Group reaction options by contestant for clarity
        for contestant_id in ["1", "2"]:
            emojis = emoji_config.get(f"contestant_{contestant_id}_emojis", [])
            name = contestants.get(contestant_id, f"Contestant {contestant_id}")
            
            if emojis:
                contestant_options = []
                for emoji in emojis:
                    amount = amounts.get(emoji, 0)
                    if amount > 0:
                        contestant_options.append(f"{emoji} `{amount}`")
                
                if contestant_options:
                    # Use the same emoji as shown in the betting summary
                    contestant_emoji = "🔴" if contestant_id == "1" else "🔵"
                    options.append(f"{contestant_emoji} **{name}:** {' '.join(contestant_options)}\n")

        return options

    @staticmethod
    def format_detailed_bet_list(
        bets: Mapping[str, BetInfo],
        user_names: Dict[str, str],
        winnings_info: Optional[Dict[str, int]] = None,
    ) -> str:
        """Formats the detailed list of individual bets."""
        if not bets:
            return ""

        detailed_list = ["\n**Individual Bets:**\n"]
        sorted_bets = sorted(
            bets.items(), key=lambda item: item[1]["amount"], reverse=True
        )

        for user_id, bet_info in sorted_bets:
            user_name = user_names.get(user_id, f"Unknown User ({user_id})")
            bet_line = f"> {user_name}: {bet_info['choice'].capitalize()} - `{bet_info['amount']}` coins"
            if winnings_info and user_id in winnings_info:
                bet_line += f" (Won: `{winnings_info[user_id]}` coins)"
            detailed_list.append(f"{bet_line}\n")

        return "".join(detailed_list)

    @staticmethod
    async def create_live_message_embed(
        betting_session: BettingSession,
        emoji_config: Dict[str, List[str]],
        reaction_amounts: Dict[str, int],
        user_names: Dict[str, str],
        current_time: Optional[float] = None,
        timer_info: Optional[TimerInfo] = None,
        betting_closed: bool = False,
        close_summary: Optional[str] = None,
        winner_info: Optional[WinnerInfo] = None,
    ) -> discord.Embed:
        """Creates an embed for the live betting message based on current state."""
        embed_title = TITLE_LIVE_BETTING_ROUND
        embed_color = COLOR_GOLD
        description_parts: List[str] = []

        if winner_info:
            # Get all user results and calculate totals
            user_results = winner_info.get("user_results", {})
            # Calculate total pot directly from bets
            total_pot = sum(bet["amount"] for bet in betting_session["bets"].values())
            total_bettors = len(betting_session["bets"])

            # Find bets placed on the winning contestant
            bets_on_winner = sum(
                1
                for bet in betting_session["bets"].values()
                if bet["choice"].lower() == winner_info["name"].lower()
            )

            # Calculate winning pot (amount bet on winner)
            winning_pot = sum(
                bet["amount"]
                for bet in betting_session["bets"].values()
                if bet["choice"].lower() == winner_info["name"].lower()
            )

            if bets_on_winner == 0:
                embed_title = f"💸 {winner_info['name']} Wins!"
                description_parts.append(
                    f"# {winner_info['name']} is the Winner!\n\n"
                    f"### 📊 Round Results\n"
                    f"> 💰 Total Pot: `{total_pot}` coins\n"
                    f"> 🎲 Total Bets: `{len(user_results)}`\n"
                    f"> ❌ All bets were on the other contestant\n"
                )
            else:
                embed_title = f"🏆 {winner_info['name']} Wins!"
                description_parts.append(
                    f"# {winner_info['name']} is the winner!\n\n"
                    f"### 📊 Round Results\n"
                    f"> 💰 Total Pot: `{total_pot}` coins\n"
                    f"> 💵 Amount Bet on Winner: `{winning_pot}` coins\n"
                    f"> 🎯 Bets on Winner: `{bets_on_winner}`\n"
                    f"> 🏆 Profitable Bets: `{bets_on_winner}`\n"
                    f"> 👥 Total Players: `{total_bettors}`\n"
                )

            # Show all bets
            description_parts.append("\n### 📈 All Bets\n")
            description_parts.append(
                MessageFormatter.format_bet_summary(
                    betting_session["contestants"], betting_session["bets"], user_names
                )
            )

            # Show results for each user
            description_parts.append("### 💰 Results\n")
            
            # Only count actual discord user bets
            for user_id, bet_info in betting_session["bets"].items():
                # Skip the display name in username that's not a real bet
                if user_id == "0":  # Used for display purposes
                    continue
                    
                user_name = user_names.get(user_id, f"Unknown User ({user_id})")
                bet_amount = bet_info["amount"]
                bet_choice = bet_info["choice"]
                
                if bet_choice.lower() == winner_info["name"].lower():
                    # Winner gets their winnings (total pot)
                    description_parts.append(f"> 🏆 **{user_name}** +`{bet_amount}` coins\n")
                else:
                    description_parts.append(f"> 💸 **{user_name}** -`{bet_amount}` coins\n")

        elif betting_closed and close_summary:
            embed_title = TITLE_BETS_LOCKED
            embed_color = COLOR_DARK_ORANGE
            if betting_session["contestants"]:
                description_parts.append(
                    MessageFormatter._format_contestants_header(
                        betting_session["contestants"]
                    )
                )
            description_parts.append(close_summary)
            description_parts.append("\n\n")
            description_parts.append(
                MessageFormatter.format_bet_summary(
                    betting_session["contestants"], betting_session["bets"], user_names
                )
            )
            description_parts.append(
                MessageFormatter.format_detailed_bet_list(
                    betting_session["bets"], user_names
                )
            )

        elif betting_session["open"]:
            if betting_session["contestants"]:
                description_parts.append(
                    MessageFormatter._format_contestants_header(
                        betting_session["contestants"]
                    )
                )
                # Add update interval info
                description_parts.append("*Live updates every 5 seconds*\n\n")

            if timer_info:
                description_parts.append(
                    MessageFormatter._generate_timer_display(
                        timer_info["remaining"], timer_info["total"]
                    )
                )
                description_parts.append("\n\n")

            description_parts.append(
                MessageFormatter.format_bet_summary(
                    betting_session["contestants"],
                    betting_session["bets"],
                    user_names,
                    include_reaction_info=True,
                    reaction_config={
                        "emojis": emoji_config,
                        "amounts": reaction_amounts,
                    },
                )
            )
            description_parts.append(f"\n📝 **Manual:** `!bet <contestant> <amount>`")

        elif betting_session["locked"]:
            embed_title = TITLE_BETS_LOCKED
            embed_color = COLOR_DARK_ORANGE
            if betting_session["contestants"]:
                description_parts.append(
                    MessageFormatter._format_contestants_header(
                        betting_session["contestants"]
                    )
                )
            description_parts.append(
                f"{MSG_BET_LOCKED_NO_NEW_BETS}\n{MSG_A_WINNER_DECLARED_SOON}\n\n"
            )
            description_parts.append(
                MessageFormatter.format_bet_summary(
                    betting_session["contestants"], betting_session["bets"], user_names
                )
            )
            description_parts.append(
                MessageFormatter.format_detailed_bet_list(
                    betting_session["bets"], user_names
                )
            )

        else:  # No active bet
            embed_title = TITLE_NO_ACTIVE_BETTING_ROUND
            embed_color = COLOR_DARK_GRAY
            description_parts.append(f"{MSG_NO_ACTIVE_BET}.\n\n")
            description_parts.append(MSG_WAIT_FOR_ADMIN_TO_START)

        return discord.Embed(
            title=embed_title, description="".join(description_parts), color=embed_color
        )

    @staticmethod
    def _format_contestants_header(contestants: Dict[str, str]) -> str:
        """Formats the contestants header section with improved visual design."""
        contestant1 = contestants.get('1', 'Contestant 1')
        contestant2 = contestants.get('2', 'Contestant 2')
        return (
            f"# 🏆 **{contestant1.upper()} vs {contestant2.upper()}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
