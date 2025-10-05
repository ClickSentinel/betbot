# 🎲 BetBot - Discord Betting Bot

> ⚠️ **WARNING: VIBE CODED** - This entire project was 100% vibe coded.

A production-ready Discord bot for interactive betting rounds with dual command/reaction interfaces, real-time updates, and comprehensive administrative tools.

## ✨ Key Features

- **Dual Betting Interface**: Command-based (`!bet`) and themed emoji reactions
- **Smart Timer System**: 90-second rounds with optimized 5-second interval updates
- **Themed Emojis**: Power/Victory (🔥⚡💪🏆) vs Excellence/Royalty (🌟💎🚀👑) themes
- **Batched Live Updates**: Intelligent 5-second batching reduces API calls by 80%
- **Role-Based Permissions**: Flexible admin system with betboy role support
- **Production Ready**: Comprehensive logging, error handling, and 129 automated tests
- **Smart Reaction Handling**: Advanced batching system for multiple rapid reactions

- **Per-Session Timers & Live Messages**: Each session created via `!openbet` or `!opensession` has its own live message posted to the configured bet channel and an independent timer; live embeds show precise remaining time.

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
   # Create .env file (⚠️ NEVER commit this file to git!)
   echo "DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE" > .env
   ```
   
   > 🔒 **Security Note:** Keep your bot token secure! Never commit `.env` to git or share your token publicly. See [SECURITY.md](SECURITY.md) for details.

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
| `!balance` | `!bal` | Check your coin balance & active bets | `!balance` |
| `!bet <contestant> <amount>` | `!b` | Place a bet on contestant | `!bet Alice 100` |
| `!betall <contestant>` | `!allin` | **NEW:** Bet all your coins | `!betall Alice` |
| `!mybet` | `!mb` | View your current bet & status | `!mybet` |
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
- Click emoji to bet → Instant confirmation with balance warnings
- Click different emoji to change bet → Rich before/after confirmation
- Remove reaction to cancel bet → Full refund
- Manual commands automatically remove reaction bets
- **Smart Rapid Reaction Handling**: Multiple quick reactions are batched - only your final choice is processed
- **Clean Visual Feedback**: All reactions are cleaned up, showing only your final selection

## ✨ Enhanced User Experience

**Smart Betting Features**:
- **All-in Commands**: `!betall Alice` or `!allin Alice` to bet all your coins
- **Typo-Resistant**: 'alice', 'ALICE', 'Ali' all work for 'Alice'
- **Balance Warnings**: Alerts when betting 70%+ of your balance (non-blocking)
- **Rich Error Messages**: Clear breakdown of balance vs required amount
- **Bet Change Confirmation**: See before/after with net change calculation
- **Enhanced Status**: `!mybet` and `!balance` show comprehensive betting context

**Improved Messaging**:
- Context-aware error messages with helpful suggestions
- Locked vs no-round distinction in command responses
- Live message links in informational commands
- Detailed winner payouts with individual user breakdowns

## ⚡ Performance Features

**Intelligent Live Message Batching**: Multiple rapid bet changes are consolidated into single Discord API calls every 5 seconds, reducing API usage from 60+ calls/minute to maximum 12 calls/minute during busy periods while maintaining real-time user experience.

**Advanced Reaction Processing**: When users rapidly click multiple reaction emojis, the system intelligently batches these interactions with a 1-second delay, processes only the final selection, and cleanly removes all other reactions. This prevents bet conflicts and provides smooth visual feedback.

## 🔧 Recent Improvements (October 2025)

**Code Quality & Maintainability**:
- Applied Black code formatting across entire codebase for consistent styling
- Fixed import path structure for proper module resolution
- Organized all test files into proper directory structure
- All 129 tests passing with clean codebase

**Enhanced Development Experience**:
- Improved error handling and debugging capabilities  
- Better file organization with tests, scripts, and docs properly structured
- Fixed bot startup issues with correct relative imports
- Enhanced development tooling and scripts

## 🛠️ Development

### Testing
```bash
# Run all tests (129 passing)
python -m pytest

# Run specific test modules
python -m pytest tests/test_betting.py -v                # Core betting logic tests
python -m pytest tests/test_multiple_reactions.py -v     # Reaction batching tests
python -m pytest tests/test_economy_cog.py -v            # Economy system tests
python -m pytest tests/test_help_cog.py -v               # Help system tests
python -m pytest tests/test_live_message.py -v           # Live message tests

# Development mode with auto-restart
python scripts/watcher.py
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
├── utils/                   # Business logic (8 modules)
│   ├── bet_state.py        # State management + type definitions
│   ├── betting_timer.py    # Timer system
│   ├── betting_utils.py    # Permissions & utilities
│   ├── live_message.py     # Message updates + state conversion
│   ├── message_formatter.py # UI formatting
│   ├── logger.py           # Logging system
│   ├── error_handler.py    # Error management
│   └── performance_monitor.py # System monitoring
├── tests/                   # Test suite (129 tests)
│   ├── test_betting.py         # Core betting logic
│   ├── test_multiple_reactions.py # Reaction batching system
│   ├── test_economy_cog.py     # Economy management
│   ├── test_help_cog.py        # Help system
│   ├── test_live_message.py    # Live message updates
│   ├── test_error_handling.py  # Error handling
│   └── [13 more test modules]  # Comprehensive coverage
├── docs/                    # Documentation
│   ├── DEPLOYMENT.md       # Production deployment guide
│   ├── CHANGELOG_v2.1.md   # Version 2.1 improvements
│   ├── QUICK_REFERENCE.md  # Quick feature reference
│   └── [other docs]        # Additional documentation
└── scripts/                 # Utility scripts
    ├── watcher.py          # Development auto-restart
    └── fix_bot_issues.py   # Issue resolution utility
```

## 🔒 Permission System

- **Users**: `!balance`, `!bet`, `!mybet`, `!bettinginfo`, reaction betting
- **betboy Role**: All user commands + betting management (`!openbet`, `!lockbets`, etc.)
- **Manage Server**: All commands including economy management (`!give`, `!take`, etc.)

## 📚 Documentation

### Core Documentation
- **README.md** (this file) - Main project overview and quick start guide
- **SECURITY.md** - Security best practices and guidelines
- **docs/DEPLOYMENT.md** - Production deployment guide with testing procedures
- **docs/CHANGELOG_v2.1.md** - Comprehensive changelog for version 2.1 improvements

### Reference Guides  
- **docs/QUICK_REFERENCE.md** - Quick guide for users, developers, and admins
- **.github/copilot-instructions.md** - Development guidelines and architecture overview

### Future Enhancements
- **docs/MULTI_BET_OVERVIEW.md** - Comprehensive analysis of multiple concurrent betting sessions
- **docs/MULTI_BET_TECHNICAL_SPEC.md** - Technical specification for multi-bet implementation

### Utility Scripts
- **scripts/watcher.py** - Development file watcher with auto-restart
- **scripts/fix_bot_issues.py** - Issue resolution and debugging utility

### 🎯 Quick Navigation
- **For Users**: Start with this README, then docs/QUICK_REFERENCE.md
- **For Developers**: Check .github/copilot-instructions.md and docs/CHANGELOG_v2.1.md  
- **For Deployment**: Use docs/DEPLOYMENT.md for production setup
- **For Security**: Read SECURITY.md for best practices

## 🔒 Security

**Your bot token is sensitive!** Follow these guidelines:

- ✅ **DO**: Store token in `.env` file (automatically ignored by git)
- ✅ **DO**: Use environment variables for all secrets
- ❌ **DON'T**: Commit `.env`, tokens, or sensitive data to git
- ❌ **DON'T**: Share your bot token publicly or in screenshots

See [SECURITY.md](SECURITY.md) for comprehensive security guidelines, including:
- Token security best practices
- Pre-commit hooks for preventing leaks
- File permissions and access control
- What to do if your token is compromised

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Install dependencies: `pip install -r requirements.txt`
4. **Run security audit**: `python scripts/security_audit.py` (must pass all checks)
5. Run tests: `python -m pytest`
6. Ensure no sensitive data in commits (use pre-commit hook)
7. Submit pull request

**Security Requirements:**
- No hardcoded tokens or secrets
- Use environment variables for all sensitive data
- Verify `.env` and `data.json` are not committed
- Review `git diff` before committing

---

<div align="center">

**🎲 BetBot - Where Every Bet Counts! 🎲**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-129%2F129%20Passing-green)](tests/)
[![Code Quality](https://img.shields.io/badge/Vibe%20Coded-100%25-purple)]()

</div>
