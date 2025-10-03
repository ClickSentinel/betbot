from data_manager import Data, save_data, ensure_user
from config import (
    COLOR_ERROR,
    BET_TIMER_DURATION,
    TITLE_BETTING_ERROR,
    MSG_BET_ALREADY_OPEN,
    MSG_BET_LOCKED,
)
from typing import Dict, Optional, TypedDict, cast, Any, List, Literal
from discord.ext import commands
import discord
import time

# Type definitions (moved from message_types.py)


class BetInfo(TypedDict):
    amount: int
    choice: str
    emoji: Optional[str]


class UserResult(TypedDict):
    winnings: int  # Amount won (0 for losers)
    bet_amount: int  # Original bet amount
    new_balance: int  # Final balance after round
    net_change: int  # Positive for winners, negative for losers


class WinnerInfo(TypedDict):
    name: str
    total_pot: int
    winning_pot: int  # Total amount bet on winner
    user_results: Dict[str, UserResult]  # User ID to their result


class BettingSession(TypedDict):
    open: bool
    locked: bool
    contestants: Dict[str, str]
    bets: Dict[str, BetInfo]


class BetUIState(TypedDict):
    bet_session: BettingSession
    emoji_config: Dict[str, List[str]]
    reaction_amounts: Dict[str, int]
    timer_info: Optional["TimerInfo"]
    winner_info: Optional[WinnerInfo]


class TimerInfo(TypedDict):
    remaining: int
    total: int


TransactionType = Literal["add", "remove", "set"]


class Economy:
    """Centralized economy management."""

    def __init__(self, data: Data):
        self.data = data

    def get_balance(self, user_id: str) -> int:
        """Get a user's current balance, ensuring they exist in the system."""
        ensure_user(self.data, user_id)
        return self.data["balances"][user_id]

    def add_balance(self, user_id: str, amount: int) -> bool:
        """Add to a user's balance. Returns True if successful."""
        if amount < 0:
            return False
        ensure_user(self.data, user_id)
        self.data["balances"][user_id] += amount
        save_data(self.data)
        return True

    def remove_balance(self, user_id: str, amount: int) -> bool:
        """Remove from a user's balance. Returns False if insufficient funds."""
        if amount < 0:
            return False
        ensure_user(self.data, user_id)
        if self.data["balances"][user_id] < amount:
            return False
        self.data["balances"][user_id] -= amount
        save_data(self.data)
        return True

    def set_balance(self, user_id: str, amount: int) -> bool:
        """Set a user's balance to a specific amount."""
        if amount < 0:
            return False
        ensure_user(self.data, user_id)
        self.data["balances"][user_id] = amount
        save_data(self.data)
        return True

    def transfer_balance(self, from_user: str, to_user: str, amount: int) -> bool:
        """Transfer balance between users. Returns False if insufficient funds."""
        if amount < 0:
            return False
        if not self.remove_balance(from_user, amount):
            return False
        self.add_balance(to_user, amount)
        return True

    def process_bet_results(self, results: Dict[str, Any]) -> None:
        """Process bet results and update balances accordingly."""
        user_results = results["user_results"]

        # For winners, add their winnings (bet was already deducted)
        for user_id, result in user_results.items():
            current_balance = self.get_balance(user_id)
            new_balance = current_balance + (
                result["winnings"] if result["winnings"] > 0 else 0
            )
            self.set_balance(user_id, new_balance)

        # Save changes
        save_data(self.data)

    def process_bet_placement(
        self, user_id: str, new_amount: int, old_amount: int = 0
    ) -> bool:
        """Process a bet placement, handling refunds and deductions.

        Args:
            user_id: The ID of the user placing the bet
            new_amount: The amount of the new bet
            old_amount: The amount of any previous bet to refund (default 0)

        Returns:
            True if successful, False if insufficient funds
        """
        current_balance = self.get_balance(user_id)
        required_amount = new_amount - old_amount

        if required_amount > current_balance:
            return False

        # If there was a previous bet, refund it
        if old_amount > 0:
            self.add_balance(user_id, old_amount)

        # Deduct the new bet amount
        self.remove_balance(user_id, new_amount)
        return True


class BetState:
    """Encapsulates all betting state management."""

    def __init__(self, data: Data):
        self.data = data
        self.economy = Economy(data)

    def get_betting_session(self) -> BettingSession:
        """Get current betting session state."""
        return {
            "contestants": self.contestants,
            "bets": self.bets,
            "open": self.is_open,
            "locked": self.is_locked,
        }

    def get_emoji_config(self) -> Dict[str, List[str]]:
        return {
            "contestant_1_emojis": self.data.get("contestant_1_emojis", []),
            "contestant_2_emojis": self.data.get("contestant_2_emojis", []),
        }

    def get_reaction_amounts(self) -> Dict[str, int]:
        return self.data.get("reaction_bet_amounts", {})

    @property
    def is_open(self) -> bool:
        return self.data["betting"]["open"]

    @property
    def is_locked(self) -> bool:
        return self.data["betting"]["locked"]

    @property
    def has_active_timer(self) -> bool:
        return self.data.get("timer_end_time") is not None

    @property
    def contestants(self) -> Dict[str, str]:
        return self.data["betting"].get("contestants", {})

    @property
    def bets(self) -> Dict[str, BetInfo]:
        return self.data["betting"].get("bets", {})

    def calculate_round_results(self, winner_name: Optional[str]) -> Dict[str, Any]:
        """Calculate all results for a betting round.

        Args:
            winner_name: Name of the winning contestant, or None if pot is lost

        Returns:
            Dictionary containing all round calculations:
            - total_pot: Total amount of all bets
            - winning_pot: Total amount bet on winner
            - bets_on_winner: Number of bets on winner
            - user_results: Dict of user results including winnings and balances
            - winning_users: List of user IDs who won
            - losing_users: List of user IDs who lost
        """
        # Calculate pot totals
        total_pot = sum(bet["amount"] for bet in self.bets.values())

        # Initialize results
        user_results: Dict[str, UserResult] = {}
        winning_users: List[str] = []
        losing_users: List[str] = []

        if not winner_name:  # Pot is lost
            winning_pot = 0
            bets_on_winner = 0

            # Everyone loses their bets (which were already deducted)
            for user_id, bet_info in self.bets.items():
                bet_amount = bet_info["amount"]
                current_balance = self.economy.get_balance(user_id)

                user_results[user_id] = {
                    "winnings": 0,
                    "bet_amount": bet_amount,
                    "new_balance": current_balance,  # No change needed, bet already deducted
                    "net_change": -bet_amount,  # They lost their bet
                }
                losing_users.append(user_id)

        else:  # We have a winner
            winner_name_lower = winner_name.lower()

            # Calculate winning pot and count winning bets
            winning_pot = sum(
                bet["amount"]
                for bet in self.bets.values()
                if bet["choice"].lower() == winner_name_lower
            )

            bets_on_winner = sum(
                1
                for bet in self.bets.values()
                if bet["choice"].lower() == winner_name_lower
            )

            # Calculate individual results
            for user_id, bet_info in self.bets.items():
                bet_amount = bet_info["amount"]
                current_balance = self.economy.get_balance(user_id)
                is_winner = bet_info["choice"].lower() == winner_name_lower

                if is_winner and winning_pot > 0:
                    # Calculate winner's share of the total pot
                    winning_amount = int((bet_amount / winning_pot) * total_pot)
                    net_change = winning_amount - bet_amount
                    new_balance = current_balance + winning_amount
                    winning_users.append(user_id)
                else:
                    winning_amount = 0
                    net_change = -bet_amount
                    new_balance = current_balance
                    losing_users.append(user_id)

                user_results[user_id] = {
                    "winnings": winning_amount,
                    "bet_amount": bet_amount,
                    "new_balance": new_balance,
                    "net_change": net_change,
                }

        return {
            "total_pot": total_pot,
            "winning_pot": winning_pot,
            "bets_on_winner": bets_on_winner,
            "user_results": user_results,
            "winning_users": winning_users,
            "losing_users": losing_users,
        }

    def get_total_pot(self) -> int:
        """Calculate the total pot from all bets."""
        return sum(bet["amount"] for bet in self.bets.values())

    def get_contestant_totals(self) -> Dict[str, int]:
        """Calculate total bets per contestant."""
        totals = {contestant_id: 0 for contestant_id in self.contestants.keys()}
        for bet in self.bets.values():
            for c_id, c_name in self.contestants.items():
                if bet["choice"] == c_name.lower():
                    totals[c_id] += bet["amount"]
                    break
        return totals

    def get_user_bet(self, user_id: str) -> Optional[BetInfo]:
        """Get a specific user's bet."""
        return self.bets.get(user_id)

    def clear_timer(self) -> None:
        """Clear the betting timer."""
        self.data["timer_end_time"] = None
        save_data(self.data)

    def start_timer(self) -> None:
        """Start a new betting timer."""
        if self.data["settings"]["enable_bet_timer"]:
            self.data["timer_end_time"] = time.time() + BET_TIMER_DURATION
            save_data(self.data)

    def get_remaining_time(self) -> Optional[int]:
        """Get remaining time on the timer, if any."""
        if self.has_active_timer:
            timer_end = cast(float, self.data["timer_end_time"])
            remaining = int(timer_end - time.time())
            return max(0, remaining)
        return None

    async def open_betting_round(
        self, ctx: commands.Context, name1: str, name2: str
    ) -> bool:
        """Opens a new betting round."""
        if self.is_open:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_BET_ALREADY_OPEN, COLOR_ERROR
            )
            return False
        if self.is_locked:
            await self._send_embed(
                ctx, TITLE_BETTING_ERROR, MSG_BET_LOCKED, COLOR_ERROR
            )
            return False

        self.data["betting"] = {
            "open": True,
            "locked": False,
            "bets": {},
            "contestants": {"1": name1, "2": name2},
        }
        save_data(self.data)
        return True

    def place_bet(
        self, user_id: str, amount: int, choice: str, emoji: Optional[str] = None
    ) -> bool:
        """Places or updates a bet for a user."""
        if not self.is_open or self.is_locked:
            return False

        # Get the old bet amount for refund calculation
        old_amount = self.bets.get(user_id, {}).get("amount", 0)

        # Process the bet through the economy system (handles validation and
        # balance updates)
        if not self.economy.process_bet_placement(user_id, amount, old_amount):
            return False

        # Record the new bet
        self.data["betting"]["bets"][user_id] = {
            "amount": amount,
            "choice": choice.lower(),
            "emoji": emoji,
        }
        save_data(self.data)
        return True

    def lock_bets(self) -> None:
        """Lock the current betting round."""
        self.data["betting"]["open"] = False
        self.data["betting"]["locked"] = True
        self.clear_timer()
        save_data(self.data)

    def declare_winner(self, winner_name: Optional[str]) -> WinnerInfo:
        """Declare a winner for the betting round.

        Args:
            winner_name: Name of the winner, or None if the pot is lost

        Returns:
            WinnerInfo containing the results
        """
        # Calculate round results
        results = self.calculate_round_results(winner_name)

        # Process results through the economy system
        self.economy.process_bet_results(results)

        # Reset betting state
        self.data["betting"] = {
            "open": False,
            "locked": False,
            "bets": {},
            "contestants": {},
        }
        save_data(self.data)

        return {
            "name": winner_name if winner_name else "",
            "total_pot": results["total_pot"],
            "winning_pot": results["winning_pot"],
            "user_results": results["user_results"],
        }

    async def _send_embed(
        self, ctx: commands.Context, title: str, description: str, color: discord.Color
    ) -> None:
        """Helper to send consistent embed messages."""
        embed = discord.Embed(title=title, description=description, color=color)
        await ctx.send(embed=embed)
