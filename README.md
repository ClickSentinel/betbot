# 🎲 BetBot - Discord Betting Bot

> ⚠️ **WARNING: VIBE CODED** - This entire project was 100% vibe coded.

A production-ready Discord bot for interactive betting rounds with dual command/reaction interfaces, real-time updates, and comprehensive administrative tools.

## ✨ Key Features

- **Dual Betting Interface**: Command-based (`!bet`) and themed emoji reactions
- **Smart Timer System**: 90-second rounds with optimized 5-second interval updates
- **Themed Emojis**: Power/Victory (🔥⚡💪🏆) vs Excellence/Royalty (🌟💎🚀👑) themes
- **Batched Live Updates**: Intelligent 5-second batching reduces API calls by 80%
- **Role-Based Permissions**: Flexible admin system with betboy role support
- **Production Ready**: Comprehensive logging, error handling, and 51 automated tests

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ (3.13+ recommended)
- Discord Bot Token with proper permissions
- Virtual environment (recommended)

### Setup Steps
1. **Clone Repository**
   ```bash
   git clone https://github.com/ClickSentinel/betbot.git
   cd betbot
   ```

2. **Create Discord Bot**
   - Visit [Discord Developer Portal](https://discord.com/developers/applications)
   - Create application → Bot tab → Add Bot
   - Enable **Message Content Intent**
   - Copy bot token

3. **Configure Environment**
   ```bash
   # Create .env file
   echo "DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE" > .env
   ```

4. **Install & Run**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate    # Windows | source .venv/bin/activate (Linux/macOS)
   pip install -r requirements.txt
   python bot.py
   ```

5. **Bot Permissions**: Send Messages, Add Reactions, Manage Messages, Read Message History, Embed Links

## 📋 Commands

### 👤 User Commands
| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `!balance` | `!bal` | Check your coin balance | `!balance` |
| `!bet <contestant> <amount>` | `!b` | Place a bet on contestant | `!bet Alice 100` |
| `!mybet` | `!mb` | View your current bet | `!mybet` |
| `!bettinginfo` | `!bi` | Display round information | `!bettinginfo` |
| `!help` | `!h` | Show user help | `!help` |

### 🔧 Admin Commands

#### Betting Management (*betboy role* or *Manage Server*)
| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `!openbet <name1> <name2>` | `!ob` | Start new betting round | `!openbet Alice Bob` |
| `!lockbets` | `!lb` | Lock current round | `!lockbets` |
| `!declarewinner <winner>` | `!dw` | Declare winner & payout | `!declarewinner Alice` |
| `!closebet <winner>` | `!cb` | Lock + declare + payout | `!closebet Alice` |
| `!forceclose` | | Emergency close round | `!forceclose` |
| `!togglebettimer` | `!tbt` | Toggle 90-second auto-timer | `!togglebettimer` |
| `!adminhelp` | `!ah` | Show admin help | `!adminhelp` |

#### Economy Management (*Manage Server* only)
| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `!give <@user> <amount>` | `!g` | Give coins to user | `!give @Alice 1000` |
| `!take <@user> <amount>` | `!t` | Take coins from user | `!take @Alice 500` |
| `!setbal <@user> <amount>` | `!sb` | Set user's balance | `!setbal @Alice 2000` |
| `!manualbet <@user> <amount> <contestant>` | | Place bet for user | `!manualbet @Alice 100 Bob` |
| `!setbetchannel [channel]` | `!sbc` | Set betting channel | `!setbetchannel #betting` |
| `!setbettimer <seconds>` | | Set timer duration | `!setbettimer 300` |

## 🎯 Reaction Betting

**Themed Emoji System**: Click emojis to bet instantly
- **Contestant 1** (Power/Victory): 🔥 100 ⚡ 250 💪 500 🏆 1000
- **Contestant 2** (Excellence/Royalty): 🌟 100 💎 250 🚀 500 👑 1000

**Features**:
- Click emoji to bet → Instant confirmation
- Click different emoji to change bet → Automatic refund
- Remove reaction to cancel bet → Full refund
- Manual commands automatically remove reaction bets

## ⚡ Performance Features

**Intelligent Live Message Batching**: Multiple rapid bet changes are consolidated into single Discord API calls every 5 seconds, reducing API usage from 60+ calls/minute to maximum 12 calls/minute during busy periods while maintaining real-time user experience.

## 🛠️ Development

### Testing
```bash
# Run all tests (51 passing)
python -m pytest

# Run specific test modules
python -m pytest tests/test_live_message_scheduler.py -v  # Scheduler tests
python -m pytest tests/test_betting.py -v                # Betting logic tests

# Development mode with auto-restart
python watcher.py
```

### Project Structure
```
betbot/
├── bot.py                    # Main entry point
├── config.py                 # Configuration & messages
├── data_manager.py          # Data persistence
├── cogs/                    # Command modules
│   ├── betting.py          # Core betting commands
│   ├── economy.py          # Balance management
│   └── help.py             # Help system
├── utils/                   # Business logic (9 modules)
│   ├── bet_state.py        # State management + type definitions
│   ├── betting_timer.py    # Timer system
│   ├── betting_utils.py    # Permissions & utilities
│   ├── bet_ui.py           # UI components
│   ├── live_message.py     # Message updates + state conversion
│   ├── message_formatter.py # UI formatting
│   ├── logger.py           # Logging system
│   ├── error_handler.py    # Error management
│   └── performance_monitor.py # System monitoring
└── tests/                   # Test suite (51 tests)
```

## 🔒 Permission System

- **Users**: `!balance`, `!bet`, `!mybet`, `!bettinginfo`, reaction betting
- **betboy Role**: All user commands + betting management (`!openbet`, `!lockbets`, etc.)
- **Manage Server**: All commands including economy management (`!give`, `!take`, etc.)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Install dependencies: `pip install -r requirements.txt`
4. Run tests: `python -m pytest`
5. Submit pull request

---

<div align="center">

**🎲 BetBot - Where Every Bet Counts! 🎲**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-51%2F51%20Passing-green)](tests/)
[![Code Quality](https://img.shields.io/badge/Vibe%20Coded-100%25-purple)]()

</div>
