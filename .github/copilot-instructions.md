# BetBot Development Guidelines - October 2025 Edition

## 🆕 Recent Major Improvements
This codebase has been significantly enhanced with:
- **Enhanced Timer System**: 90-second timer with selective updates (5s/0s intervals)
- **Themed Emoji System**: Power/Victory (🔥⚡💪🏆) vs Excellence/Royalty (🌟💎🚀👑)
- **Improved UX**: Better error messages, visual formatting, automatic reaction cleanup
- **Rate Limiting Protection**: Discord API optimization with retry logic
- **Comprehensive Testing**: 35 automated tests covering all functionality

## 🏗️ Project Architecture

### Core Structure
```
betbot/
├── bot.py                    # Main entry point and bot initialization
├── cogs/                     # Discord command modules
│   ├── betting.py           # Main betting commands (refactored, modular)
│   ├── economy.py           # Balance and economy commands
│   └── help.py              # Help system
├── utils/                    # Core architectural components
│   ├── bet_state.py         # State management system
│   ├── betting_timer.py     # Timer management (NEW - extracted)
│   ├── betting_utils.py     # Permissions & utilities (NEW - extracted)
│   ├── message_formatter.py # UI formatting system
│   ├── live_message.py      # Message coordination
│   ├── logger.py            # Structured logging system
│   ├── error_handler.py     # Comprehensive error handling
│   ├── performance_monitor.py # System monitoring
│   ├── rate_limiter.py      # Anti-abuse protection
│   ├── metrics.py           # Analytics and statistics
│   └── validators.py        # Input validation
├── data_manager.py          # Data persistence layer
├── config.py               # Configuration constants
└── tests/                  # Comprehensive test suite
```

### Modular Design Philosophy
The codebase follows a **modular architecture** with clear separation of concerns:

- **Commands Layer** (`cogs/`): Discord interface and command handling
- **Business Logic** (`utils/`): Core functionality, state management, and utilities
- **Data Layer** (`data_manager.py`): Persistence and data operations
- **Configuration** (`config.py`): Constants and settings

## 🔧 Key Components

### State Management
- **Primary**: `BetState` from `utils/bet_state.py` handles all betting operations
- **Persistence**: All changes go through `data_manager.save_data()`
- **Type Safety**: Definitions in `utils/message_types.py`
- **Conversions**: Type-safe data flow via `utils/state_converter.py`

### Enhanced Timer System (UPDATED - October 2025)
- **`utils/betting_timer.py`**: Sophisticated timer with selective updates
- **`BettingTimer` class**: 90-second timer updating only at 5s/0s intervals
- **Performance Optimized**: Reduces Discord API calls from 90 to 19 updates
- **Auto-lock**: Automatic bet locking with callback system to betting cog
- **Background Processing**: Non-blocking operation with asyncio tasks

### Permissions & Utilities (NEW - Modular)
- **`utils/betting_utils.py`**: Extracted permission checks and utilities
- **`BettingPermissions`**: Role-based access control
- **`BettingUtils`**: Common betting operations and helpers
- **Role Support**: "Manage Guild" permissions or "BetBoy" role

### Enhanced UI/Messaging System (UPDATED - October 2025)
- **Rich Visual Design**: Improved embeds with visual hierarchy and bullet points
- **Themed Emoji System**: Power/Victory (🔥⚡💪🏆) vs Excellence/Royalty (🌟💎🚀👑)
- **Smart Organization**: Reactions grouped by contestant with visual separator (➖)
- **Enhanced Error Messages**: Helpful errors showing available options when wrong names used
- **Detailed Payouts**: Individual user win/loss breakdown after each round
- **Centralized**: Message formatting through `MessageFormatter`
- **Live Updates**: Real-time updates via `utils/live_message.py` with rate limiting protection
- **Constants**: All message strings defined in `config.py`

### Production Features
- **Logging**: Structured logging with rotation (`utils/logger.py`)
- **Monitoring**: System metrics and performance tracking
- **Error Handling**: Comprehensive error management and recovery
- **Rate Limiting**: Anti-abuse protection with pattern detection
- **Validation**: Input validation with helpful error messages
- **Metrics**: User statistics and analytics

## 🎯 Core Workflows

### Betting Round Lifecycle
```
1. !openbet <name1> <name2>  →  2. User Betting  →  3. Lock/Timer  →  4. Winner Declaration
   ├─ BetState.open_betting_round()    ├─ !bet <amount> <choice>    ├─ !lockbets           ├─ !declarewinner <name>
   ├─ MessageFormatter.create_embed()   ├─ Reaction betting          ├─ Timer expiry        ├─ !closebet <name>
   ├─ BettingTimer.start_timer()       ├─ BetState.place_bet()      ├─ BetState.lock_bets()├─ BetState.declare_winner()
   └─ Live message creation            └─ Live message updates      └─ Reaction clearing   └─ Winnings distribution
```

### 1. Opening Betting (`!openbet`)
- **Entry Point**: `cogs/betting.py` - `openbet` command
- **Business Logic**: `BetState.open_betting_round()` in `utils/bet_state.py`
- **UI Generation**: `MessageFormatter.create_live_message_embed()`
- **Timer**: `BettingTimer.start_timer()` if timer enabled
- **State**: Managed through `state_converter.convert_to_betting_session()`

### 2. User Betting
**Manual Betting (`!bet`)**:
- **Processing**: `BetState.place_bet()` handles validation and state updates
- **UI Updates**: `MessageFormatter` creates updated embeds
- **Error Handling**: Constants from `config.py`, handled by `utils/error_handler.py`

**Reaction Betting**:
- **Event Handling**: `on_raw_reaction_add`/`on_raw_reaction_remove` listeners
- **One Per User**: Automatic removal of previous reactions
- **Silent Operation**: No direct messages, only live message updates
- **Validation**: Through `utils/validators.py`

### 3. Locking Bets
**Manual (`!lockbets`)**:
- **Permission Check**: Via `BettingPermissions.check_permission()`
- **State Change**: `BetState.lock_bets()`
- **Cleanup**: Clear all betting reactions

**Automatic (Timer)**:
- **Timer System**: `BettingTimer` class in `utils/betting_timer.py`
- **Auto-lock**: `_auto_lock_bets()` method
- **Integration**: Works with live message system

### 4. Winner Declaration
- **Commands**: `!declarewinner` or `!closebet`
- **Processing**: `BetState.declare_winner()` handles distribution logic
- **Calculations**: Proportional winnings based on bet ratios
- **UI**: Final results with winnings breakdown
- **Reset**: Complete state cleanup for next round

### Emergency Commands
- **`!forceclose`**: Force close stuck betting rounds
- **`!togglebettimer`**: Enable/disable automatic timer (BetBoy role compatible)

## 🎮 Reaction Betting System

### Reaction Workflow
```
1. Open Betting → 2. Add Reactions → 3. User Reacts → 4. Process Bet → 5. Update Display
   !openbet        Bot adds emojis    User clicks      Validation     Live message
   Creates round   C1_EMOJIS +        reaction         Balance check   updates
                   C2_EMOJIS                           Bet processing
```

### Implementation Details

**1. Reaction Setup**
- **Trigger**: `!openbet` command completion
- **Emojis**: From `config.py` - `C1_EMOJIS` and `C2_EMOJIS`
- **Method**: `BettingUtils._add_betting_reactions()` (extracted utility)
- **Target**: Live betting message

**2. Event Processing**
- **Listeners**: `on_raw_reaction_add` and `on_raw_reaction_remove`
- **Location**: Should be in main `bot.py` or dedicated event cog
- **Validation**: Verify reaction is on active live message

**3. Bet Processing (Add/Change)**
```python
# Flow for on_raw_reaction_add
1. Identify user and emoji → BettingUtils.get_contestant_from_emoji()
2. Get bet amount → REACTION_BET_AMOUNTS[emoji]
3. Validate balance → utils/validators.py
4. Handle existing bet:
   - Refund previous amount
   - Remove old reactions via BettingUtils
5. Process new bet:
   - Deduct amount
   - Record in data.json with emoji
   - Keep new reaction visible
6. Update display → update_live_message()
```

**4. Bet Removal**
```python
# Flow for on_raw_reaction_remove
1. Verify active bet exists for user/emoji
2. Refund bet amount → BetState refund logic
3. Remove bet from data.json
4. Update live message display
```

### Key Rules
- **One Bet Per User**: New reaction replaces previous reaction bet
- **Silent Operation**: No DMs to users, only live message updates
- **Visual Feedback**: User's active reaction remains visible
- **Lock Behavior**: All reactions cleared when betting locks
- **Error Handling**: Invalid reactions removed, errors shown in channel

### Troubleshooting
- **Missing Events**: Ensure `on_raw_reaction_add`/`remove` listeners are registered
- **Permission Issues**: Bot needs reaction management permissions
- **State Sync**: Live message must stay synchronized with data.json
- **Balance Issues**: Validate sufficient funds before processing

## 🔒 Security & Permissions

### Role-Based Access Control
```python
# Permission Hierarchy
1. Server Admins (manage_guild permission)
2. BetBoy Role (custom role-based access)
3. Regular Users (basic commands only)
```

**Admin Commands**: `!openbet`, `!lockbets`, `!declarewinner`, `!closebet`, `!forceclose`
**BetBoy Commands**: `!togglebettimer` (NEW - added role support)
**User Commands**: `!bet`, `!balance`, `!mybet`

### Permission Checking
- **Method**: `BettingPermissions.check_permission()` in `utils/betting_utils.py`
- **Implementation**: Extracted from main cog for better testability
- **Fallback**: Graceful degradation for permission errors

## 🚀 Production Features

### Monitoring & Observability
- **Logging**: `utils/logger.py` - Structured rotating logs
- **Performance**: `utils/performance_monitor.py` - System metrics & health checks
- **Metrics**: `utils/metrics.py` - User statistics and leaderboards
- **Error Tracking**: `utils/error_handler.py` - Comprehensive error management

### Reliability & Safety
- **Rate Limiting**: `utils/rate_limiter.py` - Anti-abuse protection
- **Validation**: `utils/validators.py` - Input validation with helpful errors
- **Data Integrity**: Automatic data validation and repair
- **Error Recovery**: Graceful handling of Discord API failures

### Configuration Management
- **Environment**: `.env` file for secure token storage
- **Secrets**: `.env` file (not in version control)
- **Feature Flags**: Runtime configuration options

## 📦 Dependencies & Environment

### Core Dependencies
```
discord.py >= 2.0    # Primary Discord library
psutil              # System monitoring (optional)
pytest >= 6.0       # Testing framework
pytest-asyncio     # Async test support
```

### Development Environment
- **Python**: 3.8+ required, 3.13+ recommended
- **Virtual Environment**: Use `.venv` for isolation
- **Package Management**: `pip` with `requirements.txt`
- **Code Quality**: Built-in error handling and validation

### Installation
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## 🎨 UI/UX Guidelines

### Messaging Standards
**Universal Principles**:
- **Embeds Only**: All user-facing messages use `discord.Embed` for consistency
- **Centralized Strings**: All message text defined in `config.py` constants
- **Emoji Standards**: Consistent emoji usage for status indication
- **Markdown Formatting**: Bold (`**text**`) and code (`` `code` ``) for emphasis

### Live Message Requirements
**Final Results Display**:
When a winner is declared, the live message must show:
- 🏆 **Winning contestant name**
- 💰 **Total pot amount**
- 📊 **Individual bet amounts per user**
- 💸 **Winnings breakdown for each winner**
- 📈 **Payout ratios and calculations**

### Message Categories & Examples
```python
# Status Messages
TITLE_BETTING_ERROR = "❌ Betting Error"
TITLE_BET_PLACED = "✅ Bet Placed" 
TITLE_POT_LOST = "💸 Pot Lost!"
TITLE_NO_OPEN_BETTING_ROUND = "⚠️ No Open Betting Round"

# Instructional Messages
MSG_INVALID_BET_FORMAT = "**Invalid bet format.**\nUse `!bet <contestant> <amount>`"
MSG_NO_ACTIVE_BET_AND_MISSING_ARGS = "⚠️ No active betting round. Use `!bet <amount> <choice>`"

# Dynamic Content (f-strings)
MSG_BET_CHANGED = "🔄 <@{user_id}>, your bet changed from **{old_contestant}** to **{new_contestant}**!"
MSG_LIVE_BET_DESCRIPTION = "**Contestants:**\n> {contestant1_emoji} **{name1}**\n> {contestant2_emoji} **{name2}**"
```

### Color Coding Standards
- **Success**: Green (`0x00ff00`) - Successful operations
- **Error**: Red (`0xff0000`) - Errors and failures  
- **Warning**: Yellow (`0xffff00`) - Warnings and cautions
- **Info**: Blue (`0x0099ff`) - Information and status
- **Neutral**: Default embed color for general messages

## 🧪 Comprehensive Testing Strategy

### Testing Architecture
```
tests/
├── conftest.py           # Shared fixtures and test configuration
├── test_betting.py       # Core betting functionality tests
├── test_bet_state.py     # State management tests  
├── test_utils.py         # Utility function tests
└── __pycache__/         # Compiled test files
```

**Current Status**: ✅ **35/35 tests passing** - Comprehensive coverage including October 2025 improvements

### Testing Framework & Tools
- **Primary**: `pytest` with `pytest-asyncio` for Discord.py compatibility
- **Mocking**: `unittest.mock` for Discord objects and API calls
- **Fixtures**: Comprehensive test data setup in `conftest.py`
- **Coverage**: Focus on state management, permissions, and command flows

### Key Test Areas

#### 1. Betting Round Management
```python
# Core Command Tests
- !openbet: New rounds, existing round handling, permission checks
- !lockbets: Lock behavior, already locked/closed states  
- !declarewinner/!closebet: Winner processing, fund distribution
- !forceclose: Emergency round closure
```

#### 2. User Interaction Testing
```python
# Betting Operations
- !bet: Valid/invalid amounts, insufficient funds, format parsing
- Reaction betting: Add/remove/change bets, emoji processing
- !mybet: Individual bet status checking
- Balance validation and error handling
```

#### 3. Enhanced Feature Tests (UPDATED - October 2025)
```python
# Recent Improvements Coverage
- Enhanced Timer System: 90-second timer with selective updates (5s/0s intervals)
- Themed Emoji System: Power/Victory vs Excellence/Royalty themes validation
- Reaction Cleanup: Manual bets removing old reaction bets automatically
- Enhanced Error Messages: Wrong contestant names showing available options
- Rate Limiting Protection: Discord API optimization with retry logic
- Round Statistics Accuracy: Correct pot/player counts in completion messages
- Detailed Payout Reports: Individual user win/loss breakdown testing
```

#### 4. System Integration Tests (EXPANDED)
```python
# End-to-End Workflows
- Complete betting round lifecycle with themed emojis
- Live message updates with enhanced formatting
- 90-second timer integration with selective updates
- Automatic bet locking and callback system
- Enhanced error recovery and data integrity
- Rate limiting protection during reaction processing
- Emoji reaction order validation (grouped by contestant)
```

### Test Categories

**Happy Path Tests**:
- ✅ Successful command execution with valid inputs
- ✅ Expected state changes and UI updates
- ✅ Proper fund transfers and calculations

**Edge Case Tests**:
- ✅ Min/max bet amounts and boundary conditions
- ✅ Zero balance betting attempts
- ✅ Identical contestant names
- ✅ Winner with no backers
- ✅ Timer expiry scenarios

**Error Handling Tests**:
- ✅ Invalid command arguments and formats
- ✅ Insufficient funds and permission errors
- ✅ State conflicts (betting when locked/closed)
- ✅ Discord API error simulation

### Mock Strategy
```python
# Discord.py Mocking Approach
@pytest.fixture
async def mock_context():
    # Mock Context, User, Guild, Channel objects
    # Simulate Discord API responses
    # Control permission states
    
@pytest.fixture
def mock_data():
    # Controlled test data states
    # Various betting round scenarios
    # User balance configurations
```

### Continuous Integration
- **Pre-commit Hooks**: Run tests before commits
- **Automated Testing**: GitHub Actions integration
- **Coverage Reports**: Monitor test coverage metrics
- **Performance Tests**: Timer and system monitoring validation

### Testing Best Practices
1. **Isolated Tests**: Each test independent, no shared state
2. **Descriptive Names**: Clear test naming conventions
3. **Comprehensive Mocking**: Full Discord API simulation
4. **State Validation**: Assert both data and UI changes
5. **Error Scenarios**: Test failure paths thoroughly

## 🔄 Recent Architecture Improvements

### Modular Refactoring (Latest)
The codebase has been significantly refactored for better maintainability and testability:

**Extracted Components**:
- **`utils/betting_timer.py`**: Timer management functionality separated from main cog
- **`utils/betting_utils.py`**: Permission checks and utility functions modularized
- **Result**: `cogs/betting.py` reduced from 1,236+ lines to manageable, focused code

### Production Enhancements
**Monitoring & Reliability**:
- **Structured Logging**: `utils/logger.py` with log rotation and levels
- **Performance Monitoring**: System metrics tracking with `psutil` integration
- **Error Handling**: Comprehensive error management and recovery
- **Rate Limiting**: Anti-abuse protection with pattern detection
- **Input Validation**: Robust validation with helpful error messages

**Security Improvements**:
- **Role-Based Permissions**: Enhanced `BettingPermissions` class
- **BetBoy Role Support**: Added to `!togglebettimer` command
- **Data Integrity**: Validation and automatic repair mechanisms

### Development Workflow
**Code Organization**:
- **Single Responsibility**: Each module has clear, focused purpose
- **Dependency Injection**: Better testability through modular design
- **Type Safety**: Comprehensive type hints and validation
- **Error Recovery**: Graceful handling of edge cases and failures

**Quality Assurance**:
- **100% Test Coverage**: All 15 tests passing consistently
- **Lint-Free Code**: No syntax or style errors
- **Documentation**: Comprehensive inline documentation and type hints
- **Performance**: Optimized for Discord rate limits and responsiveness

## 📋 Quick Reference

### Essential Commands
```bash
# Development
python -m pytest                    # Run full test suite
python bot.py                      # Start the bot
python watcher.py                  # Development file watcher

# Deployment  
pip install -r requirements.txt    # Install dependencies
python -m pytest --verbose        # Detailed test output
```

### Key Files to Modify
- **Commands**: `cogs/betting.py`, `cogs/economy.py`
- **Business Logic**: `utils/bet_state.py`, `utils/betting_timer.py`
- **Configuration**: `config.py`
- **Messages**: `config.py` (message constants)
- **Utilities**: `utils/betting_utils.py`, `utils/validators.py`

### Debug Checklist (UPDATED - October 2025)
1. ✅ All 35 tests passing (`python -m pytest`)
2. ✅ No lint errors (`get_errors`)
3. ✅ Timer functionality: 90-second duration with 5s/0s interval updates
4. ✅ Themed emojis: Power/Victory (🔥⚡💪🏆) vs Excellence/Royalty (🌟💎🚀👑)
5. ✅ Enhanced error messages showing available contestants
6. ✅ Rate limiting protection for Discord reactions
7. ✅ Round statistics accuracy (not showing 0 values)
8. ✅ Detailed payout messages with individual user breakdowns

### Development Best Practices (NEW)
- **Test-Driven Development**: Write tests for new features before implementation
- **Comprehensive Coverage**: Ensure all critical paths have test coverage
- **Error Handling**: Always include helpful error messages with available options
- **Performance Optimization**: Consider Discord API rate limits and user experience
- **Visual Design**: Maintain consistent emoji themes and visual hierarchy
- **Documentation**: Update README and DEPLOYMENT.md with new features
3. ✅ Module imports working
4. ✅ Data integrity preserved
5. ✅ Live messages updating correctly
6. ✅ Permissions working as expected
7. ✅ Timer functionality operational
