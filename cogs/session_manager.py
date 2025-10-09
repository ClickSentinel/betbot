"""
Session management for multi-session betting.
"""

import discord
from discord.ext import commands
from typing import Optional, Dict, List, Any
import time

from utils.logger import logger
from utils.performance_monitor import performance_monitor

from config import (
    BET_TIMER_DURATION,
)
from data_manager import (
    load_data,
    save_data,
    Data,
    MultiBettingSession,
)
from data_manager import is_multi_session_mode, find_session_by_contestant


class SessionManager(commands.Cog):
    """Manages betting sessions in multi-session mode."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def create_session(
        self,
        name1: str,
        name2: str,
        creator_id: int,
        channel_id: int
    ) -> str:
        """Create a new betting session."""
        data = load_data()

        # Ensure multi-session mode is enabled
        if not is_multi_session_mode(data):
            data["betting_sessions"] = {}
            data["active_sessions"] = []
            data["contestant_to_session"] = {}
            data["multi_session_mode"] = True

        # Check for contestant name conflicts
        for existing_session in data.get("betting_sessions", {}).values():
            if existing_session.get("status") == "closed":
                continue
            for contestant_name in existing_session.get("contestants", {}).values():
                if contestant_name.lower() in (name1.lower(), name2.lower()):
                    raise ValueError(f"Contestant '{contestant_name}' already exists in another session.")

        # Generate session ID
        if "next_session_id" not in data:
            data["next_session_id"] = 1  # type: ignore

        candidate = str(data["next_session_id"])  # type: ignore
        while candidate in data.get("betting_sessions", {}):
            data["next_session_id"] = int(data["next_session_id"]) + 1  # type: ignore
            candidate = str(data["next_session_id"])  # type: ignore

        session_id = candidate
        data["next_session_id"] = int(session_id) + 1  # type: ignore

        # Create new session
        new_session: MultiBettingSession = {
            "id": session_id,
            "title": f"{name1} vs {name2}",
            "status": "open",
            "contestants": {"c1": name1, "c2": name2},
            "bets": {},
            "timer_config": {
                "enabled": data["settings"].get("enable_bet_timer", True),
                "duration": BET_TIMER_DURATION,
                "lock_duration": None,
                "close_duration": None,
                "update_interval": 60,
                "auto_lock_at": None,
                "auto_close_at": (time.time() + BET_TIMER_DURATION)
                if data["settings"].get("enable_bet_timer", True)
                else None,
            },
            "created_at": time.time(),
            "creator_id": creator_id,
            "channel_id": channel_id,
            "lock_time": None,
            "close_time": None,
            "live_message_id": None,
            "last_update": time.time(),
            "total_pot": 0,
            "total_bettors": 0,
            "winner": None,
            "closed_at": None,
            "closed_by": None,
        }

        # Register session
        data["betting_sessions"][session_id] = new_session
        data["active_sessions"].append(session_id)
        data["contestant_to_session"][name1.lower()] = session_id
        data["contestant_to_session"][name2.lower()] = session_id

        save_data(data)

        logger.info(f"Betting session created: {session_id} - {name1} vs {name2}")
        performance_monitor.record_metric(
            "betting.session_created",
            1,
            {"contestant1": name1, "contestant2": name2, "session_id": session_id},
        )

        return session_id

    def get_active_sessions(self, data: Data) -> Dict[str, MultiBettingSession]:
        """Get all active betting sessions."""
        sessions = {}
        for session_id in data.get("active_sessions", []):
            if session_id in data.get("betting_sessions", {}):
                sessions[session_id] = data["betting_sessions"][session_id]
        return sessions

    def find_session_by_target(self, target: str, data: Data) -> Optional[str]:
        """Find a session by contestant name or session ID."""
        # Prefer contestant name resolution first
        tuple_found = find_session_by_contestant(target, data)
        if tuple_found:
            return tuple_found[0]

        # Check if target is a session ID
        if target in data.get("betting_sessions", {}):
            return target

        return None

    def resolve_session_for_channel(self, channel_id: int, data: Data) -> Optional[str]:
        """Resolve a session for a channel (first active session in that channel)."""
        for session_id in data.get("active_sessions", []):
            session = data.get("betting_sessions", {}).get(session_id)
            if session and session.get("channel_id") == channel_id:
                return session_id
        return None

    def get_single_active_session(self, data: Data) -> Optional[str]:
        """Get the single active session if there's exactly one."""
        active = data.get("active_sessions", [])
        if len(active) == 1:
            return active[0]
        return None

    async def close_session(
        self,
        ctx: commands.Context,
        session_id: str,
        winner_name: Optional[str] = None
    ) -> None:
        """Close a betting session."""
        data = load_data()

        if session_id not in data.get("betting_sessions", {}):
            await ctx.send(f"Session {session_id} not found.")
            return

        session = data["betting_sessions"][session_id]
        session["status"] = "closed"
        session["closed_at"] = time.time()
        session["closed_by"] = str(ctx.author.id)

        if winner_name:
            session["winner"] = winner_name

        # Remove from active sessions
        if session_id in data.get("active_sessions", []):
            data["active_sessions"].remove(session_id)

        save_data(data)

        logger.info(f"Session closed: {session_id} by {ctx.author}")
        await ctx.send(f"Session {session_id} closed successfully.")

    def get_session_info(self, session_id: str, data: Data) -> Optional[MultiBettingSession]:
        """Get information about a specific session."""
        return data.get("betting_sessions", {}).get(session_id)

    def list_sessions(self, data: Data) -> List[Dict[str, Any]]:
        """List all sessions with basic info."""
        sessions = []
        for session_id, session in data.get("betting_sessions", {}).items():
            sessions.append({
                "id": session_id,
                "title": session.get("title", "Unknown"),
                "status": session.get("status", "unknown"),
                "created_at": session.get("created_at", 0),
                "total_bettors": session.get("total_bettors", 0),
                "total_pot": session.get("total_pot", 0),
            })
        return sessions


async def setup(bot: commands.Bot) -> None:
    """Setup function for the SessionManager cog."""
    await bot.add_cog(SessionManager(bot))