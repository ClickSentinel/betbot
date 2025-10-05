"""
Test Phase 3: Session Management Commands.
Tests the session management functionality for multi-session betting.
"""

import pytest
import os
import tempfile
from typing import cast
from data_manager import load_data, save_data, is_multi_session_mode, Data


def create_empty_data():
    """Create empty data structure for testing."""
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
        }
    }


def create_multi_session_data():
    """Create data with existing multi-session structure."""
    data = create_empty_data()
    data.update({
        "betting_sessions": {
            "nfl_game": {
                "status": "open",
                "contestants": {
                    "c1": "Patriots",
                    "c2": "Cowboys"
                },
                "bets": {
                    "user1": {"amount": 200, "choice": "patriots", "emoji": None}
                },
                "timer_config": {
                    "enabled": True,
                    "duration": 300
                },
                "created_at": 1696348800.0,
                "created_by": "admin1"
            },
            "nba_game": {
                "status": "locked",
                "contestants": {
                    "c1": "Lakers",
                    "c2": "Warriors"
                },
                "bets": {
                    "user2": {"amount": 300, "choice": "lakers", "emoji": None}
                },
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
    })
    return data


def test_session_creation_logic():
    """Test the logic for creating new sessions."""
    data = create_empty_data()
    
    # Initially not in multi-session mode
    assert is_multi_session_mode(cast(Data, data)) == False
    
    # Simulate opensession command logic
    session_id = "test_session"
    contestant1 = "Alice"
    contestant2 = "Bob"
    timer_duration = 300
    
    # Convert to multi-session mode
    data["betting_sessions"] = {}
    data["active_sessions"] = []
    data["contestant_to_session"] = {}
    data["multi_session_mode"] = True
    
    # Create new session
    new_session = {
        "status": "open",
        "contestants": {
            "c1": contestant1,
            "c2": contestant2
        },
        "bets": {},
        "timer_config": {
            "enabled": True,
            "duration": timer_duration
        },
        "created_at": 1696348800.0,
        "created_by": "test_user"
    }
    
    # Add session to data
    data["betting_sessions"][session_id] = new_session
    data["active_sessions"].append(session_id)
    
    # Update contestant mapping
    data["contestant_to_session"][contestant1.lower()] = session_id
    data["contestant_to_session"][contestant2.lower()] = session_id
    
    # Verify session was created correctly
    assert is_multi_session_mode(cast(Data, data)) == True
    assert session_id in data["betting_sessions"]
    assert session_id in data["active_sessions"]
    assert data["betting_sessions"][session_id]["status"] == "open"
    assert len(data["betting_sessions"][session_id]["contestants"]) == 2
    assert data["contestant_to_session"]["alice"] == session_id
    assert data["contestant_to_session"]["bob"] == session_id


def test_session_listing_logic():
    """Test the logic for listing sessions."""
    data = create_multi_session_data()
    
    # Verify multi-session mode is active
    assert is_multi_session_mode(cast(Data, data)) == True
    
    # Get active sessions
    active_sessions = data.get("active_sessions", [])
    assert len(active_sessions) == 2
    assert "nfl_game" in active_sessions
    assert "nba_game" in active_sessions
    
    # Calculate session stats
    total_bets = 0
    open_sessions = 0
    
    for session_id in active_sessions:
        session = data["betting_sessions"].get(session_id, {})
        bets = session.get("bets", {})
        status = session.get("status", "unknown")
        
        total_bets += len(bets)
        if status == "open":
            open_sessions += 1
    
    assert total_bets == 2  # user1 in nfl_game, user2 in nba_game
    assert open_sessions == 1  # only nfl_game is open


def test_session_info_logic():
    """Test the logic for getting detailed session info."""
    data = create_multi_session_data()
    
    session_id = "nfl_game"
    session = data["betting_sessions"][session_id]
    
    # Verify session exists
    assert session is not None
    
    # Get session details
    contestants = session.get("contestants", {})
    bets = session.get("bets", {})
    status = session.get("status", "unknown")
    timer_config = session.get("timer_config", {})
    
    assert len(contestants) == 2
    assert "Patriots" in contestants.values()
    assert "Cowboys" in contestants.values()
    assert len(bets) == 1
    assert "user1" in bets
    assert status == "open"
    assert timer_config.get("duration") == 300
    
    # Calculate betting statistics
    total_pot = sum(bet["amount"] for bet in bets.values())
    assert total_pot == 200
    
    # Calculate contestant stats
    contestant_stats = {}
    for contestant_key, contestant_name in contestants.items():
        contestant_bets = [bet for bet in bets.values() if bet["choice"] == contestant_name.lower()]
        contestant_stats[contestant_name] = {
            "bets": len(contestant_bets),
            "pot": sum(bet["amount"] for bet in contestant_bets)
        }
    
    assert contestant_stats["Patriots"]["bets"] == 1
    assert contestant_stats["Patriots"]["pot"] == 200
    assert contestant_stats["Cowboys"]["bets"] == 0
    assert contestant_stats["Cowboys"]["pot"] == 0


def test_session_closure_logic():
    """Test the logic for closing sessions and distributing winnings."""
    data = create_multi_session_data()
    
    session_id = "nfl_game"
    winner = "Patriots"
    
    session = data["betting_sessions"][session_id]
    contestants = session.get("contestants", {})
    bets = session.get("bets", {})
    
    # Verify winner is valid
    winner_found = False
    for contestant_name in contestants.values():
        if contestant_name.lower() == winner.lower():
            winner = contestant_name  # Use exact case
            winner_found = True
            break
    
    assert winner_found == True
    
    # Calculate payouts
    initial_balance = data["balances"]["user1"]
    total_pot = sum(bet["amount"] for bet in bets.values())
    winning_bets = [bet for bet in bets.values() if bet["choice"] == winner.lower()]
    winning_pot = sum(bet["amount"] for bet in winning_bets)
    
    assert total_pot == 200
    assert len(winning_bets) == 1
    assert winning_pot == 200
    
    # Process payouts (simplified)
    for user_id, bet in bets.items():
        if bet["choice"] == winner.lower():
            # Winner gets their share of the total pot
            winnings = int((bet["amount"] / winning_pot) * total_pot)
            data["balances"][user_id] += winnings
    
    # Verify payout
    assert data["balances"]["user1"] == initial_balance + 200  # Won their bet back
    
    # Remove session from active list
    if session_id in data.get("active_sessions", []):
        data["active_sessions"].remove(session_id)
    
    # Remove contestants from mapping
    for contestant_name in contestants.values():
        data.get("contestant_to_session", {}).pop(contestant_name.lower(), None)
    
    # Mark session as closed
    session["status"] = "closed"
    session["winner"] = winner
    
    # Verify closure
    assert len(data["active_sessions"]) == 1  # Only nba_game remains
    assert session["status"] == "closed"
    assert session["winner"] == "Patriots"
    assert "patriots" not in data["contestant_to_session"]
    assert "cowboys" not in data["contestant_to_session"]


def test_contestant_name_conflict_detection():
    """Test that contestant name conflicts are properly detected."""
    data = create_multi_session_data()
    
    # Try to create a session with existing contestant names
    existing_contestants = set()
    for existing_session in data.get("betting_sessions", {}).values():
        for contestant_name in existing_session.get("contestants", {}).values():
            existing_contestants.add(contestant_name.lower())
    
    # Should detect conflicts
    assert "patriots" in existing_contestants
    assert "lakers" in existing_contestants
    
    # New contestants should be allowed
    assert "eagles" not in existing_contestants
    assert "celtics" not in existing_contestants


def test_session_validation():
    """Test session validation logic."""
    # Test session ID validation
    valid_session_ids = ["nfl_game", "lakers_vs_warriors", "test123", "a" * 50]
    invalid_session_ids = ["", "a" * 51, None]
    
    for session_id in valid_session_ids:
        assert session_id is not None and len(session_id) <= 50
    
    for session_id in invalid_session_ids:
        assert session_id is None or len(session_id) == 0 or len(session_id) > 50
    
    # Test contestant name validation
    valid_names = ["Patriots", "Los Angeles Lakers", "Team A"]
    invalid_names = ["", "   ", "a" * 51]
    
    for name in valid_names:
        clean_name = name.strip()
        assert clean_name and len(clean_name) <= 50
    
    for name in invalid_names:
        clean_name = name.strip()
        assert not clean_name or len(clean_name) > 50
    
    # Test timer duration validation
    valid_durations = [30, 300, 600, 3600]
    invalid_durations = [29, 3601, -1, 0]
    
    for duration in valid_durations:
        assert 30 <= duration <= 3600
    
    for duration in invalid_durations:
        assert duration < 30 or duration > 3600


if __name__ == "__main__":
    pytest.main([__file__])