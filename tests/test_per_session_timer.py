import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from utils.live_message import update_live_message


@pytest.mark.asyncio
async def test_session_timer_info_passed_to_formatter(tmp_path):
    # Prepare data with a single session having an auto_close_at 60s from now
    now = time.time()
    session_id = "testsession123"
    data = {
        "balances": {},
        "betting": {"open": False, "locked": False, "bets": {}, "contestants": {}},
        "settings": {"enable_bet_timer": True},
        "reaction_bet_amounts": {},
        "contestant_1_emojis": [],
        "contestant_2_emojis": [],
        "live_message": None,
        "live_channel": None,
        "live_secondary_message": None,
        "live_secondary_channel": None,
        "timer_end_time": None,
        "betting_sessions": {
            session_id: {
                "id": session_id,
                "title": "A vs B",
                "created_at": now,
                "creator_id": 1,
                "channel_id": 123,
                "timer_config": {"enabled": True, "duration": 60, "auto_close_at": now + 60},
                "lock_time": None,
                "close_time": None,
                "status": "open",
                "contestants": {"c1": "A", "c2": "B"},
                "bets": {},
                "live_message_id": 999,
                "last_update": now,
                "total_pot": 0,
                "total_bettors": 0,
                "winner": None,
                "closed_at": None,
                "closed_by": None,
            }
        },
        "active_sessions": [session_id],
        "contestant_to_session": {"a": session_id, "b": session_id},
        "multi_session_mode": True,
    }

    mock_bot = MagicMock()
    # Mock fetch_user in case it's called (no bets so shouldn't be)
    mock_bot.fetch_user = AsyncMock()

    # Patch MessageFormatter.create_live_message_embed to capture timer_info
    with patch("utils.message_formatter.MessageFormatter.create_live_message_embed", new_callable=AsyncMock) as mock_formatter:
        # Call update_live_message for the session
        await update_live_message(mock_bot, data, current_time=now + 5, session_id=session_id)

        # Ensure formatter was awaited once
        mock_formatter.assert_awaited_once()
        # `await_args` returns (args, kwargs)
        args, kwargs = mock_formatter.await_args
        timer_info = kwargs.get("timer_info")
        assert timer_info is not None
        assert timer_info["total"] == 60
        # remaining should be roughly 55 seconds
        assert 50 <= timer_info["remaining"] <= 59
