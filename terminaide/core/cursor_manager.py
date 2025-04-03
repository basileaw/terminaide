# terminaide/cursor_manager.py

"""
Cursor visibility manager for terminaide.
This module handles cursor visibility in terminal sessions by:
1. Hiding the cursor by default at startup
2. Making the cursor visible only during input operations
3. Ensuring cursor state is properly restored on exit
4. Enforcing cursor blinking state
When used as a script preloader, it patches Python's input mechanisms and 
then executes the target script with the original arguments.
"""

# IMMEDIATE CURSOR HIDING - This must be the very first code that executes
# to prevent any flash of cursor visibility during module import
import sys
sys.stdout.write("\033[?25l")  # Hide cursor immediately
sys.stdout.flush()

import builtins
import sys
import os
import importlib.util
import signal
import atexit
import traceback
import time

# Store original input functions
original_input = builtins.input
original_readline = sys.stdin.readline
original_write = sys.stdout.write

# ANSI escape sequences for cursor control
CURSOR_SHOW = "\033[?25h"
CURSOR_HIDE = "\033[?25l"
CURSOR_BLINK_ON = "\033[?12h"  # Enable cursor blinking
CURSOR_BLINK_OFF = "\033[?12l"  # Disable cursor blinking

# Check if cursor management is enabled (can be disabled via env var)
CURSOR_MGMT_ENABLED = os.environ.get("TERMINAIDE_CURSOR_MGMT", "1").lower() in ("1", "true", "yes", "enabled")
# Option to control cursor blinking (enabled by default)
CURSOR_BLINK_ENABLED = os.environ.get("TERMINAIDE_CURSOR_BLINK", "1").lower() in ("1", "true", "yes", "enabled")

# Track cursor state to prevent unnecessary operations
cursor_visible = True
cursor_blinking = False
cursor_operations = []  # Track operations to manage cursor state

def set_cursor_blink(enable=True):
    """Set cursor blinking state."""
    global cursor_blinking
    if CURSOR_MGMT_ENABLED and CURSOR_BLINK_ENABLED:
        if enable and not cursor_blinking:
            cursor_operations.append("blink_on")
            sys.stdout.write(CURSOR_BLINK_ON)
            sys.stdout.flush()
            cursor_blinking = True
        elif not enable and cursor_blinking:
            cursor_operations.append("blink_off")
            sys.stdout.write(CURSOR_BLINK_OFF)
            sys.stdout.flush()
            cursor_blinking = False

def show_cursor():
    """Make cursor visible and enable blinking if configured."""
    global cursor_visible
    if CURSOR_MGMT_ENABLED:
        cursor_operations.append("show")
        sys.stdout.write(CURSOR_SHOW)
        sys.stdout.flush()
        cursor_visible = True
        if CURSOR_BLINK_ENABLED:
            set_cursor_blink(True)

def hide_cursor():
    """Make cursor invisible."""
    global cursor_visible
    if CURSOR_MGMT_ENABLED:
        cursor_operations.append("hide")
        # Send multiple hide commands to ensure it's processed
        for _ in range(2):
            sys.stdout.write(CURSOR_HIDE)
            sys.stdout.flush()
        cursor_visible = False

def enforce_cursor_hidden():
    """Force cursor to be hidden regardless of current state."""
    global cursor_visible
    if CURSOR_MGMT_ENABLED:
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()
        cursor_visible = False

def enforce_cursor_state():
    """Enforce the desired cursor state (visible and blinking)."""
    if CURSOR_MGMT_ENABLED:
        if cursor_visible:
            sys.stdout.write(CURSOR_SHOW)
            if CURSOR_BLINK_ENABLED:
                sys.stdout.write(CURSOR_BLINK_ON)
        else:
            sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()

# Improved cleanup that ensures cursor is hidden at exit
def cleanup():
    """Ensure cursor is hidden when program exits."""
    enforce_cursor_hidden()

# Register multiple cleanup handlers to maximize chances of execution
atexit.register(cleanup)

# Handle signals to ensure cursor visibility is properly managed
def signal_handler(sig, frame):
    """Ensure cursor is hidden and re-raise the signal."""
    enforce_cursor_hidden()
    # Re-raise the signal with default handler
    signal.signal(sig, signal.SIG_DFL)
    os.kill(os.getpid(), sig)

# Register signal handlers for common termination signals
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# Patch stdout.write to intercept cursor control sequences
def patched_write(data):
    """Monitor stdout for cursor visibility control sequences."""
    global cursor_visible, cursor_blinking
    if CURSOR_MGMT_ENABLED and isinstance(data, str):
        if CURSOR_SHOW in data:
            cursor_visible = True
            cursor_operations.append("show_external")
        if CURSOR_HIDE in data:
            cursor_visible = False
            cursor_operations.append("hide_external")
        if CURSOR_BLINK_ON in data:
            cursor_blinking = True
            cursor_operations.append("blink_on_external")
        if CURSOR_BLINK_OFF in data:
            cursor_blinking = False
            cursor_operations.append("blink_off_external")
    return original_write(data)

sys.stdout.write = patched_write

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

# Create a special exit handler that runs after other atexit handlers
class ExitManager:
    def __init__(self):
        self._original_exit = sys.exit
        sys.exit = self._patched_exit
        
    def _patched_exit(self, code=0):
        """Ensure cursor is hidden before exiting."""
        enforce_cursor_hidden()
        # Small delay to ensure terminal processes the sequence
        time.sleep(0.01)
        self._original_exit(code)

exit_manager = ExitManager()

def run_script():
    """Execute the target script with the original arguments."""
    if len(sys.argv) < 2:
        print("Error: No script specified")
        sys.exit(1)
    
    script_path = sys.argv[1]
    if not os.path.exists(script_path):
        print(f"Error: Script not found: {script_path}")
        sys.exit(1)
    
    # Aggressive cursor hiding at startup
    enforce_cursor_hidden()
    time.sleep(0.01)  # Small delay to ensure terminal processes the command
    hide_cursor()
    time.sleep(0.01)  # Another small delay for good measure
    
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
        
        # Final enforced hiding before the script runs
        enforce_cursor_hidden()
        
        # Execute the target script
        spec.loader.exec_module(module)
        
        # Final enforced hiding when the script completes
        enforce_cursor_hidden()
    except Exception as e:
        # Hide cursor before displaying the error
        enforce_cursor_hidden()
        print(f"Error running script: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Belt and suspenders approach - ensure hidden state at the end
        enforce_cursor_hidden()

# Additional cleanup to ensure cursor is always properly managed
def ensure_hidden_at_termination():
    """Extra insurance - ensure cursor is hidden at termination."""
    # Apply multiple hide commands with small delays to ensure terminal processes them
    for _ in range(3):
        sys.stdout.write(CURSOR_HIDE)
        sys.stdout.flush()
        time.sleep(0.005)

# Register this extra insurance cleanup
atexit.register(ensure_hidden_at_termination)

# IMPORTANT: Pre-initialize cursor state before anything else happens
# Hide cursor immediately - this call happens at import time
hide_cursor()
# Set initial blinking state when module is imported
if CURSOR_BLINK_ENABLED:
    set_cursor_blink(True)
# Hide again to ensure it's applied
hide_cursor()

if __name__ == "__main__":
    # Ensure cursor is hidden before we do anything else
    enforce_cursor_hidden()
    time.sleep(0.01)  # Small delay to ensure terminal processes the command
    run_script()