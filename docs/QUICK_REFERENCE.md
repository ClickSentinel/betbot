# 🎯 BetBot Command Reference

Quick reference for all BetBot commands and usage patterns.

## 👤 User Commands

### Balance & Betting
| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `!balance` | `!bal` | Check your coin balance & active bets | `!balance` |
| `!bet <contestant> <amount>` | `!b` | Place a bet on contestant | `!bet Alice 100` |
| `!betall <contestant>` | `!allin` | Bet all your coins | `!betall Alice` |
| `!mybet` | `!mb` | View your current bet & status | `!mybet` |

### Information
| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `!bettinginfo` | `!bi` | Display round information | `!bettinginfo` |
| `!help` | `!h` | Show user help | `!help` |

## 🔧 Admin Commands

### Betting Management
*Requires "betboy" role or "Manage Server" permission*

| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `!openbet <name1> <name2>` | `!ob` | Start new betting round | `!openbet Alice Bob` |
| `!lockbets` | `!lb` | Lock current round | `!lockbets` |
| `!declarewinner <winner>` | `!dw` | Declare winner & payout | `!declarewinner Alice` |
| `!closebet <winner>` | `!cb` | Lock + declare + payout | `!closebet Alice` |
| `!forceclose` | | Emergency close round | `!forceclose` |
| `!togglebettimer` | `!tbt` | Toggle 90-second auto-timer | `!togglebettimer` |
| `!adminhelp` | `!ah` | Show admin help | `!adminhelp` |

### Economy Management
*Requires "Manage Server" permission*

| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `!give <@user> <amount>` | `!g` | Give coins to user | `!give @Alice 1000` |
| `!take <@user> <amount>` | `!t` | Take coins from user | `!take @Alice 500` |
| `!setbal <@user> <amount>` | `!sb` | Set user's balance | `!setbal @Alice 2000` |
| `!manualbet <@user> <amount> <contestant>` | | Place bet for user | `!manualbet @Alice 100 Bob` |

### Configuration
*Requires "Manage Server" permission*

| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `!setbetchannel [channel]` | `!sbc` | Set betting channel | `!setbetchannel #betting` |
| `!setbettimer <seconds>` | | Set timer duration | `!setbettimer 300` |

## 🎯 Reaction Betting

**Quick Betting**: Click emoji reactions to bet instantly

### Contestant 1 (Power/Victory Theme)
- 🔥 **100 coins**
- ⚡ **250 coins** 
- 💪 **500 coins**
- 🏆 **1000 coins**

### Contestant 2 (Excellence/Royalty Theme)
- 🌟 **100 coins**
- 💎 **250 coins**
- 🚀 **500 coins**
- 👑 **1000 coins**

### Reaction Behavior
- **Click emoji** → Places bet immediately
- **Change reaction** → Updates bet to new amount/contestant
- **Remove reaction** → Cancels bet (full refund)
- **Multiple rapid clicks** → System processes only your final selection

## 🔒 Permission Levels

### Regular Users
- Balance checking (`!balance`, `!mybet`)
- Betting (`!bet`, `!betall`, reaction betting)
- Information (`!bettinginfo`, `!help`)

### Betting Admins ("betboy" role)
- All user commands
- Betting management (`!openbet`, `!lockbets`, `!declarewinner`, etc.)
- Timer controls (`!togglebettimer`)

### Server Admins ("Manage Server" permission)
- All betting admin commands
- Economy management (`!give`, `!take`, `!setbal`)
- Configuration (`!setbetchannel`, `!setbettimer`)

## 🚀 Development Commands

```bash
# Run the bot
python bot.py

# Development with auto-restart
python scripts/watcher.py

# Run all tests
python -m pytest

# Run specific test modules
python -m pytest tests/test_betting.py -v
```

## 💡 Quick Tips

- **Fuzzy matching**: "alice", "ALICE", "Ali" all work for "Alice"
- **Balance warnings**: Get notified when betting 70%+ of your balance
- **Bet changes**: See before/after confirmation with net change
- **Timer**: 90-second rounds with updates at 5-second intervals
- **Live updates**: Bet changes update the live message every 5 seconds