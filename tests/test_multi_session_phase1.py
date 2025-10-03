"""
Test the multi-session data structure additions (Phase 1).
"""

import pytest
import os
import tempfile
from data_manager import load_data, save_data, find_session_by_contestant, is_multi_session_mode


def test_new_data_fields_initialization():
    """Test that new multi-session fields are properly initialized."""
    # Use a temporary file for testing - make sure file doesn't exist initially
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
        temp_file = f.name
    os.unlink(temp_file)  # Delete the file so load_data creates a new one
    
    # Mock DATA_FILE to use temp file
    original_data_file = None
    try:
        import data_manager
        original_data_file = data_manager.DATA_FILE
        data_manager.DATA_FILE = temp_file
        
        # Load data (should create new file with all fields)
        data = load_data()
        
        # Test that all new fields are present
        assert "betting_sessions" in data
        assert "active_sessions" in data  
        assert "contestant_to_session" in data
        assert "multi_session_mode" in data
        
        # Test initial values
        assert data["betting_sessions"] == {}
        assert data["active_sessions"] == []
        assert data["contestant_to_session"] == {}
        assert data["multi_session_mode"] == False
        
        # Test legacy fields still exist
        assert "betting" in data
        assert "balances" in data
        
    finally:
        # Cleanup
        if original_data_file:
            data_manager.DATA_FILE = original_data_file
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_multi_session_mode_detection():
    """Test multi-session mode detection."""
    # Test with default data (single-session mode)
    data = {
        "multi_session_mode": False,
        "betting_sessions": {},
        "active_sessions": [],
        "contestant_to_session": {},
    }
    
    assert is_multi_session_mode(data) == False
    
    # Test with multi-session mode enabled
    data["multi_session_mode"] = True
    assert is_multi_session_mode(data) == True


def test_contestant_lookup_basic():
    """Test basic contestant lookup functionality."""
    data = {
        "betting_sessions": {
            "session_001": {
                "contestants": {"1": "Alice", "2": "Bob"},
                "status": "open"
            },
            "session_002": {
                "contestants": {"1": "Charlie", "2": "Diana"},
                "status": "open"
            }
        },
        "active_sessions": ["session_001", "session_002"],
        "contestant_to_session": {},
    }
    
    # Test exact match
    result = find_session_by_contestant("Alice", data)
    assert result is not None
    session_id, contestant_key, contestant_name = result
    assert session_id == "session_001"
    assert contestant_name == "Alice"
    
    # Test case insensitive
    result = find_session_by_contestant("alice", data)
    assert result is not None
    session_id, contestant_key, contestant_name = result
    assert session_id == "session_001"
    assert contestant_name == "Alice"
    
    # Test not found
    result = find_session_by_contestant("Eve", data)
    assert result is None


def test_contestant_lookup_with_mapping():
    """Test contestant lookup with pre-built mapping."""
    data = {
        "betting_sessions": {
            "session_001": {
                "contestants": {"1": "Alice", "2": "Bob"},
                "status": "open"
            }
        },
        "active_sessions": ["session_001"],
        "contestant_to_session": {
            "Alice": "session_001",
            "Bob": "session_001"
        },
    }
    
    # Should use mapping for fast lookup
    result = find_session_by_contestant("Alice", data)
    assert result is not None
    session_id, contestant_key, contestant_name = result
    assert session_id == "session_001"
    assert contestant_name == "Alice"
    
    result = find_session_by_contestant("Bob", data)
    assert result is not None
    session_id, contestant_key, contestant_name = result
    assert session_id == "session_001"
    assert contestant_name == "Bob"


if __name__ == "__main__":
    test_new_data_fields_initialization()
    test_multi_session_mode_detection()
    test_contestant_lookup_basic()
    test_contestant_lookup_with_mapping()
    print("✅ All Phase 1 data structure tests pass!")