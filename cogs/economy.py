import discord
from discord.ext import commands
from typing import Optional

from config import (
    COLOR_SUCCESS,
    COLOR_INFO,
    COLOR_ERROR,
    MSG_AMOUNT_POSITIVE,
    TITLE_YOUR_BALANCE,
    TITLE_USER_BALANCE,
    TITLE_INVALID_AMOUNT,
    TITLE_COINS_GIVEN,
    TITLE_COINS_TAKEN,
    TITLE_INSUFFICIENT_FUNDS,
    TITLE_BALANCE_SET,
)
from data_manager import load_data, save_data, ensure_user


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_embed(
        self, ctx: commands.Context, title: str, description: str, color: discord.Color
    ) -> None:
        """Sends a consistent embed message."""
        embed = discord.Embed(title=title, description=description, color=color)
        await ctx.send(embed=embed)

    @commands.command(name="balance", aliases=["bal"])
    async def balance(
        self, ctx: commands.Context, member: Optional[discord.Member] = None
    ) -> None:
        target_member = member or ctx.author
        data = load_data()
        ensure_user(data, str(target_member.id))
        bal = data["balances"][str(target_member.id)]

        if target_member == ctx.author:
            # Enhanced balance display with betting context
            balance_info = [f"💰 **Your Balance:** `{bal}` coins"]

            # Add current bet context if user has an active bet
            # Use canonical accessor so this works in multi-session and legacy modes
            from data_manager import get_bets

            if data.get("betting", {}).get("open") or data.get("betting", {}).get("locked"):
                user_bet = get_bets(data).get(str(target_member.id))
                if user_bet:
                    bet_amount = user_bet["amount"]
                    choice = user_bet["choice"]
                    contestants = data["betting"].get("contestants", {})
                    contestant_name = next(
                        (
                            name
                            for name in contestants.values()
                            if name.lower() == choice
                        ),
                        choice.title(),
                    )

                    total_funds = bal + bet_amount
                    balance_info.extend(
                        [
                            f"🎯 **Active Bet:** `{bet_amount}` coins on **{contestant_name}**",
                            f"📊 **Total Funds:** `{total_funds}` coins ({bet_amount}/{total_funds} betting)",
                        ]
                    )

                    if data["betting"]["locked"]:
                        balance_info.append("⏳ **Status:** Awaiting bet results")
                    else:
                        balance_info.append("✅ **Status:** Bet can still be modified")

            await self._send_embed(
                ctx, TITLE_YOUR_BALANCE, "\n".join(balance_info), COLOR_INFO
            )
        else:
            await self._send_embed(
                ctx,
                TITLE_USER_BALANCE,
                f"{target_member.display_name} has `{bal}` coins.",
                COLOR_INFO,
            )

    @commands.command(name="give", aliases=["g"])
    @commands.has_permissions(manage_guild=True)
    async def give(
        self, ctx: commands.Context, member: discord.Member, amount: int
    ) -> None:
        if amount <= 0:
            await self._send_embed(
                ctx, TITLE_INVALID_AMOUNT, MSG_AMOUNT_POSITIVE, COLOR_ERROR
            )
            return

        data = load_data()
        ensure_user(data, str(member.id))
        data["balances"][str(member.id)] += amount
        save_data(data)
        await self._send_embed(
            ctx,
            TITLE_COINS_GIVEN,
            f"Gave `{amount}` coins to {member.mention}. They now have `{data['balances'][str(member.id)]}` coins.",
            COLOR_SUCCESS,
        )

    @commands.command(name="take", aliases=["t"])
    @commands.has_permissions(manage_guild=True)
    async def take(
        self, ctx: commands.Context, member: discord.Member, amount: int
    ) -> None:
        if amount <= 0:
            await self._send_embed(
                ctx, TITLE_INVALID_AMOUNT, MSG_AMOUNT_POSITIVE, COLOR_ERROR
            )
            return

        data = load_data()
        ensure_user(data, str(member.id))

        if data["balances"][str(member.id)] < amount:
            await self._send_embed(
                ctx,
                TITLE_INSUFFICIENT_FUNDS,
                f"{member.display_name} only has `{data['balances'][str(member.id)]}` coins. Cannot take `{amount}`.",
                COLOR_ERROR,
            )
            return

        data["balances"][str(member.id)] -= amount
        save_data(data)
        await self._send_embed(
            ctx,
            TITLE_COINS_TAKEN,
            f"Took `{amount}` coins from {member.mention}. They now have `{data['balances'][str(member.id)]}` coins.",
            COLOR_SUCCESS,
        )

    @commands.command(name="setbal", aliases=["sb"])
    @commands.has_permissions(manage_guild=True)
    async def set_balance(
        self, ctx: commands.Context, member: discord.Member, amount: int
    ) -> None:
        if amount < 0:
            await self._send_embed(
                ctx, TITLE_INVALID_AMOUNT, MSG_AMOUNT_POSITIVE, COLOR_ERROR
            )
            return

        data = load_data()
        ensure_user(data, str(member.id))
        data["balances"][str(member.id)] = amount
        save_data(data)
        await self._send_embed(
            ctx,
            TITLE_BALANCE_SET,
            f"Set {member.mention}'s balance to `{amount}` coins.",
            COLOR_SUCCESS,
        )


async def setup(bot: commands.Bot):
    """Set up the Economy cog."""
    await bot.add_cog(Economy(bot))
