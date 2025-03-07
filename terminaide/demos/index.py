#!/usr/bin/env python3

# terminaide/demos/index.py

"""
Index demo for terminaide.

This module displays a simple menu-based interface that serves as an index
for the available demos. It's designed to be a terminal-based equivalent 
of a web page with links to other demo terminals.
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
            print("\033[?25l\033[2J\033[H", end="")  # Clear screen
            try:
                rows, cols = _stdscr.getmaxyx()
            except:
                rows, cols = 24, 80
            msg = "Thank you for using terminaide"
            print("\033[2;{}H{}".format((cols - len(msg)) // 2, msg))
            print("\033[3;{}H{}".format((cols - len("Goodbye!")) // 2, "Goodbye!"))
            sys.stdout.flush()
        except:
            pass

def safe_addstr(stdscr, y, x, text, attr=0):
    """Safely add a string to the screen, avoiding edge errors."""
    height, width = stdscr.getmaxyx()
    
    # Check if the position is valid
    if y < 0 or y >= height or x < 0 or x >= width:
        return
    
    # Truncate text if it would go off the screen
    max_len = width - x
    if max_len <= 0:
        return
    
    display_text = text[:max_len]
    
    try:
        stdscr.addstr(y, x, display_text, attr)
    except curses.error:
        # Ignore any remaining errors (like trying to write to the bottom-right cell)
        pass

def draw_horizontal_line(stdscr, y, x, width, attr=0):
    """Safely draw a horizontal line."""
    for i in range(width):
        safe_addstr(stdscr, y, x + i, " ", attr)

def index_menu(stdscr):
    """Display a simple menu-based interface similar to a web page."""
    global _stdscr
    _stdscr = stdscr
    signal.signal(signal.SIGINT, handle_exit)
    
    # Set up colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLUE, -1)      # Title
    curses.init_pair(2, curses.COLOR_WHITE, -1)     # Normal text
    curses.init_pair(3, curses.COLOR_CYAN, -1)      # Card header
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Button
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE) # Selected button
    curses.init_pair(6, curses.COLOR_GREEN, -1)     # Info box
    
    # Hide cursor
    curses.curs_set(0)
    stdscr.clear()
    
    # Define menu options
    options = [
        "Terminal 1 (Snake Game)",
        "Terminal 2 (Pong Game)",
        "Show Instructions",
        "Exit"
    ]
    
    current_option = 0
    
    while True:
        if _exit_requested:
            break
            
        stdscr.clear()
        
        # Get screen dimensions
        max_y, max_x = stdscr.getmaxyx()
        
        # Draw title
        title = "Terminaide Test Server"
        safe_addstr(stdscr, 1, (max_x - len(title)) // 2, title, curses.color_pair(1) | curses.A_BOLD)
        title_line = "=" * len(title)
        safe_addstr(stdscr, 2, (max_x - len(title_line)) // 2, title_line, curses.color_pair(1))
        
        # Draw card
        card_width = min(max_x - 4, 70)
        card_y = 4
        card_x = (max_x - card_width) // 2
        
        # Draw card background
        for i in range(5):  # Card height
            draw_horizontal_line(stdscr, card_y + i, card_x, card_width, curses.color_pair(2) | curses.A_REVERSE)
        
        # Add blue border to left side of card
        for i in range(5):
            safe_addstr(stdscr, card_y + i, card_x, "│", curses.color_pair(1) | curses.A_BOLD)
            
        # Card content
        card_title = "Custom Terminal Index"
        safe_addstr(stdscr, card_y, card_x + 2, card_title, curses.color_pair(3) | curses.A_BOLD)
        safe_addstr(stdscr, card_y + 2, card_x + 2, "This is a terminal-based menu for accessing different demos.", curses.color_pair(2))
        safe_addstr(stdscr, card_y + 3, card_x + 2, "Use arrow keys to navigate and Enter to select an option.", curses.color_pair(2))
        
        # Draw options (buttons)
        option_y = card_y + 7
        for i, option in enumerate(options):
            option_style = curses.color_pair(5) if i == current_option else curses.color_pair(4)
            padding = " " * 3
            button_text = f"{padding}{option}{padding}"
            safe_addstr(stdscr, option_y + i*2, (max_x - len(button_text)) // 2, button_text, option_style | curses.A_BOLD)
        
        # Check if there's enough room for the info box
        info_y = option_y + len(options)*2 + 2
        if info_y + 3 < max_y:
            # Draw info box
            info_width = min(max_x - 4, 70)
            info_x = (max_x - info_width) // 2
            
            # Draw info box background
            for i in range(3):  # Info box height
                draw_horizontal_line(stdscr, info_y + i, info_x, info_width, curses.color_pair(6) | curses.A_REVERSE)
            
            # Info box content
            info_text = "Press 'q' to quit at any time"
            safe_addstr(stdscr, info_y + 1, (max_x - len(info_text)) // 2, info_text, curses.color_pair(6) | curses.A_REVERSE | curses.A_BOLD)
        
        # Draw instructions at the bottom if there's room
        if max_y > 3:
            nav_text = "↑/↓: Navigate   Enter: Select"
            safe_addstr(stdscr, max_y - 2, (max_x - len(nav_text)) // 2, nav_text)
        
        # Refresh the screen
        stdscr.refresh()
        
        # Get user input
        try:
            key = stdscr.getch()
            
            if key in [ord('q'), ord('Q'), 27]:  # q, Q, or ESC
                break
                
            elif key == curses.KEY_UP and current_option > 0:
                current_option -= 1
                
            elif key == curses.KEY_DOWN and current_option < len(options) - 1:
                current_option += 1
                
            elif key in [curses.KEY_ENTER, ord('\n'), ord('\r')]:
                if current_option == 0:  # Terminal 1 (Snake)
                    return "snake"
                elif current_option == 1:  # Terminal 2 (Pong)
                    return "pong"
                elif current_option == 2:  # Instructions
                    return "instructions"
                elif current_option == 3:  # Exit
                    break
                    
        except KeyboardInterrupt:
            break
            
    return "exit"

def run_demo():
    """Entry point for running the index demo."""
    try:
        choice = curses.wrapper(index_menu)
        
        # Based on the choice, we can give a hint about what to run next
        if choice == "snake":
            print("\n\033[1;34mTo run the Snake game, use:\033[0m")
            print("from terminaide.demos import play_snake; play_snake()")
        elif choice == "pong":
            print("\n\033[1;34mTo run the Pong game, use:\033[0m")
            print("from terminaide.demos import play_pong; play_pong()")
        elif choice == "instructions":
            print("\n\033[1;34mTo show the instructions, use:\033[0m")
            print("from terminaide.demos import show_instructions; show_instructions()")
        
    except Exception as e:
        print(f"\n\033[31mError in index demo: {e}\033[0m")
    finally:
        cleanup()

if __name__ == "__main__":
    # Set cursor to invisible using ansi 
    print("\033[?25l\033[2J\033[H", end="")
    try:
        curses.wrapper(index_menu)
    finally:
        cleanup()