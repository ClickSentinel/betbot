from config import (
    COLOR_INFO,
    COLOR_GOLD,
    TITLE_HELP,
    TITLE_BOT_COMMANDS,
    TITLE_ADMIN_COMMANDS,
    DESC_HELP_NOT_IMPLEMENTED,
    DESC_GENERAL_HELP,
    DESC_ADMIN_HELP,
)
from typing import Optional
from discord.ext import commands
import discord
import sys
import os

# Add the project root to the Python path to resolve imports like
# 'utils.live_message'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_embed(
        self,
        ctx: commands.Context,
        title: str,
        description: str,
        color: discord.Color,
        footer_text: Optional[str] = None,
    ) -> None:
        """Sends a consistent embed message."""
        embed = discord.Embed(title=title, description=description, color=color)
        if footer_text:
            embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)

    @commands.command(name="help", aliases=["h"])
    async def help_command(
        self, ctx: commands.Context, command_name: Optional[str] = None
    ) -> None:
        if command_name:
            await self._send_embed(
                ctx,
                TITLE_HELP,
                DESC_HELP_NOT_IMPLEMENTED.format(command_name=command_name),
                COLOR_INFO,
            )
        else:
            await self._send_embed(
                ctx,
                TITLE_BOT_COMMANDS,
                DESC_GENERAL_HELP,
                COLOR_INFO,
                footer_text="Bet responsibly!",
            )

    @commands.command(name="adminhelp", aliases=["ah"])
    async def admin_help_command(self, ctx: commands.Context) -> None:
        # Check if user has manage_guild permission or BetBoy role
        if not isinstance(ctx.author, discord.Member):
            await self._send_embed(
                ctx,
                TITLE_HELP,
                "This command can only be used in a server channel.",
                COLOR_INFO,
            )
            return

        has_role = discord.utils.get(ctx.author.roles, name="betboy") is not None
        has_permission = ctx.author.guild_permissions.manage_guild

        if not (has_role or has_permission):
            await self._send_embed(
                ctx,
                TITLE_HELP,
                "You need the 'BetBoy' role or 'Manage Server' permission to use this command.",
                COLOR_INFO,
            )
            return

        await self._send_embed(ctx, TITLE_ADMIN_COMMANDS, DESC_ADMIN_HELP, COLOR_GOLD)


async def setup(bot: commands.Bot):
    """Set up the Help cog."""
    await bot.add_cog(Help(bot))
