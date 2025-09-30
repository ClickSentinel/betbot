# GitHub Copilot Instructions for Discord Bot

This document provides essential guidelines for AI coding agents working on this Discord bot codebase.

## 1. Architecture Overview

The bot is built using `discord.py` and follows a cog-based architecture.
- **`bot.py`**: The main entry point, responsible for initializing the bot and loading cogs.
- **`cogs/`**: Contains modular components (cogs) that encapsulate related commands and event listeners. Each cog is a Python class inheriting from `commands.Cog`.
- **`data_manager.py`**: Handles loading and saving of persistent data (e.g., user balances, betting state) to `data.json`.
- **`config.py`**: Stores configuration variables, including Discord token, emojis, and various message strings.
- **`utils/`**: Contains utility functions, such as `live_message.py` for managing live-updating Discord messages.

## 2. Data Flow and Persistence

- **`data.json`**: All persistent data is stored in this JSON file.
- **`data_manager.py`**: Provides `load_data()` and `save_data()` functions to interact with `data.json`.
- **Data Structure**: The `data.json` typically contains keys like `balances`, `betting`, and `settings`.
  - `balances`: Stores user coin balances.
  - `betting`: Manages the state of active betting rounds (open, locked, bets, contestants).
  - `settings`: Stores bot-specific settings like `enable_bet_timer` and `bet_channel_id`.

**Convention**: Always use `data_manager.load_data()` to retrieve the current state and `data_manager.save_data()` to persist any changes. Avoid direct manipulation of `data.json`.

## 3. Key Components and Conventions

### Cogs
- Each cog should be a class inheriting from `commands.Cog`.
- Commands are defined using the `@commands.command` decorator.
- Helper methods within cogs often start with `_` (e.g., `_send_embed`, `_lock_bets_internal`).

### Live Messages
- The `utils/live_message.py` module is crucial for managing messages that update dynamically in Discord.
- Functions like `update_live_message`, `set_live_message_info`, `get_live_message_info` are used to interact with these messages.
- When updating betting state, ensure `update_live_message` is called to reflect changes in the live embed.

### Error Handling and Embeds
- The bot uses `discord.Embed` for consistent messaging.
- `_send_embed(ctx, title, description, color)` is a common helper for sending formatted messages.
- Various `COLOR_` constants (e.g., `COLOR_ERROR`, `COLOR_SUCCESS`) are defined in `config.py` for consistent styling.

## 4. General Bot Interaction Guidelines
- **Avoid Direct Messages**: The bot should never directly message a user. All communication should occur within server channels.

## 5. Critical Workflows

### Betting Round Lifecycle
1. **`!openbet <name1> <name2>`**: Initiates a new betting round. Sets `betting["open"] = True`.
2. **`!bet <amount> <choice>`**: Users place bets. Updates `data["betting"]["bets"]` and `data["balances"]`. If no betting round is open, the bot will respond with `TITLE_NO_OPEN_BETTING_ROUND` and `MSG_NO_ACTIVE_BET`. If no betting round is open and arguments are missing or invalid, the bot will respond with `TITLE_NO_OPEN_BETTING_ROUND` and `MSG_NO_ACTIVE_BET_AND_MISSING_ARGS`. If a betting round is open but arguments are missing or invalid, the bot will respond with `TITLE_INVALID_BET_FORMAT` and `MSG_INVALID_BET_FORMAT`.
3. **`!lockbets` or Timer Expiry**: Locks the betting round. Sets `betting["open"] = False` and `betting["locked"] = True`. Reactions are cleared from live messages.
4. **`!declarewinner <winner_name>` or `!closebet <winner_name>`**: Declares a winner, distributes winnings, and resets the betting state.

### Timer Management
- The `_run_bet_timer` task in `betting.py` handles automatic bet locking.
- `_cancel_bet_timer` is used to stop the timer.
- `togglebettimer` command enables/disables the timer.

### Reaction Betting Workflow
1.  **`!openbet <name1> <name2>`**: Initiates a new betting round and sends a "live betting message."
2.  **Bot adds reactions**: The bot adds predefined betting emojis (from `config.py`'s `C1_EMOJIS` and `C2_EMOJIS`) to the live message using `_add_betting_reactions`.
3.  **User reacts**: A user reacts to the live message with a betting emoji.
4.  **`on_raw_reaction_add` listener**: An event listener (expected in `bot.py` or a dedicated cog) detects the reaction.
5.  **Process reaction (Adding/Changing Bet)**:
    -   Verifies the reaction is on the active live message.
    -   Identifies the user and emoji.
    -   Uses `_get_contestant_from_emoji` to determine the chosen contestant.
    -   Retrieves the bet amount from `REACTION_BET_AMOUNTS` (in `config.py`).
    -   Checks user balance.
    -   **If the user already has an active reaction bet for this round:**
        -   The previous bet amount is refunded to their balance.
        -   The bot removes the *previous reaction emoji* from the live message.
    -   Deducts the new bet amount, records the new bet in `data.json` (including the emoji used).
    -   The user's *new reaction* remains on the live message, indicating their active bet.
    -   Calls `update_live_message` to refresh the live embed with updated bet totals. **No separate messages should be sent to the user for placing a reaction bet.**
6.  **`on_raw_reaction_remove` listener**: An event listener detects when a user removes a reaction.
7.  **Process reaction (Unbetting)**:
    -   Verifies the reaction is on the active live message and corresponds to an active bet by the user.
    -   Refunds the bet amount to the user's balance.
    -   Removes the bet from `data.json`.
    -   Calls `update_live_message` to refresh the live embed. **No separate messages should be sent to the user for removing a reaction bet.**

**Important Notes:**
-   Users can see their active bet reaction on the live message.
-   All user betting reactions are cleared from the live message when the betting round is locked (`!lockbets` or timer expiry).

**Troubleshooting Reaction Bets:**
-   The most common issue is a missing or incorrectly implemented `on_raw_reaction_add` or `on_raw_reaction_remove` event listener, or they are not properly registered with the bot.

## 6. External Dependencies

- `discord.py`: The primary library for Discord bot interaction.
- No other significant external dependencies beyond standard Python libraries are used.

## 7. Project Structure
- `betbot/`: Main application directory.
- `betbot/cogs/`: Discord cogs.
- `betbot/utils/`: Utility functions.
- `connection.txt`: Contains the bot token (not committed to Git).

## 8. Development Environment
- Python 3.8+ is required.
- Dependencies are managed via `pip`. A `requirements.txt` file should be created if not present, listing `discord.py`.

### Live Message Final Results
- When a winner is declared, the live message should be updated to clearly show:
    - The winning contestant.
    - The total pot amount.
    - The amount bet by each user.
    - How much each winning user gained.

## 9. Messaging Conventions

To maintain a consistent user experience, adhere to the following messaging guidelines:

### General Principles
- **Use Embeds for All User-Facing Messages**: All messages sent to Discord channels should be `discord.Embed` objects for consistent styling and readability.
- **Centralize Messages in `config.py`**: All static message strings and embed titles should be defined as constants in `config.py`. Avoid hardcoding messages directly in cog files.
- **Consistent Emojis**: Use predefined emojis (e.g., `✅`, `❌`, `⚠️`, `🔒`, `🏆`, `💸`) from `config.py` at the beginning of titles or descriptions to convey status or intent quickly.
- **Markdown for Emphasis**: Use Markdown consistently for bolding (`**text**`) and inline code (` `code` `) within embed descriptions.
- **F-strings for Dynamic Content**: Utilize f-strings for inserting dynamic data into message strings.

### Message Formatting Examples (from `config.py`)

```python
# Example General Message
MSG_AMOUNT_POSITIVE = "Amount must be a positive number."
MSG_INVALID_BET_FORMAT = "**Invalid bet format.**\nUse `!bet <contestant> <amount>` or `!bet <amount> <contestant>`.\nExample: `!bet Alice 100`"

# Example Betting Specific Message
MSG_BET_ALREADY_OPEN = "⚠️ A betting round is already open!"
MSG_BETTING_LOCKED_SUMMARY = "Betting is now locked! No more bets can be placed. A winner will be declared soon."

# Example Live Bet Initial Description (multi-line f-string)
MSG_LIVE_BET_INITIAL_DESCRIPTION = (
    "**Contestants:**\n> {contestant1_emoji} **{name1}**\n> {contestant2_emoji} **{name2}**\n\n"
    "No bets yet.\n"
    "**Total Pot:** `0 coins`\n\n"
    f"{MSG_PLACE_MANUAL_BET_INSTRUCTIONS}"
)
MSG_NO_BETS_PLACED_YET = "No bets placed yet."
MSG_NO_ACTIVE_BET_AND_MISSING_ARGS = "⚠️ There is no active betting round. When one is started, use `!bet <amount> <choice>` to place your bet."
MSG_BET_CHANGED = "🔄 <@{user_id}>, your bet of `{amount}` coins has been changed from **{old_contestant}** to **{new_contestant}**!"

# Example Embed Titles
TITLE_BETTING_ERROR = "❌ Betting Error"
TITLE_BET_PLACED = "✅ Bet Placed"
TITLE_POT_LOST = "💸 Pot Lost!"
TITLE_COINS_TAKEN = "✅ Coins Taken"
TITLE_NO_OPEN_BETTING_ROUND = "⚠️ No Open Betting Round"
```

### Guidelines for New Messages
- When creating new user-facing messages, always define them as constants in `config.py`.
- Follow the existing patterns for emoji usage, Markdown, and f-string interpolation.
- Ensure new messages are concise and clearly convey information to the user.

## 10. Testing Guidelines

To ensure the robustness and correctness of this Discord bot, comprehensive testing is crucial. This section outlines key areas, categories, and a suggested approach for generating test cases.

### 10.1. Identify Key Areas for Testing

Focus on the bot's core functionalities, user interactions, and error handling:

-   **Betting Round Management:**
    -   `!openbet`: Starting new rounds, handling existing open/locked rounds.
    -   `!lockbets`: Locking bets, handling already locked/closed rounds.
    -   `!declarewinner`/`!closebet`: Declaring winners, distributing funds, resetting state, handling invalid winners.
-   **User Betting:**
    -   `!bet`: Placing bets (valid/invalid amounts, insufficient funds, correct parsing of `amount` and `choice`).
    -   **Reaction Betting:** Adding/removing reactions, changing bets, insufficient funds, correct processing of emojis.
    -   `!mybet`: Checking individual bet status.
-   **Economy Commands:**
    -   `!balance`: Checking user balances.
    -   `!give`/`!take`: Modifying user balances (valid/invalid amounts, insufficient funds).
    -   `!setbal`: Setting user balances.
-   **Live Message Updates:**
    -   Ensuring the live message updates correctly after `!openbet`, `!bet`, reaction bets, `!lockbets`, and winner declaration.
    -   Correct display of timer, contestant info, bet summaries, and final results.
-   **Timer Functionality:**
    -   `!togglebettimer`: Enabling/disabling the timer.
    -   Automatic locking of bets when the timer expires.
    -   Correct timer countdown display.
-   **Permissions:**
    -   Ensuring admin-only commands (`!openbet`, `!lockbets`, etc.) are restricted to users with `manage_guild` permissions.
-   **Data Persistence:**
    -   Verifying that `data.json` is correctly loaded and saved after state changes.

### 10.2. Categorize Test Cases

For each feature, consider the following categories:

-   **Happy Path:**
    -   Successful execution with valid inputs.
    -   Expected state changes and message outputs.
-   **Edge Cases:**
    -   Minimum/maximum bet amounts.
    -   Betting with zero balance.
    -   Opening a bet with identical contestant names.
    -   Declaring a winner when no one bet on them.
    -   Timer expiring with no bets.
-   **Error Cases:**
    -   Invalid command arguments (e.g., `!bet abc def`).
    -   Insufficient funds for a bet.
    -   Attempting to bet when no round is open or when bets are locked.
    -   Non-admin users attempting admin commands.
    -   Discord API errors (e.g., message not found, HTTP exceptions during reaction removal).

### 10.3. Suggested Testing Framework and Approach

For a Python Discord bot, `pytest` is an excellent choice for writing unit and integration tests. Since `discord.py` interactions involve external services, you'll need to mock Discord objects and API calls.

**Key Techniques:**

-   **Mocking:** Use `unittest.mock` (or `pytest-mock`) to simulate `discord.Message`, `discord.Context`, `discord.User`, `discord.TextChannel`, `bot.get_channel`, `message.send`, `message.add_reaction`, etc. This allows you to test your bot's logic without actually connecting to Discord.
-   **Dependency Injection:** Design your cogs and helper functions to make it easier to inject mocked dependencies.
-   **State Management:** For integration tests, you might want to set up a temporary `data.json` file or mock `load_data`/`save_data` to control the bot's internal state.

### 10.4. Example Test Cases (Conceptual)

#### Example: `!openbet`

-   **Happy Path:**
    -   Test `!openbet Alice Bob` by an admin.
    -   Assert `data["betting"]["open"]` is `True`.
    -   Assert `data["betting"]["contestants"]` contains "Alice" and "Bob".
    -   Assert `_send_embed` was called with `TITLE_BETTING_ROUND_OPENED`.
    -   Assert `_add_betting_reactions` was called on the live message.
    -   If timer enabled, assert `bet_timer_task` is running and `timer_end_time` is set.
-   **Error Cases:**
    -   Test `!openbet Alice Bob` by a non-admin.
    -   Assert `_send_embed` was called with a permission error.
    -   Assert `data["betting"]` state remains unchanged.
    -   Test `!openbet` when a round is already open.
    -   Assert `_send_embed` was called with `MSG_BET_ALREADY_OPEN`.

#### Example: `!bet`

-   **Happy Path:**
    -   Set up an open betting round.
    -   Test `!bet Alice 100`.
    -   Assert user's balance decreased by 100.
    -   Assert `data["betting"]["bets"]` contains the new bet.
    -   Assert `update_live_message` was called.
    -   Assert `_send_embed` was called with `TITLE_BET_PLACED`.
-   **Error Cases:**
    -   Test `!bet` with no open betting round.
    -   Assert `_send_embed` was called with `TITLE_NO_OPEN_BETTING_ROUND` and `MSG_NO_ACTIVE_BET_AND_MISSING_ARGS`.
    -   Test `!bet Alice 100` with insufficient funds.
    -   Assert `_send_embed` was called with "Insufficient balance!" message.
    -   Test `!bet invalid_choice 100`.
    -   Assert `_send_embed` was called with `TITLE_INVALID_BET_FORMAT`.

#### Example: Reaction Betting (`on_raw_reaction_add`)

-   **Happy Path (New Bet):**
    -   Set up an open betting round.
    -   Simulate a user reacting with a valid emoji (e.g., "🔴").
    -   Assert user's balance decreased.
    -   Assert `data["betting"]["bets"]` contains the new bet with the correct emoji.
    -   Assert `update_live_message` was called.
    -   Assert no direct message was sent to the user.
-   **Happy Path (Change Bet):**
    -   Set up an open betting round with an existing bet for a user (e.g., on "Alice" with "🔴").
    -   Simulate the same user reacting with a different valid emoji (e.g., "🔵" for "Bob").
    -   Assert previous bet amount was refunded.
    -   Assert new bet amount was deducted.
    -   Assert `data["betting"]["bets"]` reflects the new bet on "Bob".
    -   Assert `message.remove_reaction` was called for the old emoji ("🔴").
    -   Assert `_send_embed` was called with `MSG_BET_CHANGED`.
    -   Assert `update_live_message` was called.
-   **Error Cases:**
    -   Simulate reaction when betting is locked.
    -   Assert reaction is removed and no bet is placed.
    -   Simulate reaction with insufficient funds.
    -   Assert reaction is removed and an embed is sent to the channel.

## 11. Development Environment
- Python 3.8+ is required.
- Dependencies are managed via `pip`. A `requirements.txt` file should be created if not present, listing `discord.py`.
