# terminaide/cursor_manager.py

"""
Cursor visibility manager for terminaide.

This module handles cursor visibility in terminal sessions by:
1. Hiding the cursor by default at startup
2. Making the cursor visible only during input operations
3. Ensuring cursor state is properly restored on exit

When used as a script preloader, it patches Python's input mechanisms and 
then executes the target script with the original arguments.
"""

import builtins
import sys
import os
import importlib.util
import signal
import atexit
import traceback

# Store original input functions
original_input = builtins.input
original_readline = sys.stdin.readline

# ANSI escape sequences for cursor control (simplified)
CURSOR_SHOW = "\033[?25h"
CURSOR_HIDE = "\033[?25l"

# Check if cursor management is enabled (can be disabled via env var)
CURSOR_MGMT_ENABLED = os.environ.get("TERMINAIDE_CURSOR_MGMT", "1").lower() in ("1", "true", "yes", "enabled")

# Track cursor state to prevent unnecessary operations
_cursor_visible = True

def show_cursor():
    """Make cursor visible."""
    global _cursor_visible
    if CURSOR_MGMT_ENABLED and not _cursor_visible:
        sys.stdout.write(CURSOR_SHOW)
        sys.stdout.flush()
        _cursor_visible = True

def hide_cursor():
    """Make cursor invisible."""
    global _cursor_visible
    if CURSOR_MGMT_ENABLED and _cursor_visible:
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()
        _cursor_visible = False

# Clean up cursor state on exit
def cleanup():
    """Ensure cursor is visible when program exits."""
    show_cursor()

atexit.register(cleanup)

# Handle signals to ensure cursor visibility is restored
def signal_handler(sig, frame):
    """Restore cursor and re-raise the signal."""
    show_cursor()
    # Re-raise the signal with default handler
    signal.signal(sig, signal.SIG_DFL)
    os.kill(os.getpid(), sig)

# Register signal handlers for common termination signals
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)

# Patch input function
def patched_input(prompt=""):
    """Patched version of input() that manages cursor visibility."""
    show_cursor()
    try:
        return original_input(prompt)
    finally:
        hide_cursor()

# Patch readline method
def patched_readline(*args, **kwargs):
    """Patched version of sys.stdin.readline() that manages cursor visibility."""
    show_cursor()
    try:
        return original_readline(*args, **kwargs)
    finally:
        hide_cursor()

# Apply patches
builtins.input = patched_input
sys.stdin.readline = patched_readline

def run_script():
    """Execute the target script with the original arguments."""
    if len(sys.argv) < 2:
        print("Error: No script specified")
        sys.exit(1)
    
    script_path = sys.argv[1]
    if not os.path.exists(script_path):
        print(f"Error: Script not found: {script_path}")
        sys.exit(1)
    
    # Hide cursor at startup
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
        spec.loader.exec_module(module)
    except Exception as e:
        # Show cursor before displaying the error
        show_cursor()
        print(f"Error running script: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_script()