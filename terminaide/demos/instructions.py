#!/usr/bin/env python3

import curses
import time

#set cursor to invisible using ansi 
print("\033[?25l\033[2J\033[H", end="")

def main(stdscr):
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
        # Print each line with a tiny delay for a "type-in" effect
        for i, line in enumerate(instructions):
            # Calculate the x offset to center horizontally
            x = max((width - len(line)) // 2, 0)
            stdscr.addstr(start_y + i, x, line)
            stdscr.refresh()
            time.sleep(0.05)

        # Wait for user to press any key before exiting
        stdscr.getch()

    except KeyboardInterrupt:
        # Graceful exit if Ctrl+C is pressed
        pass

if __name__ == "__main__":
    curses.wrapper(main)
