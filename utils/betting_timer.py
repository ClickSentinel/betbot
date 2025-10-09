"""
Betting timer management functionality.
"""

import asyncio
from typing import Optional
from discord.ext import commands


from data_manager import Data, save_data, load_data
from utils.live_message import (
    update_live_message,
    schedule_live_message_update,
    schedule_live_message_update_for_session,
)
from data_manager import get_active_sessions
from utils.logger import logger


class BettingTimer:
    """Manages betting round timers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.timer_task: Optional[asyncio.Task] = None
        self.session_monitor_task: Optional[asyncio.Task] = None
        self.timeout_callback = None

    def cancel_timer(self):
        """Cancel the current betting timer."""
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
            logger.info("Betting timer cancelled")

    def clear_timer_state_in_data(self, data: Data) -> None:
        """Clears timer-related data."""
        data["timer_end_time"] = None
        save_data(data)

    async def start_timer(
        self, ctx: commands.Context, total_duration: int, timeout_callback=None
    ):
        """Start a betting timer for the specified duration."""
        self.timeout_callback = timeout_callback
        self.timer_task = asyncio.create_task(self._run_timer(ctx, total_duration))
        # Ensure the session monitor is running so multi-session timers are processed
        if not self.session_monitor_task or self.session_monitor_task.done():
            self.session_monitor_task = asyncio.create_task(self._run_session_monitor())
        logger.info(f"Betting timer started for {total_duration} seconds")

    async def _run_timer(self, ctx: commands.Context, total_duration: int):
        """Internal timer implementation."""
        import time as time_module  # Import directly to avoid mock interference

        try:
            # Set end time
            end_time = time_module.time() + total_duration
            data = load_data()
            data["timer_end_time"] = end_time
            save_data(data)

            # Update live message periodically (only on 5s/0s intervals)
            last_update_time = None
            while time_module.time() < end_time:
                current_time = time_module.time()
                remaining_time = int(end_time - current_time)

                data = load_data()

                # Check if betting was manually locked
                if data["betting"]["locked"]:
                    logger.info("Timer stopped - betting was manually locked")
                    self.clear_timer_state_in_data(data)
                    return

                # Only update live message when remaining time ends in 5 or 0
                should_update = remaining_time % 10 == 5 or remaining_time % 10 == 0

                # Also update if this is the first update or if enough time has
                # passed since last update
                if should_update and (
                    last_update_time is None or remaining_time != last_update_time
                ):
                    # Use direct update for timer displays to ensure accurate
                    # countdown
                    await update_live_message(self.bot, data, current_time=current_time)
                    last_update_time = remaining_time
                    logger.info(f"Timer update: {remaining_time} seconds remaining")

                # Check every second but only update on 5s/0s intervals
                await asyncio.sleep(1)

            # Timer expired - auto-lock bets
            data = load_data()
            if data["betting"]["open"] and not data["betting"]["locked"]:
                if self.timeout_callback:
                    await self.timeout_callback(ctx)
                else:
                    await self._auto_lock_bets(ctx, data)

        except asyncio.CancelledError:
            logger.info("Betting timer was cancelled")
            data = load_data()
            self.clear_timer_state_in_data(data)
        except Exception as e:
            logger.error(f"Error in betting timer: {e}", exc_info=True)
            # Clear timer state on error to prevent future issues
            try:
                data = load_data()
                self.clear_timer_state_in_data(data)
            except Exception:
                pass  # Don't let cleanup errors break the error handler

    async def _run_session_monitor(self):
        """
        Background monitor that iterates active sessions and processes per-session
        timers based on `timer_config.auto_close_at` and related fields.
        """
        import time as time_module

        try:
            while True:
                data = load_data()

                # Iterate active sessions and handle auto-close/auto-lock
                for session_id in data.get("active_sessions", []):
                    session = data.get("betting_sessions", {}).get(session_id)
                    if not session:
                        continue

                    tc = session.get("timer_config") or {}
                    if not tc.get("enabled"):
                        continue

                    now = time_module.time()

                    # Prefer auto_close_at (session-level precise close time)
                    auto_close = tc.get("auto_close_at")
                    # Optionally support auto_lock_at if provided
                    auto_lock = tc.get("auto_lock_at")

                    # If auto_lock is present and we've passed it, mark locked
                    if auto_lock and session.get("status") == "open" and auto_lock <= now:
                        # Lock this session
                        await self._auto_lock_bets_for_session(session_id, data)

                    # If auto_close is present and we've passed it, finalize/close
                    if auto_close and session.get("status") != "completed" and auto_close <= now:
                        # Mark session as completed/closed and update live message
                        await self._auto_close_session(session_id, data)

                # Throttle checks to once per second
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Session monitor cancelled")
        except Exception as e:
            logger.error(f"Error in session monitor: {e}", exc_info=True)

    async def _auto_lock_bets_for_session(self, session_id: str, data):
        """Lock a specific session when its timer triggers auto-lock."""
        from config import MSG_BETTING_TIMER_EXPIRED_SUMMARY

        session = data.get("betting_sessions", {}).get(session_id)
        if not session:
            return

        logger.info(f"Auto-locking session {session_id} due to timer")

        # Change status to locked
        session["status"] = "locked"
        # Persist timer/lock state
        save_data(data)

        # Create summary tailored for the session
        total_bets = len(session.get("bets", {}))
        lock_summary = MSG_BETTING_TIMER_EXPIRED_SUMMARY.format(
            total_bets=total_bets,
            bet_summary="Timer expired - bets are now locked",
        )

        # Update the session live message immediately
        try:
            await update_live_message(self.bot, data, betting_closed=True, close_summary=lock_summary, session_id=session_id)
        except Exception:
            logger.exception("Failed to update live message for session lock")

        # Schedule a batched update for the session to allow pending operations
        schedule_live_message_update_for_session(session_id)

    async def _auto_close_session(self, session_id: str, data):
        """Finalize/close a session when its timer triggers auto-close."""
        session = data.get("betting_sessions", {}).get(session_id)
        if not session:
            return

        logger.info(f"Auto-closing session {session_id} due to timer")

        # Mark session as completed
        session["status"] = "completed"
        session["closed_at"] = __import__("time").time()
        save_data(data)

        # Update live message to show closed/completed status
        try:
            await update_live_message(self.bot, data, betting_closed=True, close_summary="Session closed by timer", session_id=session_id)
        except Exception:
            logger.exception("Failed to update live message for session close")

        # Also schedule a batched update for the session id
        schedule_live_message_update_for_session(session_id)

    async def _auto_lock_bets(self, ctx: commands.Context, data: Data):
        """Automatically lock bets when timer expires."""
        from config import MSG_BETTING_TIMER_EXPIRED_SUMMARY

        logger.info("Betting timer expired - auto-locking bets")

        # Lock the bets
        data["betting"]["open"] = False
        data["betting"]["locked"] = True
        self.clear_timer_state_in_data(data)
        save_data(data)

        # Create summary message
        lock_summary = MSG_BETTING_TIMER_EXPIRED_SUMMARY.format(
            total_bets=len(data["betting"]["bets"]),
            bet_summary="Timer expired - bets are now locked",
        )

        # Update live message immediately to show locked state
        # Use direct update instead of batched to ensure immediate feedback
        await update_live_message(
            self.bot, data, betting_closed=True, close_summary=lock_summary
        )

        # Also schedule a batched update to handle any last-moment bets that
        # might be pending
        schedule_live_message_update()
