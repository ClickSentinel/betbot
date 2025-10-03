import subprocess
import sys
import time
import threading
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class BotRestarter(FileSystemEventHandler):
    def __init__(self, bot_script_name):
        self.bot_script_name = bot_script_name
        self.venv_python_executable = self._get_venv_python_executable()
        self.bot_process = self._start_bot()
        self._restart_timer = None
        self._lock = threading.Lock()

    def _get_venv_python_executable(self):
        """Determines the path to the Python executable within the .venv."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # CHANGE: .venv is now directly inside script_dir (betbot folder)
        venv_path = os.path.join(script_dir, ".venv")

        if sys.platform == "win32":
            python_executable = os.path.join(venv_path, "Scripts", "python.exe")
        else:  # Linux, macOS
            python_executable = os.path.join(venv_path, "bin", "python")

        if not os.path.exists(python_executable):
            print(
                f"Warning: Venv Python not found at '{python_executable}'. Falling back to current Python.",
                file=sys.stderr,
            )
            return sys.executable
        return python_executable

    def _start_bot(self):
        """Starts the bot process."""
        bot_script_full_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), self.bot_script_name
        )
        # Changed print statement to only show the Python executable path
        print(f"Starting bot using {self.venv_python_executable}")
        # Set cwd to the bot's directory so it can find its modules (config, data_manager, etc.)
        return subprocess.Popen(
            [self.venv_python_executable, bot_script_full_path],
            cwd=os.path.dirname(bot_script_full_path),
        )

    def _restart_bot_action(self):
        """Terminates the old bot process and starts a new one."""
        with self._lock:
            if self.bot_process:
                print("Terminating current bot process...")
                self.bot_process.terminate()
                try:
                    self.bot_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(
                        "Bot process did not terminate gracefully, forcefully killing it."
                    )
                    self.bot_process.kill()
                    self.bot_process.wait()
            print("Restarting bot...")
            self.bot_process = self._start_bot()

    def on_modified(self, event):
        # Only react to .py file modifications
        _, ext = os.path.splitext(event.src_path)
        if ext == ".py":
            script_dir_abs = os.path.abspath(os.path.dirname(__file__))
            event_src_path_abs = os.path.abspath(event.src_path)

            # Ensure the modified file is within the watched directory (betbot)
            if event_src_path_abs.startswith(script_dir_abs + os.sep) or event_src_path_abs == script_dir_abs:  # type: ignore
                with self._lock:
                    # Cancel any pending restart to debounce multiple rapid changes
                    if self._restart_timer is not None:
                        self._restart_timer.cancel()

                    print(
                        f"Detected change in {os.path.basename(event.src_path)}, scheduling bot restart..."
                    )
                    # Schedule a restart after a short delay (e.g., 1 second)
                    self._restart_timer = threading.Timer(1.0, self._restart_bot_action)
                    self._restart_timer.start()


if __name__ == "__main__":
    # The watcher will monitor the 'betbot' directory
    watched_path = os.path.dirname(os.path.abspath(__file__))
    bot_main_script = "bot.py"

    event_handler = BotRestarter(bot_main_script)
    observer = Observer()
    observer.schedule(event_handler, watched_path, recursive=True)
    observer.start()
    print(
        f"Watcher started. Monitoring '{watched_path}' for .py file changes. Bot will restart on code changes."
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        with event_handler._lock:
            if event_handler._restart_timer is not None:
                event_handler._restart_timer.cancel()
            if event_handler.bot_process:
                print("Terminating bot process on exit...")
                event_handler.bot_process.terminate()
                try:
                    event_handler.bot_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    event_handler.bot_process.kill()
    observer.join()
