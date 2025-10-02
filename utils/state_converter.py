from typing import Dict, Any, Optional, cast
from .message_types import BetInfo, WinnerInfo, BettingSession, TimerInfo, UserResult
from data_manager import Data
import time

def convert_to_betting_session(data: Data) -> BettingSession:
    """Converts raw data dict to a BettingSession object."""
    betting_data = data["betting"]
    return {
        "contestants": betting_data.get("contestants", {}),
        "bets": betting_data.get("bets", {}),
        "open": betting_data.get("open", False),
        "locked": betting_data.get("locked", False),
    }

def create_winner_info(winner_name: Optional[str], winnings_info: Optional[Dict[str, int]] = None) -> Optional[WinnerInfo]:
    """Legacy function for backward compatibility. Now uses BetState."""
    if not winner_name:
        return None
        
    if winnings_info is None:
        winnings_info = {}

    # Create a minimal bet state with just the necessary data
    from .bet_state import BetState
    from typing import TypedDict, Dict

    class UserBet(TypedDict):
        amount: int
        choice: str
        emoji: Optional[str]

    class BettingState(TypedDict):
        bets: Dict[str, UserBet]
        open: bool
        locked: bool
        contestants: Dict[str, str]

    data: Data = {
        "betting": {
            "bets": {
                user_id: {
                    "amount": abs(winnings) if winnings <= 0 else winnings // 2,
                    "choice": winner_name.lower() if winnings > 0 else "other",
                    "emoji": None
                }
                for user_id, winnings in winnings_info.items()
            },
            "open": False,
            "locked": True,
            "contestants": {}
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
        "timer_end_time": None
    }
    
    # Use the centralized calculation
    bet_state = BetState(data)
    results = bet_state.calculate_round_results(winner_name)
    
    return {
        "name": winner_name,
        "total_pot": results["total_pot"],
        "winning_pot": results["winning_pot"],
        "user_results": results["user_results"]
    }

def create_timer_info(
    current_remaining_time: Optional[int],
    current_total_duration: Optional[int]
) -> Optional[TimerInfo]:
    """Creates a TimerInfo object from timer data."""
    if current_remaining_time is None or current_total_duration is None:
        return None
        
    return {
        "remaining": current_remaining_time,
        "total": current_total_duration
    }

def get_emoji_config(data: Data) -> Dict[str, Any]:
    """Gets reaction emoji configuration from data."""
    return {
        "contestant_1_emojis": data.get("contestant_1_emojis", []),
        "contestant_2_emojis": data.get("contestant_2_emojis", [])
    }

def get_reaction_bet_amounts(data: Data) -> Dict[str, int]:
    """Gets reaction bet amounts configuration from data."""
    return data.get("reaction_bet_amounts", {})