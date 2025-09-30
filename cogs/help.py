import sys
import os

# Add the project root to the Python path to resolve imports like 'utils.live_message'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import discord
from discord.ext import commands
from typing import Optional

from config import (
    COLOR_INFO, COLOR_GOLD,
    TITLE_HELP, TITLE_BOT_COMMANDS, TITLE_ADMIN_COMMANDS,
    DESC_HELP_NOT_IMPLEMENTED, DESC_GENERAL_HELP, DESC_ADMIN_HELP
)

class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_embed(self, ctx: commands.Context, title: str, description: str, color: discord.Color, footer_text: Optional[str] = None) -> None:
        """Sends a consistent embed message."""
        embed = discord.Embed(title=title, description=description, color=color)
        if footer_text:
            embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)

    @commands.command(name="help", aliases=["h"])
    async def help_command(self, ctx: commands.Context, command_name: Optional[str] = None) -> None:
        if command_name:
            await self._send_embed(ctx, TITLE_HELP,
                                   DESC_HELP_NOT_IMPLEMENTED.format(command_name=command_name),
                                   COLOR_INFO)
        else:
            await self._send_embed(ctx, TITLE_BOT_COMMANDS, DESC_GENERAL_HELP, COLOR_INFO,
                                   footer_text="Bet responsibly! Contact an admin if you need help.")

    @commands.command(name="adminhelp", aliases=["ah"])
    @commands.has_permissions(manage_guild=True)
    async def admin_help_command(self, ctx: commands.Context) -> None:
        await self._send_embed(ctx, TITLE_ADMIN_COMMANDS, DESC_ADMIN_HELP, COLOR_GOLD)

async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))