# BetBot Development Guidelines

## ️ Project Architecture

### Core Structure
```
betbot/
├── bot.py                    # Main entry point and bot initialization
├── cogs/                     # Discord command modules
│   ├── betting.py           # Main betting commands and reaction handling
│   ├── economy.py           # Balance and economy commands
│   └── help.py              # Help system
├── utils/                    # Core architectural components
│   ├── bet_state.py         # State management system + type definitions
│   ├── betting_timer.py     # Timer management (90s with 5s/0s updates)
│   ├── betting_utils.py     # Permissions & utilities
│   ├── message_formatter.py # UI formatting system
│   ├── live_message.py      # Message coordination + batched updates (5s intervals)
│   ├── logger.py            # Structured logging system
│   ├── error_handler.py     # Comprehensive error handling
│   └── performance_monitor.py # System monitoring
├── data_manager.py          # Data persistence layer
├── config.py               # Configuration constants
└── tests/                  # 127 automated tests
    ├── test_betting.py        # Core betting logic (26 tests)
    ├── test_multiple_reactions.py # Reaction batching (4 tests)
    ├── test_economy_cog.py    # Economy management (11 tests)
    ├── test_help_cog.py       # Help system (9 tests)
    ├── test_live_message.py   # Live message updates (13 tests)
    ├── test_error_handling.py # Error handling (6 tests)
    └── [10 more modules]      # Comprehensive edge case coverage
```

## 🔧 Key Components

### State Management (`utils/bet_state.py`)
- **BetState class**: Central state management for all betting operations
- **TypedDict definitions**: Type safety for betting data structures
- **Core methods**: `open_betting_round()`, `place_bet()`, `lock_bets()`, `declare_winner()`
- **Persistence**: All changes saved via `data_manager.save_data()`

### Timer System (`utils/betting_timer.py`)
- **BettingTimer class**: 90-second countdown with updates at 5s/0s intervals only
- **Auto-lock functionality**: Automatic bet locking with callback system
- **Performance optimized**: Reduces API calls from 90 to 19 updates per timer

### Live Message Updates (`utils/live_message.py`)
- **LiveMessageScheduler**: Batches message updates every 5 seconds
- **Dual strategy**: Immediate updates for major changes, batched for bet changes
- **API optimization**: Reduces Discord calls by ~80% during high activity

### Permissions (`utils/betting_utils.py`)
- **BettingPermissions**: Role-based access control
- **Supported roles**: "Manage Guild" permission or "betboy" role
- **BettingUtils**: Common validation and utility functions

### UI/Messaging (`utils/message_formatter.py`)
- **MessageFormatter class**: Centralized embed creation and formatting
- **Themed emojis**: Power/Victory (🔥⚡💪🏆) vs Excellence/Royalty (🌟💎🚀👑)
- **Visual organization**: Grouped reactions with separators
- **Constants**: All message strings in `config.py`

## 🎯 Core Workflows

### Betting Lifecycle
```
!openbet → User Betting → Lock/Timer → !declarewinner → Payouts
```

### Commands & Permissions
**Admin Commands** (Manage Guild or "betboy" role):
- `!openbet <name1> <name2>` - Start betting round
- `!lockbets` - Lock betting manually
- `!declarewinner <name>` / `!closebet <name>` - Declare winner and distribute winnings
- `!forceclose` - Emergency close
- `!togglebettimer` - Enable/disable 90s auto-timer

**User Commands**:
- `!bet <amount> <choice>` - Place manual bet with enhanced UX
- `!betall <choice>` / `!allin <choice>` - Bet all coins
- Reaction betting - Click emoji to bet preset amounts
- `!mybet` - Check current bet with comprehensive status
- `!balance` - Check coin balance with active bet context

## 🎮 Reaction Betting System

### Key Features
- **Preset Amounts**: Emoji reactions bet predefined amounts (config.py: `REACTION_BET_AMOUNTS`)
- **One Bet Per User**: New reaction replaces previous bet automatically
- **Visual Feedback**: User's active reaction stays visible
- **Batched Updates**: Live message updates every 5 seconds via `LiveMessageScheduler`
- **Enhanced UX**: Balance warnings, rich confirmations, typo-resistant commands

### Event Handling (`cogs/betting.py`)
- **Listeners**: `on_raw_reaction_add` / `on_raw_reaction_remove`
- **Validation**: Check active betting round and valid emojis
- **Processing**: `_process_bet()` handles bet placement/changes
- **Cleanup**: All reactions cleared when betting locks

### Reaction Batching System (NEW)
- **Problem Solved**: Multiple rapid reactions from same user causing conflicts
- **Solution**: 1-second delay batching system that processes only the final reaction
- **Key Components**:
  - `_pending_reaction_bets`: Dict tracking latest reaction per user
  - `_reaction_timers`: Dict tracking processing timers per user
  - `_process_batched_reaction()`: Processes final bet after delay
  - `_delayed_reaction_processing()`: Handles 1-second delay with cancellation
- **Behavior**: User spam-clicking multiple emojis → Only last emoji processed → All others removed
- **Visual Result**: Clean message showing only user's final selection

## 🔒 Key Data Structures

### BetState Class (`utils/bet_state.py`)
**Core Methods**:
- `open_betting_round(contestant1, contestant2)` - Start new round
- `place_bet(user_id, contestant, amount, emoji=None)` - Process bet
- `lock_bets()` - Lock betting
- `declare_winner(winner_name)` - Calculate and distribute winnings
- `get_betting_session()` - Get current state for UI

### Data Persistence (`data_manager.py`)
- **save_data(data)** - Write to data.json with backup
- **load_data()** - Read from data.json with validation
- **Auto-backup** - Creates .bak files before writes

## ⚙️ Configuration (`config.py`)

### Essential Constants
- **Colors**: `COLOR_SUCCESS`, `COLOR_ERROR`, `COLOR_INFO` - Embed colors
- **Emojis**: `C1_EMOJIS`, `C2_EMOJIS` - Reaction emoji sets
- **Bet Amounts**: `REACTION_BET_AMOUNTS` - Emoji → amount mapping
- **Messages**: `TITLE_*`, `MSG_*` - All user-facing text
- **Timer**: `BET_TIMER_DURATION` - 90 seconds default

## 🧪 Testing

### Test Structure
- **127 automated tests** covering all functionality
- **Key test files**: `test_betting.py`, `test_multiple_reactions.py`, `test_economy_cog.py`, `test_help_cog.py`
- **Run tests**: `python -m pytest`
- **Coverage**: All betting workflows, reaction batching, timer system, live message batching, error handling

## 🎨 Development Notes

### Key Implementation Details
- **All user messages use `discord.Embed`** for consistency
- **Message constants in `config.py`** - never hardcode strings
- **Live message updates batched every 5 seconds** to reduce API calls
- **Timer updates only at 5s/0s intervals** for performance
- **Reaction betting uses preset amounts** from `REACTION_BET_AMOUNTS`
- **All state changes go through `data_manager.save_data()`**
- **Enhanced UX**: Balance warnings, typo-resistant matching, rich error messages
- **Smart features**: `!betall` command, improved bet change confirmations
- **Reaction batching**: Advanced system handles multiple rapid reactions intelligently
- **Edge case handling**: Comprehensive error handling and user feedback improvements

## 📋 Quick Reference

### Development Commands
```bash
python -m pytest                   # Run all 127 tests
python bot.py                      # Start the bot
python watcher.py                  # Development file watcher
```

### Debug Checklist
1. ✅ All 58 tests passing (`python -m pytest`)
2. ✅ Timer: 90s with 5s/0s updates only
3. ✅ Live messages: 5-second batched updates
4. ✅ Permissions: "Manage Guild" or "betboy" role
5. ✅ Data persistence: All changes via `data_manager.save_data()`
