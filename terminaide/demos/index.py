#!/usr/bin/env python3

# terminaide/demos/index.py

"""
Termin-Arcade menu for terminaide.

This module displays a simple menu-based interface that serves as an entry point
for the available arcade games. When a user selects a game, it directly launches
that game.
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
        "Snake",
        "Tetris",
        "Pong"
    ]
    
    current_option = 0
    prev_option = 0  # Track previous selection for optimized redrawing
    
    # Initial full draw
    stdscr.clear()
    
    # Get screen dimensions
    max_y, max_x = stdscr.getmaxyx()
    
    # Draw ASCII art title
    title_lines = [
        "████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗      █████╗ ██████╗  ██████╗ █████╗ ██████╗ ███████╗",
        "╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝",
        "   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║     ███████║██████╔╝██║     ███████║██║  ██║█████╗  ",
        "   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║     ██╔══██║██╔══██╗██║     ██╔══██║██║  ██║██╔══╝  ",
        "   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║     ██║  ██║██║  ██║╚██████╗██║  ██║██████╔╝███████╗",
        "   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═════╝ ╚══════╝"
    ]
    
    # Simpler ASCII art title for smaller terminals
    simple_title_lines = [
        " _____              _         _                   _      ",
        "|_   _|__ _ __ _ __ (_)_ __   /_\\  _ __ ___ __ _  _| | ___ ",
        "  | |/ _ \\ '__| '_ \\| | '_ \\ //_\\\\| '__/ __/ _` |/ _` |/ _ \\",
        "  | |  __/ |  | | | | | | | /  _ \\ | | (_| (_| | (_| |  __/",
        "  |_|\\___|_|  |_| |_|_|_| |_\\_/ \\_\\_|  \\___\\__,_|\\__,_|\\___|"
    ]
    
    # Simplest ASCII art title for very small terminals
    very_simple_title = [
        "==============================",
        "||     TERMIN-ARCADE       ||",
        "=============================="
    ]
    
    # Choose which title to display based on terminal width
    if max_x >= 90:
        title_to_use = title_lines
    elif max_x >= 60:
        title_to_use = simple_title_lines
    else:
        title_to_use = very_simple_title
        
    # Draw the title
    for i, line in enumerate(title_to_use):
        if len(line) <= max_x:
            safe_addstr(stdscr, 1 + i, (max_x - len(line)) // 2, line, curses.color_pair(1) | curses.A_BOLD)
    
    start_y = 2 + len(title_to_use)
    
    # Simple instructions
    instruction = "Use ↑/↓ to navigate, Enter to select, Q to quit"
    safe_addstr(stdscr, start_y + 2, (max_x - len(instruction)) // 2, instruction, curses.color_pair(2))
    
    # Calculate the length of the longest option for consistent button widths
    max_option_length = max(len(option) for option in options)
    
    # Draw initial buttons
    option_y = start_y + 5
    for i, option in enumerate(options):
        option_style = curses.color_pair(5) if i == current_option else curses.color_pair(4)
        # Calculate padding needed to make all buttons the same width
        padding = " " * 3
        # Center the text within a fixed-width area based on the longest option
        space_needed = max_option_length - len(option)
        left_space = space_needed // 2
        right_space = space_needed - left_space
        button_text = f"{padding}{' ' * left_space}{option}{' ' * right_space}{padding}"
        safe_addstr(stdscr, option_y + i*2, (max_x - len(button_text)) // 2, button_text, option_style | curses.A_BOLD)
    
    # Main loop
    while True:
        if _exit_requested:
            break
            
        # Only update the buttons that changed
        if current_option != prev_option:
            # Update the previously selected button with consistent width
            option_style = curses.color_pair(4) | curses.A_BOLD
            space_needed = max_option_length - len(options[prev_option])
            left_space = space_needed // 2
            right_space = space_needed - left_space
            prev_button_text = f"{padding}{' ' * left_space}{options[prev_option]}{' ' * right_space}{padding}"
            safe_addstr(stdscr, option_y + prev_option*2, (max_x - len(prev_button_text)) // 2, 
                      prev_button_text, option_style)
            
            # Update the newly selected button with consistent width
            option_style = curses.color_pair(5) | curses.A_BOLD
            space_needed = max_option_length - len(options[current_option])
            left_space = space_needed // 2
            right_space = space_needed - left_space
            new_button_text = f"{padding}{' ' * left_space}{options[current_option]}{' ' * right_space}{padding}"
            safe_addstr(stdscr, option_y + current_option*2, (max_x - len(new_button_text)) // 2, 
                      new_button_text, option_style)
            
            # Update prev_option for next iteration
            prev_option = current_option
        
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
                if current_option == 0:      # Snake
                    return "snake"
                elif current_option == 1:    # Tetris
                    return "tetris"
                elif current_option == 2:    # Pong
                    return "pong"
                    
        except KeyboardInterrupt:
            break
            
    return "exit"

def run_demo():
    """Entry point for running the index demo."""
    try:
        # Get the user's choice from the menu
        choice = curses.wrapper(index_menu)
        
        # If the user chose to exit, just show the goodbye message
        if choice == "exit":
            cleanup()
            return
            
        # Reset the terminal before launching a new game
        if _stdscr is not None:
            curses.endwin()
        
        # Import and run the selected demo
        if choice == "snake":
            # Import here to avoid circular imports
            from terminaide.demos import play_snake
            play_snake()
        elif choice == "tetris":
            from terminaide.demos import play_tetris
            play_tetris()
        elif choice == "pong":
            from terminaide.demos import play_pong
            play_pong()
        
    except Exception as e:
        print(f"\n\033[31mError in index demo: {e}\033[0m")
    finally:
        # We only call cleanup if there was an error or unexpected exit
        # For normal navigation to other games, the cleanup is handled by those games
        if choice == "exit":
            cleanup()

if __name__ == "__main__":
    # Set cursor to invisible using ansi 
    print("\033[?25l\033[2J\033[H", end="")
    try:
        curses.wrapper(index_menu)
    finally:
        cleanup()