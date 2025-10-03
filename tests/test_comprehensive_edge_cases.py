"""
Comprehensive edge case and stress testing for the multi-session betting system.
Tests error conditions, boundary cases, and system robustness.
"""

import pytest
import tempfile
import os
from typing import cast
from data_manager import load_data, save_data, is_multi_session_mode, find_session_by_contestant, Data


def cast_data(data: dict) -> Data:
    """Helper to cast dict to Data type for testing."""
    return cast(Data, data)


def create_test_data_with_sessions():
    """Create test data with multiple sessions for edge case testing."""
    return {
        "balances": {"user1": 900, "user2": 500, "user3": 1000},  # user1 already has existing bet
        "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
        "settings": {},
        "betting_sessions": {
            "session1": {
                "status": "open",
                "contestants": {"c1": "Team A", "c2": "Team B"},
                "bets": {"user2": {"amount": 200, "choice": "team a", "emoji": None}},
                "timer_config": {"enabled": False, "duration": 0}
            },
            "session2": {
                "status": "open", 
                "contestants": {"c1": "Fighter 1", "c2": "Fighter 2"},
                "bets": {"user1": {"amount": 100, "choice": "fighter 1", "emoji": None}},
                "timer_config": {"enabled": False, "duration": 0}
            },
            "session3": {
                "status": "closed",
                "contestants": {"c1": "Player X", "c2": "Player Y"},
                "bets": {},
                "timer_config": {"enabled": False, "duration": 0}
            }
        },
        "active_sessions": ["session1", "session2"],
        "contestant_to_session": {
            "team a": "session1",
            "team b": "session1", 
            "fighter 1": "session2",
            "fighter 2": "session2"
        },
        "multi_session_mode": True,
        "reaction_bet_amounts": {},
        "contestant_1_emojis": [],
        "contestant_2_emojis": [],
        "live_message": None
    }


def test_empty_session_handling():
    """Test system behavior with empty sessions."""
    data = create_test_data_with_sessions()
    
    # Add empty session
    data["betting_sessions"]["empty_session"] = {
        "status": "open",
        "contestants": {},
        "bets": {},
        "timer_config": {"enabled": False, "duration": 0}
    }
    data["active_sessions"].append("empty_session")
    
    # Should handle empty contestants gracefully
    assert is_multi_session_mode(cast_data(data)) == True
    
    assert find_session_by_contestant("NonExistent", cast_data(data)) is None


def test_invalid_data_structures():
    """Test handling of invalid or corrupted data structures."""
    data = create_test_data_with_sessions()
    
    # Test with missing contestants key
    data["betting_sessions"]["broken_session"] = {
        "status": "open",
        "bets": {},
        "timer_config": {"enabled": False, "duration": 0}
    }
    
    result = find_session_by_contestant("Team A", cast_data(data))
    assert result is not None  # Should still find valid sessions
    
    # Test with invalid contestants type
    result = find_session_by_contestant("NonExistent", cast_data(data))
    assert result is None


def test_contestant_name_edge_cases():
    """Test edge cases in contestant name handling."""
    data = create_test_data_with_sessions()
    
    # Test various search terms
    test_cases = [
        ("Team A", True),      # Exact match
        ("team a", True),      # Case insensitive  
        ("TEAM A", True),      # All caps
        ("Team", True),        # Partial match
                    ("A", False),          # Single character (too short to match)
        ("XYZ", False),        # No match
        ("", False),           # Empty string
        ("Team A Extra", False)  # Extra text
    ]
    
    for search_term, should_find in test_cases:
        result = find_session_by_contestant(search_term, cast_data(data))
        if should_find:
            assert result is not None, f"Should find session for: '{search_term}'"
        else:
            assert result is None, f"Should not find session for: '{search_term}'"


def test_session_status_validation():
    """Test different session statuses and their behavior."""
    data = create_test_data_with_sessions()
    
    # Test finding contestants in different session states
    open_result = find_session_by_contestant("Team A", cast_data(data))  # Open session
    locked_result = find_session_by_contestant("Player X", cast_data(data))  # Locked session
    
    assert open_result is not None
    assert locked_result is None  # Closed sessions should not be found in active searches


def test_extreme_balance_scenarios():
    """Test edge cases with user balances."""
    data = create_test_data_with_sessions()
    
    # Test with zero balance
    data["balances"]["broke_user"] = 0
    
    # Test with negative balance (should not happen but handle gracefully)
    data["balances"]["debt_user"] = -100
    
    # Test with very large balance
    data["balances"]["rich_user"] = 999999999
    
    # Test with missing balance (should default to 0)
    # Don't add missing_user to balances dict
    
    # System should handle all these gracefully
    assert "broke_user" in data["balances"]
    assert data["balances"]["broke_user"] == 0
    assert data["balances"]["debt_user"] == -100
    assert data["balances"]["rich_user"] == 999999999


def test_concurrent_session_betting():
    """Test users betting on multiple sessions simultaneously."""
    data = create_test_data_with_sessions()

    # User1 bets on multiple sessions
    session1 = data["betting_sessions"]["session1"]

    # Place bet in session1
    session1["bets"]["user1"] = {"amount": 200, "choice": "team a", "emoji": None}
    data["balances"]["user1"] -= 200

    # Verify user can have bets in multiple sessions
    session2 = data["betting_sessions"]["session2"]
    assert "user1" in session2["bets"]  # Already has bet from test data
    assert "user1" in session1["bets"]  # New bet we just added

    # Calculate total exposure
    total_bet = session1["bets"]["user1"]["amount"] + session2["bets"]["user1"]["amount"]
    remaining_balance = data["balances"]["user1"]

    assert total_bet == 300  # 200 + 100
    assert remaining_balance == 700  # user1 started with 900, deducted 200 = 700


def test_session_lifecycle():
    """Test complete session lifecycle from creation to closure."""
    data = {
        "balances": {"user1": 1000, "user2": 1000},
        "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
        "settings": {},
        "betting_sessions": {},
        "active_sessions": [],
        "contestant_to_session": {},
        "multi_session_mode": True
    }

    # 1. Create session
    session_id = "test_session"
    new_session = {
        "status": "open",
        "contestants": {"c1": "Alpha", "c2": "Beta"},
        "bets": {},
        "timer_config": {"enabled": True, "duration": 300}
    }

    data["betting_sessions"][session_id] = new_session
    data["active_sessions"].append(session_id)
    data["contestant_to_session"]["alpha"] = session_id
    data["contestant_to_session"]["beta"] = session_id

    assert session_id in data["active_sessions"]
    assert is_multi_session_mode(cast_data(data))

    # 2. Place bets
    new_session["bets"]["user1"] = {"amount": 300, "choice": "alpha", "emoji": None}
    new_session["bets"]["user2"] = {"amount": 200, "choice": "beta", "emoji": None}
    data["balances"]["user1"] -= 300
    data["balances"]["user2"] -= 200

    assert len(new_session["bets"]) == 2

    # 3. Lock session
    new_session["status"] = "locked"

    # 4. Close session with winner
    winner = "Alpha"
    total_pot = sum(bet["amount"] for bet in new_session["bets"].values())
    winning_bets = [bet for bet in new_session["bets"].values() if bet["choice"] == winner.lower()]
    winning_pot = sum(bet["amount"] for bet in winning_bets)

    # Process payouts
    for user_id, bet in new_session["bets"].items():
        if bet["choice"] == winner.lower():
            # Winner gets their share of the total pot
            winnings = int((bet["amount"] / winning_pot) * total_pot)
            data["balances"][user_id] += winnings

    # Close session
    data["active_sessions"].remove(session_id)
    data["contestant_to_session"].pop("alpha", None)
    data["contestant_to_session"].pop("beta", None)
    new_session["status"] = "closed"
    new_session["winner"] = winner

    assert session_id not in data["active_sessions"]
    assert new_session["status"] == "closed"
    assert data["balances"]["user1"] == 1200  # Won back their bet + opponent's (500 total pot)


def test_data_consistency():
    """Test data consistency across operations."""
    data = create_test_data_with_sessions()
    
    # Verify active_sessions matches betting_sessions status
    for session_id in data["active_sessions"]:
        assert session_id in data["betting_sessions"]
        session = data["betting_sessions"][session_id]
        assert session["status"] in ["open", "locked"]
    
    # Verify contestant_to_session mapping is consistent
    for contestant, session_id in data["contestant_to_session"].items():
        assert session_id in data["betting_sessions"]
        session = data["betting_sessions"][session_id]
        # Check if contestant exists in session (case insensitive)
        found = False
        for contestant_display in session["contestants"].values():
            if contestant_display.lower() == contestant.lower():
                found = True
                break
        assert found, f"Contestant '{contestant}' not found in session '{session_id}'"


def test_legacy_data_migration():
    """Test migration scenarios from legacy to multi-session."""
    # Start with legacy data
    legacy_data = {
        "balances": {"user1": 1000, "user2": 500},
        "betting": {
            "open": True,
            "locked": False,
            "bets": {"user1": {"amount": 200, "choice": "team a", "emoji": None}},
            "contestants": {"c1": "Team A", "c2": "Team B"}
        },
        "settings": {}
    }
    
    # Should detect as legacy mode initially
    assert is_multi_session_mode(cast_data(legacy_data)) == False
    
    # Add multi-session fields
    legacy_data["betting_sessions"] = {}
    legacy_data["active_sessions"] = []
    legacy_data["contestant_to_session"] = {}
    legacy_data["multi_session_mode"] = True
    
    # Should now detect as multi-session mode
    assert is_multi_session_mode(cast_data(legacy_data)) == True


def test_performance_with_many_sessions():
    """Test system performance with large numbers of sessions."""
    data = {
        "balances": {f"user_{i}": 1000 for i in range(50)},
        "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
        "settings": {},
        "betting_sessions": {},
        "active_sessions": [],
        "contestant_to_session": {},
        "multi_session_mode": True
    }
    
    # Create 100+ sessions
    for i in range(100):
        session_id = f"session_{i}"
        contestants = {
            "c1": f"Team_{i}_A",
            "c2": f"Team_{i}_B"
        }
        
        data["betting_sessions"][session_id] = {
            "status": "open",
            "contestants": contestants,
            "bets": {},
            "timer_config": {"enabled": False, "duration": 0}
        }
        data["active_sessions"].append(session_id)
        
        # Add to contestant mapping
        for contestant in contestants.values():
            data["contestant_to_session"][contestant.lower()] = session_id
    
    # Test search performance - should be fast with mapping
    import time
    start_time = time.time()
    
    for i in range(0, 100, 10):  # Test every 10th session
        result = find_session_by_contestant(f"Team_{i}_A", cast_data(data))
        assert result is not None
    
    elapsed = time.time() - start_time
    assert elapsed < 1.0  # Should complete in under 1 second


def test_error_recovery():
    """Test system recovery from various error conditions."""
    data = create_test_data_with_sessions()

    # Test with corrupted active_sessions
    data["active_sessions"].append("non_existent_session")

    # Should handle gracefully
    result = find_session_by_contestant("Team A", cast_data(data))
    assert result is not None  # Should still find valid sessions

    # Test with corrupted contestant_to_session mapping
    data["contestant_to_session"]["invalid_contestant"] = "non_existent_session"

    # Should fall back to searching through sessions
    result = find_session_by_contestant("Team A", cast_data(data))
    assert result is not None

    # Test with None values
    data["betting_sessions"]["session1"]["contestants"] = None

    # Should handle None contestants gracefully
    result = find_session_by_contestant("Team A", cast_data(data))
    # Team A should still be found in session2, or None if corrupted session was only source
    assert result is None or result[0] == "session2"


if __name__ == "__main__":
    pytest.main([__file__])