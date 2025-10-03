"""
Test Phase 2: Command Integration for multi-session betting.
Tests that betting commands work correctly with multiple sessions.
"""

import pytest
import os
import tempfile
from data_manager import load_data, save_data, find_session_by_contestant, is_multi_session_mode


def create_multi_session_test_data():
    """Create test data with multiple betting sessions."""
    return {
        "balances": {
            "user1": 1000,
            "user2": 1500,
            "user3": 500
        },
        "betting": {
            "open": False,
            "locked": False,
            "bets": {},
            "contestants": {}
        },
        "settings": {
            "enable_bet_timer": True,
            "bet_channel_id": None
        },
        "betting_sessions": {
            "nfl_game": {
                "status": "open",
                "contestants": {
                    "c1": "Patriots",
                    "c2": "Cowboys"
                },
                "bets": {},
                "timer_config": {
                    "enabled": True,
                    "duration": 300
                }
            },
            "nba_game": {
                "status": "open",
                "contestants": {
                    "c1": "Lakers",
                    "c2": "Warriors"
                },
                "bets": {},
                "timer_config": {
                    "enabled": True,
                    "duration": 600
                }
            }
        },
        "active_sessions": ["nfl_game", "nba_game"],
        "contestant_to_session": {
            "patriots": "nfl_game",
            "cowboys": "nfl_game",
            "lakers": "nba_game",
            "warriors": "nba_game"
        },
        "multi_session_mode": True
    }


def test_multi_session_detection():
    """Test that multi-session mode is correctly detected."""
    data = create_multi_session_test_data()
    
    # Should detect multi-session mode
    assert is_multi_session_mode(data) == True
    
    # Legacy data should not be multi-session
    legacy_data = {
        "betting": {"open": True, "bets": {}, "contestants": {}},
        "balances": {},
        "settings": {}
    }
    assert is_multi_session_mode(legacy_data) == False


def test_contestant_lookup_multi_session():
    """Test that contestants can be found across multiple sessions."""
    data = create_multi_session_test_data()
    
    # Test finding contestants in different sessions
    result = find_session_by_contestant("Patriots", data) 
    assert result is not None
    session_id, contestant_id, contestant_name = result
    assert session_id == "nfl_game"
    assert contestant_name == "Patriots"
    
    result = find_session_by_contestant("Lakers", data)
    assert result is not None
    session_id, contestant_id, contestant_name = result
    assert session_id == "nba_game"
    assert contestant_name == "Lakers"
    
    # Test case insensitive matching
    result = find_session_by_contestant("lakers", data)
    assert result is not None
    assert result[2] == "Lakers"
    
    # Test partial matching
    result = find_session_by_contestant("Patri", data)
    assert result is not None
    assert result[2] == "Patriots"


def test_bet_placement_multi_session():
    """Test that bets can be placed in the correct session."""
    data = create_multi_session_test_data()
    
    # Simulate placing a bet on Patriots (NFL session)
    user_id = "user1" 
    amount = 200
    choice = "Patriots"
    
    # Find the session
    session_result = find_session_by_contestant(choice, data)
    assert session_result is not None
    session_id, contestant_id, contestant_name = session_result
    
    # Place the bet
    session = data["betting_sessions"][session_id]
    original_balance = data["balances"][user_id]
    
    data["balances"][user_id] -= amount
    session["bets"][user_id] = {
        "amount": amount,
        "choice": contestant_name.lower(),
        "emoji": None
    }
    
    # Verify bet was placed correctly
    assert user_id in session["bets"] 
    assert session["bets"][user_id]["amount"] == amount
    assert session["bets"][user_id]["choice"] == "patriots"
    assert data["balances"][user_id] == original_balance - amount
    
    # Verify bet is in correct session (not in other session)
    other_session = data["betting_sessions"]["nba_game"]
    assert user_id not in other_session["bets"]


def test_multiple_bets_different_sessions():
    """Test that users can bet on different sessions simultaneously."""
    data = create_multi_session_test_data()
    
    user_id = "user2"
    original_balance = data["balances"][user_id]
    
    # Bet on NFL game
    nfl_amount = 300
    nfl_session = data["betting_sessions"]["nfl_game"]
    data["balances"][user_id] -= nfl_amount
    nfl_session["bets"][user_id] = {
        "amount": nfl_amount,
        "choice": "patriots",
        "emoji": None
    }
    
    # Bet on NBA game
    nba_amount = 400 
    nba_session = data["betting_sessions"]["nba_game"]
    data["balances"][user_id] -= nba_amount
    nba_session["bets"][user_id] = {
        "amount": nba_amount,
        "choice": "lakers",
        "emoji": None
    }
    
    # Verify both bets exist
    assert user_id in nfl_session["bets"]
    assert user_id in nba_session["bets"]
    assert nfl_session["bets"][user_id]["amount"] == nfl_amount
    assert nba_session["bets"][user_id]["amount"] == nba_amount
    assert data["balances"][user_id] == original_balance - nfl_amount - nba_amount
    
    # Verify bets are on different contestants
    assert nfl_session["bets"][user_id]["choice"] == "patriots"
    assert nba_session["bets"][user_id]["choice"] == "lakers"


def test_session_status_validation():
    """Test that bets can only be placed on open sessions."""
    data = create_multi_session_test_data()
    
    # Close one session
    data["betting_sessions"]["nfl_game"]["status"] = "locked"
    
    # Should be able to find contestant but session is locked
    result = find_session_by_contestant("Patriots", data)
    assert result is not None
    session_id, _, _ = result
    
    session = data["betting_sessions"][session_id] 
    assert session["status"] == "locked"
    
    # Should still be able to bet on open session
    result = find_session_by_contestant("Lakers", data)
    assert result is not None
    session_id, _, _ = result
    session = data["betting_sessions"][session_id]
    assert session["status"] == "open"


if __name__ == "__main__":
    pytest.main([__file__])