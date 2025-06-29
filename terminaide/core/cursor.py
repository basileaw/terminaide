# cursor.py

"""Cursor visibility manager for terminaide."""
import sys

sys.stdout.write("\033[?25l")  # Hide cursor immediately
sys.stdout.flush()

import builtins, os, importlib.util, signal, atexit, traceback

original_input, original_readline, original_write = (
    builtins.input,
    sys.stdin.readline,
    sys.stdout.write,
)
CURSOR_HIDE, CURSOR_SHOW_AND_BLINK = "\033[?25l", "\033[?25h\033[?12h"

# Cache environment variables at startup for performance
CURSOR_MGMT_ENABLED = os.environ.get("TERMINAIDE_CURSOR_MGMT", "1").lower() in (
    "1",
    "true",
    "yes",
    "enabled",
)
CURSOR_BLINK_ENABLED = os.environ.get("TERMINAIDE_CURSOR_BLINK", "1").lower() in (
    "1",
    "true",
    "yes",
    "enabled",
)


cursor_visible = False


def show_cursor():
    global cursor_visible
    if CURSOR_MGMT_ENABLED and not cursor_visible:
        original_write(CURSOR_SHOW_AND_BLINK)
        sys.stdout.flush()
        cursor_visible = True


def hide_cursor():
    global cursor_visible
    if CURSOR_MGMT_ENABLED and cursor_visible:
        original_write(CURSOR_HIDE)
        sys.stdout.flush()
        cursor_visible = False


def patched_write(data):
    global cursor_visible
    if CURSOR_MGMT_ENABLED and isinstance(data, str) and "\033" in data:
        if "\033[?25h" in data:
            cursor_visible = True
        if "\033[?25l" in data:
            cursor_visible = False
    return original_write(data)


def patched_input(prompt=""):
    if CURSOR_MGMT_ENABLED:
        show_cursor()
        try:
            return original_input(prompt)
        finally:
            hide_cursor()
    return original_input(prompt)


def patched_readline(*args, **kwargs):
    if CURSOR_MGMT_ENABLED:
        show_cursor()
        try:
            return original_readline(*args, **kwargs)
        finally:
            hide_cursor()
    return original_readline(*args, **kwargs)


# Only patch if cursor management is enabled
if CURSOR_MGMT_ENABLED:
    sys.stdout.write, builtins.input, sys.stdin.readline = (
        patched_write,
        patched_input,
        patched_readline,
    )


class ExitManager:
    def __init__(self):
        self._original_exit = sys.exit
        sys.exit = self._patched_exit

    def _patched_exit(self, code=0):
        if CURSOR_MGMT_ENABLED:
            original_write(CURSOR_HIDE)
            sys.stdout.flush()
        self._original_exit(code)


def cleanup():
    if CURSOR_MGMT_ENABLED:
        original_write(CURSOR_HIDE)
        sys.stdout.flush()


def signal_handler(sig, _):
    if CURSOR_MGMT_ENABLED:
        original_write(CURSOR_HIDE)
        sys.stdout.flush()
    signal.signal(sig, signal.SIG_DFL)
    os.kill(os.getpid(), sig)


exit_manager = ExitManager()
atexit.register(cleanup)
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)


def run_script():
    """Execute the target script with cursor management."""
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

        script_dir = os.path.dirname(os.path.abspath(script_path))
        for p in (script_dir, os.getcwd()):
            if p and p not in sys.path:
                sys.path.insert(0, p)

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
