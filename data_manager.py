import json
import os
from typing import Dict, Any, TypedDict, Optional, List, Tuple  # Added List for clarity
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


# Multi-session support (Phase 1 - Data Structure)
class SessionStatus:
    OPEN = "open"
    LOCKED = "locked"
    COMPLETED = "completed"
    EXPIRED = "expired"


class TimerConfig(TypedDict):
    enabled: bool  # Whether timer is active
    duration: int  # Timer duration in seconds
    lock_duration: Optional[int]  # Seconds until auto-lock
    close_duration: Optional[int]  # Seconds until auto-close
    update_interval: int  # Live message update frequency
    auto_lock_at: Optional[float]  # Specific timestamp to lock
    auto_close_at: Optional[float]  # Specific timestamp to close


class MultiBettingSession(TypedDict):
    # Identity
    id: str  # Format: "{timestamp}_{random}"
    title: str  # User-friendly display name

    # Metadata
    created_at: float  # Unix timestamp
    creator_id: int  # Discord user ID
    channel_id: int  # Origin channel ID

    # Timing
    timer_config: TimerConfig  # Timing configuration
    lock_time: Optional[float]  # When session will/did lock
    close_time: Optional[float]  # When session will/did close

    # State
    status: str  # Current session status (use SessionStatus constants)
    contestants: Dict[str, str]  # contestant_key -> display_name
    bets: Dict[str, UserBet]  # user_id -> bet_info

    # Live messaging
    live_message_id: Optional[int]  # Dedicated live message
    last_update: float  # Last live message update

    # Analytics (cached for performance)
    total_pot: int  # Cached total pot value
    total_bettors: int  # Cached bettor count
    winner: Optional[str]  # Winner if completed

    # Closure metadata
    closed_at: Optional[float]  # Unix timestamp when closed
    closed_by: Optional[str]  # User ID who closed the session


class Data(TypedDict):
    balances: Dict[str, int]
    betting: BettingSession  # Legacy single session (backwards compatibility)
    settings: Dict[str, Any]
    reaction_bet_amounts: Dict[str, int]
    contestant_1_emojis: List[str]
    contestant_2_emojis: List[str]
    live_message: Optional[int]
    live_channel: Optional[int]
    live_secondary_message: Optional[int]
    live_secondary_channel: Optional[int]
    timer_end_time: Optional[float]  # Legacy timer

    # Multi-session support (Phase 1 - New fields)
    betting_sessions: Dict[str, MultiBettingSession]  # session_id -> session_data
    active_sessions: List[str]  # List of non-completed session IDs
    contestant_to_session: Dict[
        str, str
    ]  # contestant_name -> session_id (for auto-detection)
    multi_session_mode: bool  # Enable multi-session features


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
            # Multi-session support (Phase 1 - Initialize new fields)
            "betting_sessions": {},  # No sessions initially
            "active_sessions": [],  # No active sessions initially
            "contestant_to_session": {},  # No contestant mapping initially
            "multi_session_mode": False,  # Start in legacy single-session mode
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

    # Phase 1: Ensure multi-session fields are initialized
    if "betting_sessions" not in data:
        data["betting_sessions"] = {}
        modified = True
    if "active_sessions" not in data:
        data["active_sessions"] = []
        modified = True
    if "contestant_to_session" not in data:
        data["contestant_to_session"] = {}
        modified = True
    if "multi_session_mode" not in data:
        data["multi_session_mode"] = (
            False  # Start in legacy mode for existing installations
        )
        modified = True

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


# ---------- Multi-Session Support Functions (Phase 1) ----------


def is_multi_session_mode(data: Data) -> bool:
    """Check if multi-session mode is enabled."""
    return data.get("multi_session_mode", False)


def get_active_sessions(data: Data) -> Dict[str, MultiBettingSession]:
    """Get all active betting sessions."""
    sessions = {}
    for session_id in data.get("active_sessions", []):
        if session_id in data.get("betting_sessions", {}):
            sessions[session_id] = data["betting_sessions"][session_id]
    return sessions


def find_session_by_contestant(
    contestant_name: str, data: Data
) -> Optional[Tuple[str, str, str]]:
    """Find session containing the specified contestant.

    Returns:
        Tuple of (session_id, contestant_key, contestant_display_name) if found, None otherwise
    """

    # Direct mapping lookup (fastest)
    contestant_mapping = data.get("contestant_to_session", {})
    lower_name = contestant_name.lower()
    if lower_name in contestant_mapping:
        session_id = contestant_mapping[lower_name]
        # Verify session is still active
        if session_id in data.get("active_sessions", []):
            session = data.get("betting_sessions", {}).get(session_id)
            if session and session.get("contestants"):
                # Find the contestant key and display name
                for contestant_key, contestant_display in session[
                    "contestants"
                ].items():
                    if contestant_display.lower() == lower_name:
                        return (session_id, contestant_key, contestant_display)

    # Fallback: Search through all active sessions (case-insensitive, partial match)
    for session_id in data.get("active_sessions", []):
        session = data.get("betting_sessions", {}).get(session_id)
        if not session or not session.get("contestants"):
            continue

        # Check all contestants in session
        for contestant_key, contestant_display in session["contestants"].items():
            if _is_contestant_match(contestant_name, contestant_display):
                # Update mapping for future lookups
                data["contestant_to_session"][contestant_display.lower()] = session_id
                return (session_id, contestant_key, contestant_display)

    return None


def _is_contestant_match(input_name: str, contestant_name: str) -> bool:
    """Check if input matches contestant name (case-insensitive, partial match)."""
    input_lower = input_name.lower().strip()
    contestant_lower = contestant_name.lower().strip()

    # Exact match
    if input_lower == contestant_lower:
        return True

    # Partial match (input is substring of contestant name)
    if len(input_lower) >= 3 and input_lower in contestant_lower:
        return True

    # Handle common abbreviations (first 3+ characters)
    if len(input_lower) >= 3 and contestant_lower.startswith(input_lower):
        return True

    return False


# ---------- Betting storage accessors (canonical accessors) ----------
def get_bets(data: Data, session_id: Optional[str] = None) -> Dict[str, UserBet]:
    """Return the bets dict for the given session_id (multi-session) or the
    legacy betting dict when session_id is None or multi-session mode is not
    used. This returns the live dict reference so callers can read/iterate
    without copying.
    """
    if session_id and data.get("betting_sessions") and session_id in data["betting_sessions"]:
        return data["betting_sessions"][session_id].get("bets", {})

    # Fallback to legacy single-session bets
    return data["betting"].get("bets", {})


def set_bet(data: Data, session_id: Optional[str], user_id: str, bet_info: UserBet) -> None:
    """Set or update a bet for a user in the given session (or legacy). Persists
    changes to disk via save_data.
    """
    if session_id and data.get("betting_sessions") and session_id in data["betting_sessions"]:
        session = data["betting_sessions"][session_id]
        session.setdefault("bets", {})
        session["bets"][user_id] = bet_info
        save_data(data)
        return

    # Legacy
    data["betting"].setdefault("bets", {})
    data["betting"]["bets"][user_id] = bet_info
    save_data(data)


def remove_bet(data: Data, session_id: Optional[str], user_id: str) -> None:
    """Remove a user's bet from the specified session or legacy storage and
    persist changes. No error if not present.
    """
    if session_id and data.get("betting_sessions") and session_id in data["betting_sessions"]:
        session = data["betting_sessions"][session_id]
        if "bets" in session and user_id in session["bets"]:
            del session["bets"][user_id]
            save_data(data)
        return

    if "bets" in data["betting"] and user_id in data["betting"]["bets"]:
        del data["betting"]["bets"][user_id]
        save_data(data)


def get_user_bets_across_sessions(data: Data, user_id: str) -> Dict[str, Tuple[str, UserBet]]:
    """Get all bets for a user across all active sessions.
    
    Returns a dict mapping session_id to (session_title, bet_info) for sessions
    where the user has placed a bet.
    """
    user_bets = {}
    
    # Check multi-session bets
    if is_multi_session_mode(data):
        for session_id in data.get("active_sessions", []):
            session = data.get("betting_sessions", {}).get(session_id)
            if session and session.get("status") == "open":
                bets = session.get("bets", {})
                if user_id in bets:
                    user_bets[session_id] = (session.get("title", f"Session {session_id}"), bets[user_id])
    
    # Also check legacy single-session bets (for backwards compatibility)
    legacy_bets = data.get("betting", {}).get("bets", {})
    if user_id in legacy_bets and data.get("betting", {}).get("open", False):
        user_bets["legacy"] = ("Legacy Session", legacy_bets[user_id])
    
    return user_bets
