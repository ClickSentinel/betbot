"""
Betting timer management functionality.
"""
import asyncio
import time
from typing import Optional
import discord
from discord.ext import commands

from config import BET_TIMER_DURATION, BET_TIMER_UPDATE_INTERVAL
from data_manager import Data, save_data, load_data
from utils.live_message import update_live_message
from utils.logger import logger


class BettingTimer:
    """Manages betting round timers."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.timer_task: Optional[asyncio.Task] = None
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
    
    async def start_timer(self, ctx: commands.Context, total_duration: int, timeout_callback=None):
        """Start a betting timer for the specified duration."""
        self.timeout_callback = timeout_callback
        self.timer_task = asyncio.create_task(
            self._run_timer(ctx, total_duration)
        )
        logger.info(f"Betting timer started for {total_duration} seconds")
    
    async def _run_timer(self, ctx: commands.Context, total_duration: int):
        """Internal timer implementation."""
        try:
            # Set end time
            end_time = time.time() + total_duration
            data = load_data()
            data["timer_end_time"] = end_time
            save_data(data)
            
            # Update live message periodically (only on 5s/0s intervals)
            last_update_time = None
            while time.time() < end_time:
                current_time = time.time()
                remaining_time = int(end_time - current_time)
                
                data = load_data()
                
                # Check if betting was manually locked
                if data["betting"]["locked"]:
                    logger.info("Timer stopped - betting was manually locked")
                    self.clear_timer_state_in_data(data)
                    return
                
                # Only update live message when remaining time ends in 5 or 0
                should_update = (remaining_time % 10 == 5 or remaining_time % 10 == 0)
                
                # Also update if this is the first update or if enough time has passed since last update
                if should_update and (last_update_time is None or remaining_time != last_update_time):
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
    
    async def _auto_lock_bets(self, ctx: commands.Context, data: Data):
        """Automatically lock bets when timer expires."""
        from utils.message_formatter import MessageFormatter
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
            bet_summary="Timer expired - bets are now locked"
        )
        
        # Update live message
        await update_live_message(
            self.bot, data, betting_closed=True, close_summary=lock_summary
        )