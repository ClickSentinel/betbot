from utils.performance_monitor import performance_monitor
from utils.error_handler import error_handler
from utils.logger import logger
from config import (
    TOKEN,
    COLOR_ERROR,
    COLOR_WARNING,
)
import traceback
from dotenv import load_dotenv
from discord.ext import commands
import discord
import os
import sys

# Add the project root to the Python path to resolve imports like 'betbot.cogs.betting'
# This ensures that 'betbot' is recognized as a top-level package.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# Add enhanced logging

load_dotenv()

# Ensure TOKEN is loaded
if TOKEN is None:
    print("Error: DISCORD_TOKEN environment variable not set.")
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True


class MyBot(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix, intents=intents)
        self._ambiguous_matches: dict[int, list[str]] = {}

    async def setup_hook(self) -> None:
        # Clear any stale timer state from previous runs
        await self._cleanup_stale_timer_state()

        # Load cogs
        logger.info("Loading cogs...")
        await self.load_extension("cogs.betting")
        await self.load_extension("cogs.economy")
        await self.load_extension("cogs.help")
        logger.info("Cogs loaded successfully.")

    async def _cleanup_stale_timer_state(self) -> None:
        """Clean up any stale timer state from previous bot runs."""
        try:
            from data_manager import load_data, save_data

            data = load_data()
            if data.get("timer_end_time") is not None:
                logger.info("Cleaning up stale timer state from previous run")
                data["timer_end_time"] = None
                save_data(data)
        except Exception as e:
            logger.warning(f"Failed to cleanup stale timer state: {e}")

    async def get_context(self, message, *, cls=commands.Context):
        ctx = await super().get_context(message, cls=cls)
        if ctx.command is None and ctx.prefix is not None:
            invoked_with = ctx.invoked_with
            if invoked_with:
                all_command_names_and_aliases = {cmd.name for cmd in self.commands}
                for cmd in self.commands:
                    all_command_names_and_aliases.update(cmd.aliases)

                potential_matches_names = [
                    cmd_name_or_alias
                    for cmd_name_or_alias in all_command_names_and_aliases
                    if cmd_name_or_alias.lower().startswith(invoked_with.lower())
                ]

                unique_potential_commands = list(
                    dict.fromkeys(
                        self.get_command(name_or_alias)
                        for name_or_alias in potential_matches_names
                        if self.get_command(name_or_alias)
                    )
                )

                if len(unique_potential_commands) == 1:
                    if unique_potential_commands[0] is not None:
                        ctx.command = unique_potential_commands[0]
                        ctx.invoked_with = unique_potential_commands[0].name
                elif len(unique_potential_commands) > 1:
                    self._ambiguous_matches[message.id] = sorted(
                        [
                            cmd.name
                            for cmd in unique_potential_commands
                            if cmd is not None
                        ]
                    )
        return ctx

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            message_id = ctx.message.id
            ambiguous_cmds = self._ambiguous_matches.pop(message_id, None)

            if ambiguous_cmds:
                cmd_list = ", ".join([f"`!{cmd}`" for cmd in ambiguous_cmds])
                embed = discord.Embed(
                    title="🤔 Ambiguous Command",
                    description=f"Did you mean one of these commands?\n{cmd_list}",
                    color=COLOR_WARNING,
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Command Not Found",
                    description=f"The command `!{
                        ctx.invoked_with}` does not exist. Use `!help` for a list of commands.",
                    color=COLOR_ERROR,
                )
                await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="⚠️ Missing Argument",
                description=f"You are missing a required argument: `{
                    error.param.name}`.\nUsage: `!{
                    ctx.command.name} {
                    ctx.command.signature}`",
                color=COLOR_ERROR,
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="⚠️ Bad Argument",
                description=f"Invalid argument provided: {error}\nUsage: `!{
                    ctx.command.name} {
                    ctx.command.signature}`",
                color=COLOR_ERROR,
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.NoPrivateMessage):
            embed = discord.Embed(
                title="🚫 Private Message Not Allowed",
                description="This command cannot be used in private messages.",
                color=COLOR_ERROR,
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="🚫 Missing Permissions",
                description=f"You do not have the required permissions to run this command: `{
                    ', '.join(
                        error.missing_permissions)}`.",
                color=COLOR_ERROR,
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                title="🚫 Bot Missing Permissions",
                description=f"I do not have the required permissions to run this command: `{
                    ', '.join(
                        error.missing_permissions)}`.",
                color=COLOR_ERROR,
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏳ Command on Cooldown",
                description=f"This command is on cooldown. Try again in `{
                    error.retry_after:.2f}` seconds.",
                color=COLOR_WARNING,
            )
            await ctx.send(embed=embed)
        else:
            print(
                f"Ignoring exception in command {
                    ctx.command}:",
                file=sys.stderr,
            )
            traceback.print_exception(
                type(error), error, error.__traceback__, file=sys.stderr
            )
            embed = discord.Embed(
                title="🚫 An Unexpected Error Occurred",
                description=f"An unexpected error occurred while running `!{
                    ctx.command}`. Please try again later.",
                color=COLOR_ERROR,
            )
            await ctx.send(embed=embed)


bot = MyBot(command_prefix="!", intents=intents)
bot.remove_command("help")  # Remove default help command to implement our own


@bot.event
async def on_ready():
    """Called when the bot is ready."""
    logger.info(f"Bot is ready! Logged in as {bot.user}")
    logger.info(f"Connected to {len(bot.guilds)} guilds")
    logger.info(f"Latency: {bot.latency * 1000:.2f}ms")

    # Initialize live message scheduler for batched updates
    from utils.live_message import initialize_live_message_scheduler

    initialize_live_message_scheduler(bot)
    logger.info("Live message scheduler initialized for batched updates")

    # Record startup metric
    performance_monitor.record_metric("bot.startup", 1)


@bot.event
async def on_command(ctx):
    """Called before every command."""
    logger.debug(
        f"Command '{
            ctx.command}' invoked by {
            ctx.author} in {
                ctx.guild}"
    )
    performance_monitor.record_metric("command.invoked", 1)


@bot.event
async def on_command_completion(ctx):
    """Called after successful command completion."""
    logger.debug(f"Command '{ctx.command}' completed successfully")


@bot.event
async def on_command_error(ctx, error):
    """Enhanced error handling with logging."""
    await error_handler.handle_command_error(ctx, error)


def main():
    """Main function to start the bot."""
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
