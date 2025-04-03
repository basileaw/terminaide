# terminaide/cursor_manager.py
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

# Quick configuration check - cache the result for performance
@lru_cache(maxsize=1)
def is_cursor_mgmt_enabled():
    return os.environ.get("TERMINAIDE_CURSOR_MGMT", "1").lower() in ("1", "true", "yes", "enabled")

@lru_cache(maxsize=1)
def is_cursor_blink_enabled():
    return os.environ.get("TERMINAIDE_CURSOR_BLINK", "1").lower() in ("1", "true", "yes", "enabled")

# Simplified cursor state - just track if visible
cursor_visible = False

# Optimized cursor control functions - inlined where possible
def show_cursor():
    """Make cursor visible with blinking."""
    global cursor_visible
    if is_cursor_mgmt_enabled() and not cursor_visible:
        sys.stdout.write(CURSOR_SHOW_AND_BLINK)
        sys.stdout.flush()
        cursor_visible = True

def hide_cursor():
    """Make cursor invisible."""
    global cursor_visible
    if is_cursor_mgmt_enabled() and cursor_visible:
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()
        cursor_visible = False

# Simplified stdout patching - focus only on essential behavior
def patched_write(data):
    """Lightweight stdout monitoring for cursor control sequences."""
    global cursor_visible
    if is_cursor_mgmt_enabled() and isinstance(data, str):
        if "\033[?25h" in data:
            cursor_visible = True
        if "\033[?25l" in data:
            cursor_visible = False
    return original_write(data)

sys.stdout.write = patched_write

# Optimized input and readline patches
def patched_input(prompt=""):
    """Optimized patched input with cursor management."""
    if is_cursor_mgmt_enabled():
        show_cursor()
        try:
            return original_input(prompt)
        finally:
            hide_cursor()
    else:
        return original_input(prompt)

def patched_readline(*args, **kwargs):
    """Optimized patched readline with cursor management."""
    if is_cursor_mgmt_enabled():
        show_cursor()
        try:
            return original_readline(*args, **kwargs)
        finally:
            hide_cursor()
    else:
        return original_readline(*args, **kwargs)

# Apply patches
builtins.input = patched_input
sys.stdin.readline = patched_readline

# Streamlined exit manager - only essential functionality
class ExitManager:
    def __init__(self):
        self._original_exit = sys.exit
        sys.exit = self._patched_exit
        
    def _patched_exit(self, code=0):
        """Ensure cursor is hidden before exiting."""
        if is_cursor_mgmt_enabled():
            sys.stdout.write(CURSOR_HIDE)
            sys.stdout.flush()
        self._original_exit(code)

exit_manager = ExitManager()

# Single cleanup handler to minimize overhead
def cleanup():
    """Ensure cursor is hidden when program exits."""
    if is_cursor_mgmt_enabled():
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()

atexit.register(cleanup)

# Optimized signal handler - do minimal work
def signal_handler(sig, frame):
    """Minimal signal handler to hide cursor and re-raise."""
    if is_cursor_mgmt_enabled():
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()
    # Re-raise the signal
    signal.signal(sig, signal.SIG_DFL)
    os.kill(os.getpid(), sig)

# Register only for critical signals
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
    
    # Hide cursor once before running script
    hide_cursor()
    
    try:
        # Configure script args (remove cursor_manager.py from argv)
        sys.argv = sys.argv[1:]
        
        # Load and execute the target script
        spec = importlib.util.spec_from_file_location("__main__", script_path)
        if spec is None:
            print(f"Error: Failed to load script: {script_path}")
            sys.exit(1)
            
        module = importlib.util.module_from_spec(spec)
        sys.modules["__main__"] = module
        
        # Execute the target script
        spec.loader.exec_module(module)
        
    except Exception as e:
        hide_cursor()
        print(f"Error running script: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        hide_cursor()

# Initialize cursor state - hide at import time
hide_cursor()

if __name__ == "__main__":
    run_script()