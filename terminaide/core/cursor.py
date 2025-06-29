# cursor.py

"""
Optimized cursor visibility manager for terminaide.
Handles cursor visibility and blinking with maximum performance.
"""

# IMMEDIATE CURSOR HIDING - This must be the very first code that executes
import sys

sys.stdout.write("\033[?25l")  # Hide cursor immediately
sys.stdout.flush()

# Import only what we need
import builtins
import os
import importlib.util
import signal
import atexit
import traceback
from functools import lru_cache

# Store original input functions
original_input = builtins.input
original_readline = sys.stdin.readline
original_write = sys.stdout.write

# ANSI escape sequences - combined where possible for efficiency
CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW_AND_BLINK = "\033[?25h\033[?12h"  # Combined for performance


@lru_cache(maxsize=1)
def is_cursor_mgmt_enabled():
    return os.environ.get("TERMINAIDE_CURSOR_MGMT", "1").lower() in (
        "1",
        "true",
        "yes",
        "enabled",
    )


@lru_cache(maxsize=1)
def is_cursor_blink_enabled():
    return os.environ.get("TERMINAIDE_CURSOR_BLINK", "1").lower() in (
        "1",
        "true",
        "yes",
        "enabled",
    )


cursor_visible = False


def show_cursor():
    global cursor_visible
    if is_cursor_mgmt_enabled() and not cursor_visible:
        sys.stdout.write(CURSOR_SHOW_AND_BLINK)
        sys.stdout.flush()
        cursor_visible = True


def hide_cursor():
    global cursor_visible
    if is_cursor_mgmt_enabled() and cursor_visible:
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()
        cursor_visible = False


def patched_write(data):
    global cursor_visible
    if is_cursor_mgmt_enabled() and isinstance(data, str):
        if "\033[?25h" in data:
            cursor_visible = True
        if "\033[?25l" in data:
            cursor_visible = False
    return original_write(data)


sys.stdout.write = patched_write


def patched_input(prompt=""):
    if is_cursor_mgmt_enabled():
        show_cursor()
        try:
            return original_input(prompt)
        finally:
            hide_cursor()
    else:
        return original_input(prompt)


def patched_readline(*args, **kwargs):
    if is_cursor_mgmt_enabled():
        show_cursor()
        try:
            return original_readline(*args, **kwargs)
        finally:
            hide_cursor()
    else:
        return original_readline(*args, **kwargs)


builtins.input = patched_input
sys.stdin.readline = patched_readline


class ExitManager:
    def __init__(self):
        self._original_exit = sys.exit
        sys.exit = self._patched_exit

    def _patched_exit(self, code=0):
        if is_cursor_mgmt_enabled():
            sys.stdout.write(CURSOR_HIDE)
            sys.stdout.flush()
        self._original_exit(code)


exit_manager = ExitManager()


def cleanup():
    if is_cursor_mgmt_enabled():
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()


atexit.register(cleanup)


def signal_handler(sig, _):
    if is_cursor_mgmt_enabled():
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()
    signal.signal(sig, signal.SIG_DFL)
    os.kill(os.getpid(), sig)


for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)


def run_script():
    """Execute the target script with minimal overhead."""
    if len(sys.argv) < 2:
        print("Error: No script specified")
        sys.exit(1)

    script_path = sys.argv[1]
    if not os.path.exists(script_path):
        print(f"Error: Script not found: {script_path}")
        sys.exit(1)

    hide_cursor()

    try:
        # Remove cursor_manager.py from argv
        sys.argv = sys.argv[1:]

        # ------------------------------------------------------------------
        # Inject both cwd *and* the directory of the target script so that
        # local-relative imports resolve.
        # ------------------------------------------------------------------
        script_dir = os.path.dirname(os.path.abspath(script_path))
        for p in (script_dir, os.getcwd()):
            if p and p not in sys.path:
                sys.path.insert(0, p)
        # ------------------------------------------------------------------

        spec = importlib.util.spec_from_file_location("__main__", script_path)
        if spec is None:
            print(f"Error: Failed to load script: {script_path}")
            sys.exit(1)

        module = importlib.util.module_from_spec(spec)
        sys.modules["__main__"] = module
        spec.loader.exec_module(module)

    except Exception as e:
        hide_cursor()
        print(f"Error running script: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        hide_cursor()


hide_cursor()

if __name__ == "__main__":
    run_script()
