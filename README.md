# BetBot - A Discord Betting Bot

BetBot is a feature-rich Discord bot that allows users to place bets on custom contests, manage their virtual currency, and interact with live betting rounds.

## Features

-   **Custom Betting Rounds**: Admins can open betting rounds between two contestants.
-   **Flexible Betting**: Users can place bets using commands (`!bet <contestant> <amount>`) or by reacting to live messages.
-   **Live Updates**: Betting messages update in real-time to show current bets, total pot, and timer status.
-   **Economy System**: Users have a virtual balance that is updated based on betting outcomes.
-   **Admin Controls**: Commands for managing betting rounds, setting channels, toggling timers, and adjusting user balances.
-   **Detailed Results**: Final betting results display winners, total pot, individual bets, and winnings.

## Setup and Installation

Follow these steps to get your BetBot up and running:

### 1. Clone the Repository

```bash
git clone https://github.com/ClickSentinel/betbot.git
cd betbot
```

### 2. Create a Discord Bot Application

1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2.  Click "New Application" and give your bot a name.
3.  Navigate to the "Bot" tab, click "Add Bot," and confirm.
4.  **Crucially, enable all three "Privileged Gateway Intents" (PRESENCE INTENT, SERVER MEMBERS INTENT, MESSAGE CONTENT INTENT) under the "Privileged Gateway Intents" section.**
5.  Copy your bot's token. You will need this in the next step.

### 3. Environment Configuration

Create a `.env` file in the `betbot` directory (the same directory as `bot.py`) and add your bot token:

```
DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
```

Replace `YOUR_BOT_TOKEN_HERE` with the token you copied from the Discord Developer Portal.

### 4. Install Dependencies

It's highly recommended to use a virtual environment.

```bash
python -m venv venv
./venv/Scripts/activate # On Windows
source venv/bin/activate # On macOS/Linux
pip install -r requirements.txt
```

### 5. Run the Bot

```bash
python bot.py
```

The bot should now be online in your Discord server.

## Bot Usage

### General Commands

-   `!balance`: Check your current coin balance.
-   `!bet <contestant> <amount>` / `!bet <amount> <contestant>`: Place a bet on one of the contestants. Example: `!bet Alice 100`.
-   `!mybet`: Show your current bet in the active round.
-   `!bettinginfo`: Display current betting round information.

### Admin Commands (Requires `Manage Guild` permission)

-   `!openbet <name1> <name2>` / `!ob`: Start a new betting round between two contestants.
-   `!lockbets` / `!lb`: Lock the current betting round, preventing new bets.
-   `!declarewinner <winner_name>` / `!dw`: Declare a winner for a locked betting round and distribute coins.
-   `!closebet <winner_name>` / `!cb`: (Shortcut) Locks bets, declares a winner, and distributes coins.
-   `!setbetchannel [channel]`: Set the channel where live betting messages will appear. If no channel is specified, the current channel is used.
-   `!togglebettimer` / `!tbt`: Toggle the automatic betting timer on or off.
-   `!setbettimer <seconds>`: Set the duration of the automatic betting timer in seconds.
-   `!give <@user> <amount>` / `!g`: Give a specified amount of coins to a user.
-   `!take <@user> <amount>` / `!t`: Take a specified amount of coins from a user.
-   `!setbal <@user> <amount>` / `!sb`: Set a user's coin balance to a specific amount.
-   `!manualbet <@user> <amount> <contestant>`: Manually place a bet for another user.

### Reaction Betting

When a betting round is open, you can also place bets by reacting to the live betting message:

-   **Place/Change Bet**: React with one of the designated contestant emojis (e.g., 🔴, 🔵) to place a bet. If you react with a different emoji, your previous bet will be updated.
-   **Unbet**: Remove your reaction to cancel your bet.

## Development

### Project Structure

```
betbot/
├── __init__.py
├── bot.py
├── config.py
├── data_manager.py
├── data.json
├── watcher.py
├── .gitignore
├── requirements.txt
├── cogs/
│   ├── __init__.py
│   ├── betting.py
│   ├── economy.py
│   └── help.py
└── utils/
    ├── __init__.py
    └── live_message.py
```

### Running with Watcher

If you are using `watcher.py` for development, you can run it as follows:

```bash
python watcher.py
```

This will automatically restart the bot when changes are detected in the codebase.

## Contributing

Feel free to fork the repository, make improvements, and submit pull requests. Please ensure your code adheres to the existing style and conventions.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details (if applicable).
