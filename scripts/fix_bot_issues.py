"""
Utility script to fix common bot issues and cleanup stale states.
Run this if the bot encounters problems or gets stuck in invalid states.
"""

import json
import os
import sys
from pathlib import Path


def load_data():
    """Load data from JSON file."""
    data_file = Path("data.json")
    if data_file.exists():
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data):
    """Save data to JSON file."""
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def clear_timer_state():
    """Clear any stuck timer state."""
    data = load_data()
    if data.get("timer_end_time") is not None:
        print("Clearing stuck timer state...")
        data["timer_end_time"] = None
        save_data(data)
        print("Timer state cleared!")
        return True
    else:
        print("No timer state to clear.")
        return False


def reset_betting_state():
    """Reset betting to a clean state."""
    data = load_data()
    print("Resetting betting state...")
    data["betting"] = {"open": False, "locked": False, "bets": {}, "contestants": {}}
    data["timer_end_time"] = None
    data["live_message"] = None
    data["live_channel"] = None
    data["live_secondary_message"] = None
    data["live_secondary_channel"] = None
    save_data(data)
    print("Betting state reset!")


def show_current_state():
    """Display current bot state."""
    data = load_data()
    print("\n=== Current Bot State ===")
    print(f"Betting Open: {data.get('betting', {}).get('open', False)}")
    print(f"Betting Locked: {data.get('betting', {}).get('locked', False)}")
    print(f"Active Bets: {len(data.get('betting', {}).get('bets', {}))}")
    print(f"Contestants: {len(data.get('betting', {}).get('contestants', {}))}")
    print(f"Timer Active: {data.get('timer_end_time') is not None}")
    print(f"Live Message: {data.get('live_message') is not None}")

    balances = data.get("balances", {})
    print(f"User Balances: {len(balances)} users")
    total_coins = sum(balances.values())
    print(f"Total Coins in Economy: {total_coins:,}")


def main():
    """Main utility menu."""
    while True:
        print("\n=== BetBot Fix Utility ===")
        print("1. Show current state")
        print("2. Clear stuck timer state")
        print("3. Reset betting state (clears all bets)")
        print("4. Run all fixes")
        print("5. Exit")

        choice = input("\nSelect option (1-5): ").strip()

        if choice == "1":
            show_current_state()
        elif choice == "2":
            clear_timer_state()
        elif choice == "3":
            confirm = (
                input("This will clear all active bets. Continue? (y/N): ")
                .strip()
                .lower()
            )
            if confirm == "y":
                reset_betting_state()
            else:
                print("Reset cancelled.")
        elif choice == "4":
            print("Running all fixes...")
            clear_timer_state()
            print("All fixes applied!")
        elif choice == "5":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please select 1-5.")


if __name__ == "__main__":
    # Change to bot directory if not already there
    script_dir = Path(__file__).parent
    if script_dir.name != "betbot":
        betbot_dir = script_dir / "betbot"
        if betbot_dir.exists():
            os.chdir(betbot_dir)
        else:
            print("Error: Could not find betbot directory")
            sys.exit(1)

    main()
