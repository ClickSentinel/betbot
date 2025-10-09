import pytest
from data_manager import get_bets, set_bet, remove_bet


def test_get_set_remove_bets(test_data):
    # Prepare an empty session in multi-session mode
    test_data["betting_sessions"] = {"s1": {"bets": {}, "contestants": {}}}
    test_data["active_sessions"] = ["s1"]
    test_data["multi_session_mode"] = True

    # Initially no bets
    bets = get_bets(test_data, "s1")
    assert bets == {}

    # Set a bet
    set_bet(test_data, "s1", "u1", {"amount": 100, "choice": "alice", "emoji": None})
    bets = get_bets(test_data, "s1")
    assert "u1" in bets
    assert bets["u1"]["amount"] == 100

    # Remove the bet
    remove_bet(test_data, "s1", "u1")
    bets = get_bets(test_data, "s1")
    assert "u1" not in bets

    # Legacy fallback (no session)
    test_data["multi_session_mode"] = False
    # ensure canonical structure
    test_data["betting"].setdefault("bets", {})
    set_bet(test_data, None, "u2", {"amount": 50, "choice": "bob", "emoji": None})
    bets_legacy = get_bets(test_data)
    assert "u2" in bets_legacy
    remove_bet(test_data, None, "u2")
    assert "u2" not in test_data["betting"]["bets"]
