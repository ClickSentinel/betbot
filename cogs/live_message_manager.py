"""
Live message management for betting rounds.
"""

import discord
from discord.ext import commands
from typing import Optional, Tuple, Dict, Any
import asyncio
import time

# Add enhanced logging
from utils.logger import logger
from utils.performance_monitor import performance_monitor

from config import (
    CONTESTANT_EMOJIS,
    SEPARATOR_EMOJI,
    COLOR_GOLD,
    TITLE_LIVE_BETTING_ROUND,
    MSG_LIVE_BET_INITIAL_DESCRIPTION,
)
from data_manager import (
    load_data,
    save_data,
    Data,
)
from utils.live_message import (
    get_live_message_info,
    get_saved_bet_channel_id,
    set_live_message_info,
    set_secondary_live_message_info,
    clear_live_message_info,
    update_live_message,
    get_live_message_link,
    get_live_message_link_for_session,
    get_secondary_live_message_info,
    schedule_live_message_update,
    schedule_live_message_update_for_session,
    initialize_live_message_scheduler,
)


class LiveMessageManager(commands.Cog):
    """Manages live betting messages and updates."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Initialize the live message scheduler
        initialize_live_message_scheduler(bot)

    async def create_live_message(
        self,
        ctx: commands.Context,
        name1: str,
        name2: str,
        session_id: Optional[str] = None
    ) -> Optional[discord.Message]:
        """Create a new live betting message."""
        data = load_data()

        main_chan_id = get_saved_bet_channel_id(data)
        target_channel: Optional[discord.TextChannel] = None

        if main_chan_id:
            channel_obj = self.bot.get_channel(main_chan_id)
            if isinstance(channel_obj, discord.TextChannel):
                target_channel = channel_obj

        # If no valid saved text channel, try to use the context channel if
        # it's a text channel
        if target_channel is None and isinstance(ctx.channel, discord.TextChannel):
            target_channel = ctx.channel

        # If still no target_channel (e.g., ctx.channel is a DMChannel and no
        # saved channel)
        if target_channel is None:
            return None

        initial_embed_description = MSG_LIVE_BET_INITIAL_DESCRIPTION.format(
            contestant1_emoji=CONTESTANT_EMOJIS[0],
            name1=name1,
            contestant2_emoji=CONTESTANT_EMOJIS[1],
            name2=name2,
        )

        main_live_msg = None
        try:
            main_live_msg = await target_channel.send(
                embed=discord.Embed(
                    title=TITLE_LIVE_BETTING_ROUND,
                    description=initial_embed_description,
                    color=COLOR_GOLD,
                )
            )

            if session_id:
                from utils.live_message import set_session_live_message_info
                set_session_live_message_info(data, session_id, main_live_msg.id, target_channel.id)
            else:
                set_live_message_info(data, main_live_msg.id, target_channel.id)

            # Update live message to populate the embed
            await update_live_message(self.bot, data, session_id=session_id)

        except Exception as e:
            logger.error(f"Error sending main live message: {e}")
            if session_id:
                from utils.live_message import set_session_live_message_info
                set_session_live_message_info(data, session_id, None, None)
            else:
                set_live_message_info(data, None, None)
            return None

        if main_live_msg:
            # Add reactions in the background
            self._add_reactions_background(main_live_msg, data)

        # Only send a secondary message if no saved bet channel exists and
        # the invoking channel is different from the target channel.
        if (
            main_chan_id is None
            and isinstance(ctx.channel, discord.TextChannel)
            and ctx.channel.id != target_channel.id
        ):
            try:
                secondary_live_msg = await ctx.channel.send(
                    embed=discord.Embed(
                        title=TITLE_LIVE_BETTING_ROUND,
                        description=initial_embed_description,
                        color=COLOR_GOLD,
                    )
                )
                set_secondary_live_message_info(
                    data, secondary_live_msg.id, ctx.channel.id
                )
            except Exception as e:
                logger.error(f"Error sending secondary live message: {e}")
                set_secondary_live_message_info(data, None, None)

        return main_live_msg

    async def update_live_messages(self, data: Data, session_id: Optional[str] = None) -> None:
        """Update all relevant live messages."""
        await update_live_message(self.bot, data, session_id=session_id)

    def _add_reactions_background(self, message: discord.Message, data: Data) -> None:
        """Add reactions to a message in the background."""
        async def add_reactions():
            try:
                # Add all betting emojis from both contestants with separator
                c1_emojis = data.get("contestant_1_emojis", [])
                c2_emojis = data.get("contestant_2_emojis", [])
                
                # Add contestant 1 emojis
                for emoji in c1_emojis:
                    await message.add_reaction(emoji)
                
                # Add separator
                await message.add_reaction(SEPARATOR_EMOJI)
                
                # Add contestant 2 emojis
                for emoji in c2_emojis:
                    await message.add_reaction(emoji)
            except Exception as e:
                logger.error(f"Failed to add reactions to message {message.id}: {e}")

        asyncio.create_task(add_reactions())

    async def clear_live_messages(self, data: Data, session_id: Optional[str] = None) -> None:
        """Clear live message information."""
        if session_id:
            # TODO: Implement session-specific clearing
            pass
        else:
            clear_live_message_info(data)

    def get_live_message_link(self, data: Data, session_id: Optional[str] = None) -> Optional[str]:
        """Get the link to the live message."""
        if session_id:
            return get_live_message_link_for_session(self.bot, data, session_id)
        else:
            return get_live_message_link(self.bot, data, True)


async def setup(bot: commands.Bot) -> None:
    """Setup function for the LiveMessageManager cog."""
    await bot.add_cog(LiveMessageManager(bot))