"""
Betting-specific utilities and permission checks.
"""

import discord
from discord.ext import commands
from typing import Optional, Tuple

from config import ROLE_BETBOY, COLOR_ERROR, TITLE_BETTING_ERROR
from data_manager import Data
from utils.logger import logger


class BettingPermissions:
    """Handles betting permission checks."""

    @staticmethod
    async def check_permission(ctx: commands.Context, action: str) -> bool:
        """Centralized permission check for betting actions."""
        if not isinstance(ctx.author, discord.Member):
            embed = discord.Embed(
                title=TITLE_BETTING_ERROR,
                description="This command can only be used in a server channel.",
                color=COLOR_ERROR,
            )
            await ctx.send(embed=embed)
            return False

        required_role = discord.utils.get(ctx.author.roles, name=ROLE_BETBOY)
        if required_role is None:
            embed = discord.Embed(
                title=TITLE_BETTING_ERROR,
                description=f"You need the '{ROLE_BETBOY}' role to {action}.",
                color=COLOR_ERROR,
            )
            await ctx.send(embed=embed)
            return False

        logger.debug(f"Permission check passed for {ctx.author} to {action}")
        return True


class BettingUtils:
    """Utility functions for betting operations."""

    @staticmethod
    def find_contestant_info(
        data: Data, choice_input: str
    ) -> Optional[Tuple[str, str]]:
        """Finds a contestant ID and name based on partial input."""
        contestants = data["betting"].get("contestants", {})
        choice_lower = choice_input.lower()

        for c_id, c_name in contestants.items():
            if c_name.lower().startswith(choice_lower):
                return c_id, c_name
        return None

    @staticmethod
    async def send_embed(
        ctx: commands.Context, title: str, description: str, color: discord.Color
    ) -> None:
        """Sends a consistent embed message."""
        embed = discord.Embed(title=title, description=description, color=color)
        await ctx.send(embed=embed)

    @staticmethod
    async def add_betting_reactions(message: discord.Message, data: Data) -> None:
        """Adds all configured betting reactions to a message with rate limiting protection."""
        import asyncio
        from config import SEPARATOR_EMOJI

        all_emojis_to_add = (
            data["contestant_1_emojis"]
            + [SEPARATOR_EMOJI]
            + data["contestant_2_emojis"]
        )

        for i, emoji in enumerate(all_emojis_to_add):
            try:
                await message.add_reaction(emoji)
                # Add a small delay between reactions to avoid rate limiting
                # Discord allows roughly 1 reaction per 0.25 seconds
                if i < len(all_emojis_to_add) - 1:  # Don't delay after the last emoji
                    await asyncio.sleep(0.3)
            except discord.HTTPException as e:
                if "rate limited" in str(e).lower() or "429" in str(e):
                    # If we're rate limited, wait longer and retry once
                    logger.warning(
                        f"Rate limited adding reaction {emoji}, waiting and retrying..."
                    )
                    await asyncio.sleep(1.0)
                    try:
                        await message.add_reaction(emoji)
                    except discord.HTTPException as retry_e:
                        logger.warning(
                            f"Could not add reaction {emoji} after retry: {retry_e}"
                        )
                else:
                    logger.warning(
                        f"Could not add reaction {emoji} to live message: {e}"
                    )

    @staticmethod
    async def remove_user_betting_reactions(
        message: discord.Message,
        user: discord.abc.User,
        data: Data,
        exclude_emoji: Optional[str] = None,
    ) -> None:
        """Removes all betting reactions from a specific user on a message."""
        all_betting_emojis = data["contestant_1_emojis"] + data["contestant_2_emojis"]

        for emoji_str in all_betting_emojis:
            if emoji_str == exclude_emoji:
                continue  # Skip the emoji that was just added

            try:
                await message.remove_reaction(emoji_str, user)
            except discord.NotFound:
                pass  # Reaction not found, that's fine
            except discord.HTTPException as e:
                logger.warning(
                    f"Failed to remove reaction {emoji_str} from user {
                        user.name}: {e}"
                )
