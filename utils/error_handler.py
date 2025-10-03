"""
Centralized error handling and recovery system.
"""

import asyncio
import discord
from datetime import datetime
from functools import wraps

from utils.logger import logger


class BotError(Exception):
    """Base exception for bot-specific errors."""

    pass


class BettingError(BotError):
    """Betting-related errors."""

    pass


class DataError(BotError):
    """Data persistence errors."""

    pass


class RateLimitError(BotError):
    """Rate limiting errors."""

    pass


class ErrorHandler:
    """Centralized error handling system."""

    def __init__(self):
        self.error_counts = {}
        self.last_errors = {}

    async def handle_command_error(self, ctx, error: Exception):
        """Handle command errors with user-friendly messages."""

        # Log the error
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)

        # Track error frequency
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        self.last_errors[error_type] = datetime.now()

        # Create user-friendly embed
        if isinstance(error, discord.errors.NotFound):
            embed = discord.Embed(
                title="❌ Message Not Found",
                description="The message or channel couldn't be found. It may have been deleted.",
                color=discord.Color.red(),
            )
        elif isinstance(error, discord.errors.Forbidden):
            embed = discord.Embed(
                title="❌ Permission Error",
                description="I don't have permission to perform this action.",
                color=discord.Color.red(),
            )
        elif isinstance(error, BettingError):
            embed = discord.Embed(
                title="❌ Betting Error",
                description=str(error),
                color=discord.Color.red(),
            )
        elif isinstance(error, RateLimitError):
            embed = discord.Embed(
                title="⏰ Rate Limited",
                description=str(error),
                color=discord.Color.orange(),
            )
        else:
            # Generic error
            embed = discord.Embed(
                title="❌ Something went wrong",
                description="An unexpected error occurred. The issue has been logged.",
                color=discord.Color.red(),
            )
            embed.add_field(name="Error ID", value=f"`{id(error)}`", inline=False)

        try:
            await ctx.send(embed=embed)
        except BaseException:
            # Fallback if embed fails
            await ctx.send(
                "❌ An error occurred and I couldn't send the error message."
            )

    async def handle_task_error(self, task_name: str, error: Exception):
        """Handle background task errors."""
        logger.error(f"Task error in {task_name}: {error}", exc_info=True)

        # Implement retry logic if appropriate
        if isinstance(error, (asyncio.TimeoutError, ConnectionError)):
            logger.info(f"Retrying task {task_name} in 30 seconds...")
            await asyncio.sleep(30)
            return True  # Indicate retry

        return False  # Don't retry

    def get_error_stats(self) -> dict:
        """Get error statistics for monitoring."""
        return {
            "error_counts": self.error_counts.copy(),
            "last_errors": {k: v.isoformat() for k, v in self.last_errors.items()},
        }


def handle_exceptions(fallback_return=None):
    """Decorator for automatic exception handling."""

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Exception in {
                        func.__name__}: {e}",
                    exc_info=True,
                )
                return fallback_return

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Exception in {
                        func.__name__}: {e}",
                    exc_info=True,
                )
                return fallback_return

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Global error handler instance
error_handler = ErrorHandler()
