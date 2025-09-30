import os
from dotenv import load_dotenv
import discord # Import discord to use discord.Color

load_dotenv()

# ---------- Bot Configuration ----------
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
STARTING_BALANCE = 1_000

# New: Betting Timer Configuration
ENABLE_BET_TIMER_DEFAULT = False # Default state for the timer feature
BET_TIMER_DURATION = 60          # Duration of the betting timer in seconds
BET_TIMER_UPDATE_INTERVAL = 5    # How often the live message updates during the timer

# ---------- Emojis ----------
SEPARATOR_EMOJI = "➖" # Example separator emoji

# Main contestant display emojis (used in embeds for general display, e.g., !bet overview)
CONTESTANT_EMOJI_1 = "🔴" # Red Circle
CONTESTANT_EMOJI_2 = "🔵" # Blue Circle
CONTESTANT_EMOJIS = [CONTESTANT_EMOJI_1, CONTESTANT_EMOJI_2] # Used for general display

# Emojis for Contestant 1 (Circles) - used for reaction betting
C1_EMOJIS = ["🔴", "🟡", "🔵", "🟣"]
# Emojis for Contestant 2 (Squares) - used for reaction betting
C2_EMOJIS = ["🟥", "🟨", "🟦", "🟪"]

# Mapping of reaction emojis to bet amounts
REACTION_BET_AMOUNTS = {
    "🔴": 100, "🟡": 250, "🔵": 500, "🟣": 1000,
    "🟥": 100, "🟨": 250, "🟦": 500, "🟪": 1000,
}

# ---------- Live Message Keys (for data_manager) ----------
LIVE_MESSAGE_KEY = "live_message"
LIVE_CHANNEL_KEY = "live_channel"
LIVE_SECONDARY_KEY = "live_secondary_message"
LIVE_SECONDARY_CHANNEL_KEY = "live_secondary_channel"

# ---------- Colors for Embeds ----------
COLOR_SUCCESS = discord.Color(0x2ECC71)  # Green
COLOR_INFO = discord.Color(0x3498DB)     # Blue
COLOR_WARNING = discord.Color(0xF1C40F)  # Yellow
COLOR_ERROR = discord.Color(0xE74C3C)    # Red
COLOR_GOLD = discord.Color(0xFFD700)     # Gold
COLOR_DARK_ORANGE = discord.Color(0xFF8C00) # Dark Orange
COLOR_DARK_GRAY = discord.Color(0x607D8B) # Dark Gray

# ---------- General Messages ----------
MSG_AMOUNT_POSITIVE = "Amount must be a positive number."
MSG_AMOUNT_NON_NEGATIVE = "Amount cannot be negative."
MSG_INVALID_BET_FORMAT = "**Invalid bet format.**\nUse `!bet <contestant> <amount>` or `!bet <amount> <contestant>`.\nExample: `!bet Alice 100`"
MSG_NO_CONTESTANTS_DEFINED = "No contestants defined for this round."
MSG_A_WINNER_DECLARED_SOON = "A winner will be declared soon."
MSG_PLACE_MANUAL_BET_INSTRUCTIONS = "To place a manual bet:\n`!bet <contestant> <amount>`\nExample: `!bet Alice 100`"
MSG_WAIT_FOR_ADMIN_TO_START = "To place a bet, wait for an admin to start a round.\nWhen a round is open, use:\n`!bet <contestant> <amount>`\nExample: `!bet Alice 100`"
MSG_FAILED_SEND_LIVE_MESSAGE = "Failed to send live betting message."

# ---------- Betting Specific Messages ----------
MSG_BET_ALREADY_OPEN = "⚠️ A betting round is already open!"
MSG_BET_LOCKED = "⚠️ Betting is currently locked. Please wait for a winner to be declared."
MSG_NO_ACTIVE_BET = "⚠️ There is no active betting round."
MSG_BET_LOCKED_NO_NEW_BETS = "⚠️ Betting is locked. No new bets can be placed."
MSG_NO_BETS_TO_CLOSE = "⚠️ There are no open or locked bets to close."
MSG_INTERNAL_ERROR_LOCKED = "❌ Internal error: Betting state is inconsistent (locked but not open)."
MSG_BETTING_LOCKED_SUMMARY = "Betting is now locked! No more bets can be placed. A winner will be declared soon."
MSG_BETTING_TIMER_EXPIRED_SUMMARY = "Time's up! Betting is automatically locked. A winner will be declared soon."
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
TITLE_HELP = "Help" # Retain for specific command help if implemented
TITLE_BOT_COMMANDS = "🤖 BetBot Commands" # Updated title
TITLE_ADMIN_COMMANDS = "👑 Admin Commands" # Retain for adminhelp command

# ---------- Help Descriptions
DESC_HELP_NOT_IMPLEMENTED = "Help for `{command_name}` is not yet implemented."
DESC_GENERAL_HELP = ( # Updated with bullet points and bold text
    "Welcome to BetBot!\n"
    "Start a betting round between two contestants, place your bets, and win coins!\n\n"
    "**How Betting Works:**\n"
    "- An admin starts a round between two contestants.\n"
    "- Place your bet with `!bet <contestant> <amount>`.\n"
    "- When the round ends, the admin closes it with `!closebet <winner>`.\n"
    "- **Winners split the pot proportionally to their bet size.**\n" # Made bold
    "- If no one bets on the winner, the pot is lost!\n"
    "- Check your balance anytime with `!balance`.\n"
    "- Use `!helpbets` for detailed help.\n\n"
    "🔗 **Current Bet**\n"
    "`!bet <contestant> <amount>`\n"
    "Place a bet on one of the contestants. Example: `!bet Alice 100`\n"
    "`!balance`\n"
    "Check your current coin balance.\n"
    "`!helpbets`\n"
    "Show detailed help for all betting commands."
)
DESC_ADMIN_HELP = ( # Updated to clarify !closebet is a shortcut and include new aliases
    "Admin commands are integrated into the general help description.\n"
    "Please use `!help` for a full overview of how betting works, including admin actions like starting and closing bets.\n\n"
    "**Quick Admin Command List:**\n"
    "`!openbet <name1> <name2>` / `!ob` - Start a new betting round.\n"
    "`!lockbets` / `!lb` - Lock current bets.\n"
    "`!declarewinner <winner_name>` / `!dw` - Declare a winner for locked bets.\n"
    "`!closebet <winner_name>` / `!cb` - **(Shortcut)** Lock bets, declare winner, and distribute coins.\n" # Added (Shortcut)
    "`!setbetchannel` / `!sbc` - Set the main live betting channel.\n"
    "`!togglebettimer` / `!tbt` - Toggle the automatic betting timer.\n"
    "`!give <@user> <amount>` / `!g` - Give coins to a user.\n" # Updated with alias
    "`!take <@user> <amount>` / `!t` - Take coins from a user.\n" # Updated with alias
    "`!setbal <@user> <amount>` / `!sb` - Set a user's balance." # Updated with alias
)