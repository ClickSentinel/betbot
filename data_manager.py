import json
import os
from typing import Dict, Any, TypedDict, Optional, List  # Added List for clarity
from config import (
    DATA_FILE,
    STARTING_BALANCE,
    ENABLE_BET_TIMER_DEFAULT,
    REACTION_BET_AMOUNTS,
    C1_EMOJIS,
    C2_EMOJIS,
    LIVE_MESSAGE_KEY,
    LIVE_CHANNEL_KEY,
    LIVE_SECONDARY_KEY,
    LIVE_SECONDARY_CHANNEL_KEY,
)


# ---------- Data Schemas ----------
class UserBet(TypedDict):
    choice: str
    amount: int
    emoji: Optional[str]  # Added to store the emoji used for reaction bets


class BettingSession(TypedDict):
    open: bool
    locked: bool
    bets: Dict[str, UserBet]
    contestants: Dict[str, str]


class Data(TypedDict):
    balances: Dict[str, int]
    betting: BettingSession
    settings: Dict[str, Any]
    reaction_bet_amounts: Dict[str, int]
    contestant_1_emojis: List[str]
    contestant_2_emojis: List[str]
    live_message: Optional[int]
    live_channel: Optional[int]
    live_secondary_message: Optional[int]
    live_secondary_channel: Optional[int]
    # New: Add timer_end_time to track when the betting timer will expire
    timer_end_time: Optional[float]


# ---------- Data I/O ----------
def load_data() -> Data:
    file_exists = os.path.exists(DATA_FILE)
    modified = False

    if not file_exists:
        initial_data: Data = {
            "balances": {},
            "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
            "settings": {"enable_bet_timer": ENABLE_BET_TIMER_DEFAULT},
            "reaction_bet_amounts": REACTION_BET_AMOUNTS,
            "contestant_1_emojis": C1_EMOJIS,
            "contestant_2_emojis": C2_EMOJIS,
            LIVE_MESSAGE_KEY: None,  # Use the constant as key
            LIVE_CHANNEL_KEY: None,  # Use the constant as key
            LIVE_SECONDARY_KEY: None,  # Use the constant as key
            LIVE_SECONDARY_CHANNEL_KEY: None,  # Use the constant as key
            "timer_end_time": None,  # Initialize new key
        }
        save_data(initial_data)
        return initial_data

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # --- Migration/Update Logic for existing data.json files ---

    # Ensure 'betting' structure is complete
    if "betting" not in data:
        data["betting"] = {
            "open": False,
            "locked": False,
            "bets": {},
            "contestants": {},
        }
        modified = True
    else:
        if "open" not in data["betting"]:
            data["betting"]["open"] = False
            modified = True
        if "locked" not in data["betting"]:
            data["betting"]["locked"] = False
            modified = True
        if "bets" not in data["betting"]:
            data["betting"]["bets"] = {}
            modified = True
        if "contestants" not in data["betting"]:
            data["betting"]["contestants"] = {}
            modified = True

    if "settings" not in data:
        data["settings"] = {}
        modified = True
    if "enable_bet_timer" not in data["settings"]:
        data["settings"]["enable_bet_timer"] = ENABLE_BET_TIMER_DEFAULT
        modified = True

    # Always overwrite emoji-related data with values from config.py
    if data.get("reaction_bet_amounts") != REACTION_BET_AMOUNTS:
        data["reaction_bet_amounts"] = REACTION_BET_AMOUNTS
        modified = True
    if data.get("contestant_1_emojis") != C1_EMOJIS:
        data["contestant_1_emojis"] = C1_EMOJIS
        modified = True
    if data.get("contestant_2_emojis") != C2_EMOJIS:
        data["contestant_2_emojis"] = C2_EMOJIS
        modified = True

    # Ensure live message keys are present (and initialized to None if missing)
    if LIVE_MESSAGE_KEY not in data:
        data[LIVE_MESSAGE_KEY] = None
        modified = True
    if LIVE_CHANNEL_KEY not in data:
        data[LIVE_CHANNEL_KEY] = None
        modified = True
    if LIVE_SECONDARY_KEY not in data:
        data[LIVE_SECONDARY_KEY] = None
        modified = True
    if LIVE_SECONDARY_CHANNEL_KEY not in data:
        data[LIVE_SECONDARY_CHANNEL_KEY] = None
        modified = True
    data.setdefault("timer_end_time", None)  # Ensure timer_end_time is present

    # Ensure user balances are initialized if missing
    if "balances" not in data:
        data["balances"] = {}
        modified = True
    # This loop ensures existing users in data.json have a balance entry if
    # somehow missing
    for user_id in list(data["balances"].keys()):
        # This condition is technically redundant if "balances" is initialized
        if user_id not in data["balances"]:
            data["balances"][user_id] = STARTING_BALANCE
            modified = True

    if modified:
        print("[data_manager.load_data] Data file migrated/updated. Saving changes.")
        save_data(data)

    return data


def save_data(data: Data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def ensure_user(data: Data, user_id: str):
    if user_id not in data["balances"]:
        data["balances"][user_id] = STARTING_BALANCE
