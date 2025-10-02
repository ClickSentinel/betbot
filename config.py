import os
from dotenv import load_dotenv
import discord

load_dotenv()

# ---------- Bot Configuration ----------
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
STARTING_BALANCE = 1_000

# New: Betting Timer Configuration
ENABLE_BET_TIMER_DEFAULT = False
BET_TIMER_DURATION = 90
BET_TIMER_UPDATE_INTERVAL = 5

# ---------- Emojis ----------
SEPARATOR_EMOJI = "➖"

# Main contestant display emojis
CONTESTANT_EMOJI_1 = "🔴"
CONTESTANT_EMOJI_2 = "🔵"
CONTESTANT_EMOJIS = [CONTESTANT_EMOJI_1, CONTESTANT_EMOJI_2]

# Emojis for Contestant 1 (Power/Victory theme) - used for reaction betting
C1_EMOJIS = ["🔥", "⚡", "💪", "🏆"]
# Emojis for Contestant 2 (Excellence/Royalty theme) - used for reaction betting
C2_EMOJIS = ["🌟", "💎", "🚀", "👑"]

# Mapping of reaction emojis to bet amounts
REACTION_BET_AMOUNTS = {
    "🔥": 100,
    "⚡": 250,
    "💪": 500,
    "🏆": 1000,
    "🌟": 100,
    "💎": 250,
    "🚀": 500,
    "👑": 1000,
}

# ---------- Live Message Keys ----------
LIVE_MESSAGE_KEY = "live_message"
LIVE_CHANNEL_KEY = "live_channel"
LIVE_SECONDARY_KEY = "live_secondary_message"
LIVE_SECONDARY_CHANNEL_KEY = "live_secondary_channel"

# ---------- Colors for Embeds ----------
COLOR_SUCCESS = discord.Color(0x2ECC71)  # Green
COLOR_INFO = discord.Color(0x3498DB)  # Blue
COLOR_WARNING = discord.Color(0xF1C40F)  # Yellow
COLOR_ERROR = discord.Color(0xE74C3C)  # Red
COLOR_GOLD = discord.Color(0xFFD700)  # Gold
COLOR_DARK_ORANGE = discord.Color(0xFF8C00)  # Dark Orange
COLOR_DARK_GRAY = discord.Color(0x607D8B)  # Dark Gray
COLOR_WARNING = discord.Color(0xF1C40F)  # Yellow
COLOR_ERROR = discord.Color(0xE74C3C)  # Red
COLOR_GOLD = discord.Color(0xFFD700)  # Gold
COLOR_DARK_ORANGE = discord.Color(0xFF8C00)  # Dark Orange
COLOR_DARK_GRAY = discord.Color(0x607D8B)  # Dark Gray

# ---------- General Messages ----------
MSG_AMOUNT_POSITIVE = "Amount must be a positive number."
MSG_INVALID_BET_FORMAT = "**Invalid bet format.**\nUse `!bet <contestant> <amount>` or `!bet <amount> <contestant>`.\nExample: `!bet Alice 100`"
MSG_UNKNOWN_CONTESTANT = "**Unknown contestant: '{contestant_name}'**\n\nAvailable contestants:\n{contestants_list}\n\nExample: `!bet {example_contestant} 100`"
MSG_INVALID_OPENBET_FORMAT = "**Invalid openbet format.**\nUse `!openbet <contestant1> <contestant2>` to start a new betting round.\nExample: `!openbet Alice Bob`"
MSG_A_WINNER_DECLARED_SOON = "A winner will be declared soon."
MSG_PLACE_MANUAL_BET_INSTRUCTIONS = (
    "To place a manual bet:\n`!bet <contestant> <amount>`\nExample: `!bet Alice 100`"
)
MSG_WAIT_FOR_ADMIN_TO_START = "To place a bet, wait for an admin to start a round.\nWhen a round is open, use:\n`!bet <contestant> <amount>`\nExample: `!bet Alice 100`"
MSG_FAILED_SEND_LIVE_MESSAGE = "Failed to send live betting message."

# ---------- Betting Specific Messages ----------
MSG_BET_ALREADY_OPEN = "⚠️ A betting round is already open!"
MSG_BET_LOCKED = (
    "⚠️ Betting is currently locked. Please wait for a winner to be declared."
)
MSG_NO_ACTIVE_BET = "⚠️ There is no active betting round."
MSG_BET_LOCKED_NO_NEW_BETS = "⚠️ Betting is locked. No new bets can be placed."
MSG_BET_LOCKED_WITH_LIVE_LINK = "⚠️ Betting is currently locked. No new bets can be placed.\n\n**Live Message:** [View Current Bets]({live_link})"
MSG_NO_BETS_TO_CLOSE = "⚠️ There are no open or locked bets to close."
MSG_INTERNAL_ERROR_LOCKED = (
    "❌ Internal error: Betting state is inconsistent (locked but not open)."
)
MSG_BETTING_LOCKED_SUMMARY = (
    "Betting is now locked! No more bets can be placed. A winner will be declared soon."
)
MSG_BETTING_TIMER_EXPIRED_SUMMARY = (
    "Time's up! Betting is automatically locked. A winner will be declared soon."
)
MSG_LIVE_BET_INITIAL_DESCRIPTION = (
    "**Contestants:**\n> {contestant1_emoji} **{name1}**\n> {contestant2_emoji} **{name2}**\n\n"
    "No bets yet.\n"
    "**Total Pot:** `0 coins`\n\n"
    f"{MSG_PLACE_MANUAL_BET_INSTRUCTIONS}"
)
MSG_NO_BETS_PLACED_YET = "No bets placed yet."
MSG_NO_ACTIVE_BET_AND_MISSING_ARGS = "⚠️ There is no active betting round. When one is started, use `!bet <amount> <choice>` to place your bet."
MSG_BET_CHANGED = "🔄 <@{user_id}>, your bet of `{amount}` coins has been changed from **{old_contestant}** to **{new_contestant}**!"

# ---------- Embed Titles ----------
TITLE_BETTING_ERROR = "❌ Betting Error"
TITLE_CANNOT_LOCK_BETS = "❌ Cannot Lock Bets"
TITLE_BETS_LOCKED = "🔒 Bets Locked!"
TITLE_BETTING_ROUND_OPENED = "✅ Betting Round Opened"
TITLE_INVALID_BET_FORMAT = "❌ Invalid Bet Format"
TITLE_INVALID_CHOICE = "❌ Invalid Choice"
TITLE_INVALID_AMOUNT = "❌ Invalid Amount"
TITLE_BET_PLACED = "✅ Bet Placed"
TITLE_CANNOT_CLOSE_BETS = "❌ Cannot Close Bets"
TITLE_INTERNAL_ERROR = "❌ Internal Error"
TITLE_BETTING_CHANNEL_SET = "✅ Betting Channel Set"
TITLE_TIMER_TOGGLED = "✅ Timer Toggled"
TITLE_CURRENT_BETS_OVERVIEW = "📊 Current Bets Overview"
TITLE_BETTING_LOCKED_OVERVIEW = "🔒 Betting Locked - Overview"
TITLE_NO_ACTIVE_BETTING_ROUND = "No Active Betting Round"
TITLE_LIVE_BETTING_ROUND = "💸 Live Betting Round"
TITLE_POT_LOST = "💸 Pot Lost!"
TITLE_NO_OPEN_BETTING_ROUND = "⚠️ No Open Betting Round"

# Economy Titles
TITLE_YOUR_BALANCE = "💰 Your Balance"
TITLE_USER_BALANCE = "💰 User Balance"
TITLE_COINS_GIVEN = "✅ Coins Given"
TITLE_COINS_TAKEN = "✅ Coins Taken"
TITLE_INSUFFICIENT_FUNDS = "❌ Insufficient Funds"
TITLE_BALANCE_SET = "✅ Balance Set"

# ---------- Help Titles
TITLE_HELP = "Help"  # Retain for specific command help if implemented
TITLE_BOT_COMMANDS = "🤖 BetBot Commands"  # Updated title
TITLE_ADMIN_COMMANDS = "👑 Admin Commands"  # Retain for adminhelp command
ROLE_BETBOY = "betboy"

# ---------- Help Descriptions
DESC_HELP_NOT_IMPLEMENTED = "Help for `{command_name}` is not yet implemented."
DESC_GENERAL_HELP = (
    "🎉 **Welcome to BetBot!**\n"
    "Start betting rounds, place your bets, and win coins!\n\n"
    "**📋 How Betting Works:**\n"
    "• An admin starts a round between two contestants\n"
    "• Players place bets on their chosen contestant\n"
    "• **Winners split the pot proportionally to their bet size**\n"
    "• If no one bets on the winner, the pot is lost!\n\n"
    "**💰 User Commands:**\n"
    "• `!balance` (or `!bal`) - Check your coin balance\n"
    "• `!bet <contestant> <amount>` (or `!b`) - Place a bet\n"
    "   *Example: `!bet Alice 100`*\n"
    "• `!mybet` (or `!mb`) - Show your current bet\n"
    "• `!bettinginfo` (or `!bi`) - View betting round info\n\n"
    "**🎯 Quick Betting with Reactions:**\n"
    "• Click emoji reactions on the live message to bet instantly\n"
    "• Change bet by clicking a different emoji\n"
    "• Remove bet by removing your reaction\n\n"
    "**🔧 Need Admin Help?**\n"
    "Ask an admin to use `!adminhelp` (or `!ah`) for management commands"
)
DESC_ADMIN_HELP = (
    "🛠️ **Admin Commands Overview**\n"
    "Use `!help` for general betting info and user commands.\n\n"
    "**🔐 Permission Requirements:**\n"
    "• **BetBoy Role**: Betting management commands\n"
    "• **Manage Server**: Economy and bot settings\n\n"
    "**🎲 Betting Management** *(BetBoy role)*\n"
    "• `!openbet <name1> <name2>` (or `!ob`) - Start new betting round\n"
    "• `!lockbets` (or `!lb`) - Lock current bets (stop new bets)\n"
    "• `!declarewinner <winner>` (or `!dw`) - Declare winner for locked bets\n"
    "• `!closebet <winner>` (or `!cb`) - **Quick shortcut: lock + declare + distribute**\n\n"
    "**⚙️ Bot Settings** *(Manage Server)*\n"
    "• `!setbetchannel` (or `!sbc`) - Set main betting channel\n"
    "• `!togglebettimer` (or `!tbt`) - Toggle auto-timer for bets\n\n"
    "**💸 Economy Management** *(Manage Server)*\n"
    "• `!give <@user> <amount>` (or `!g`) - Give coins to user\n"
    "• `!take <@user> <amount>` (or `!t`) - Remove coins from user\n"
    "• `!setbal <@user> <amount>` (or `!sb`) - Set user's balance directly"
)
