#!/usr/bin/env python3
"""
Start the bot with comprehensive logging to file
This captures ALL output including Discord.py logs, bot logs, and errors
"""
import sys
import os
from datetime import datetime

# Redirect all output to both console and log file


class TeeOutput:
    def __init__(self, *files):
        self.files = files

    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()

    def flush(self):
        for f in self.files:
            f.flush()


# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

# Create timestamped log file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file_path = os.path.join(log_dir, f"bot_full_{timestamp}.log")

# Open log file
log_file = open(log_file_path, "w", encoding="utf-8")

# Redirect stdout and stderr
original_stdout = sys.stdout
original_stderr = sys.stderr
sys.stdout = TeeOutput(sys.stdout, log_file)
sys.stderr = TeeOutput(sys.stderr, log_file)

print(f"🚀 Starting bot with full logging to: {log_file_path}")
print(f"⏰ Started at: {datetime.now()}")
print("=" * 80)

try:
    # Import and run the bot
    from bot import main

    main()
except Exception as e:
    print(f"💥 Bot crashed with error: {e}")
    import traceback

    traceback.print_exc()
finally:
    print("=" * 80)
    print(f"🏁 Bot stopped at: {datetime.now()}")

    # Restore original stdout/stderr
    sys.stdout = original_stdout
    sys.stderr = original_stderr

    # Close log file
    log_file.close()

    print(f"📝 Full logs saved to: {log_file_path}")
