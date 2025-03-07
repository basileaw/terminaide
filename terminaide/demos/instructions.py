#!/usr/bin/env python3

# terminaide/demos/instructions.py

"""
Instructions demo for terminaide.

This module shows the default instructions that appear when no
client script is specified. It can also be run directly as a demo.
"""

import curses
import time
import signal
import sys
import os

_stdscr = None
_exit_requested = False  # Set by the SIGINT handler when Ctrl+C is pressed.

def handle_exit(sig, frame):
    """Set exit flag on Ctrl+C instead of raising KeyboardInterrupt."""
    global _exit_requested
    _exit_requested = True

def cleanup():
    """Restore terminal state and print goodbye message."""
    if _stdscr is not None:
        try:
            curses.endwin()
            # Just make cursor visible again without changing background
            print("\033[?25h", end="")
            sys.stdout.flush()
        except:
            pass

def instructions(stdscr):
    """Main entry point for the instructions screen."""
    global _stdscr
    _stdscr = stdscr
    signal.signal(signal.SIGINT, handle_exit)
    
    # Setup terminal - force transparent background
    curses.start_color()
    curses.use_default_colors()  # Use terminal's default colors
    curses.init_pair(1, curses.COLOR_WHITE, -1)  # -1 means transparent background
    
    # Ensure the cursor is invisible
    curses.curs_set(0)

    instructions = [
        "DEFAULT CLIENT SCRIPT",
        "====================",
        "",
        "You're seeing this message because no custom client script was configured.",
        "",
        "To use your own client script, provide a path to your script when calling",
        "serve_tty(), for tests:",
        "",
        "serve_tty(client_script='/path/to/your/script.py')",
        "",
        "Your client script should contain the logic you want to run in the",
        "terminal session.",
        "",
        "Press any key (or Ctrl+C) to exit..."
    ]

    # Get terminal dimensions
    height, width = stdscr.getmaxyx()

    # We'll anchor near the top, but horizontally center each line
    start_y = 2

    try:
        # Clear the screen without changing background
        stdscr.clear()
        
        # Print each line with a tiny delay for a "type-in" effect
        for i, line in enumerate(instructions):
            if _exit_requested:
                break
                
            # Calculate the x offset to center horizontally
            x = max((width - len(line)) // 2, 0)
            
            # Use the transparent color pair
            stdscr.addstr(start_y + i, x, line, curses.color_pair(1))
            stdscr.refresh()
            time.sleep(0.05)
            
        # Wait for user to press any key before exiting
        if not _exit_requested:
            stdscr.nodelay(False)  # Make getch blocking
            stdscr.getch()

    except KeyboardInterrupt:
        # Graceful exit if Ctrl+C is pressed
        pass
    finally:
        # Make sure cleanup happens
        cleanup()

def run_demo():
    """Entry point for running the demo from elsewhere."""
    try:
        # Set environment variable to disable background fill
        os.environ.setdefault('NCURSES_NO_SETBUF', '1')
        
        # Use curses wrapper with custom flags
        curses.wrapper(instructions)
    except Exception as e:
        print(f"\n\033[31mError in instructions demo: {e}\033[0m")
    finally:
        cleanup()

if __name__ == "__main__":
    # Set cursor to invisible, but don't change background
    print("\033[?25l", end="")
    
    import os
    # Set environment variable to disable background fill
    os.environ.setdefault('NCURSES_NO_SETBUF', '1')
    
    try:
        curses.wrapper(instructions)
    finally:
        cleanup()