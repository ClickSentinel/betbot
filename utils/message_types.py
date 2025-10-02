from typing import TypedDict, Optional, Dict, Any, List, Literal


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
    timer_info: Optional['TimerInfo']
    winner_info: Optional[WinnerInfo]


class TimerInfo(TypedDict):
    remaining: int
    total: int


TransactionType = Literal["add", "remove", "set"]
