# terminaide/core/index_curses.py

"""
Curses interface implementation for AutoIndex.

This module provides the terminal-based curses menu interface for AutoIndex,
including signal handling, menu display, and user interaction.
"""

import curses
import signal
import sys
import logging
import subprocess
import importlib
from typing import Optional

from .terminascii import terminascii
from .index_api import AutoIndex, AutoMenuItem

logger = logging.getLogger("terminaide")

# Global state for signal handling (curses mode)
stdscr = None
exit_requested = False


def handle_exit(sig, _):
    """Handle SIGINT (Ctrl+C) for clean program exit."""
    global exit_requested
    exit_requested = True


def cleanup():
    """Restore terminal state and print goodbye message."""
    global stdscr
    try:
        if stdscr:
            curses.endwin()
            stdscr = None
        print("\033[?25h\033[2J\033[H", end="")  # Show cursor, clear screen
        print("Thank you for using terminaide")
        print("Goodbye!")
        sys.stdout.flush()
    except:
        pass


def safe_addstr(win, y, x, text, attr=0):
    """Safely add a string to the screen, handling boundary conditions."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    ml = w - x
    if ml <= 0:
        return
    t = text[:ml]
    try:
        win.addstr(y, x, t, attr)
    except:
        curses.error


def launch_menu_item(menu_item: AutoMenuItem) -> bool:
    """
    Launch a menu item (Curses mode only).
    
    Args:
        menu_item: The AutoMenuItem to launch
        
    Returns:
        bool: True to return to menu (always true now)
    """
    if menu_item.function:
        try:
            menu_item.function()
            return True  # Always return to menu
        except Exception as e:
            logger.error(f"Error executing function {menu_item.function.__name__}: {e}")
            return True
            
    elif menu_item.script:
        try:
            # Execute script
            subprocess.run([sys.executable, menu_item.script], 
                          capture_output=False, 
                          check=False)
            return True  # Always return to menu
        except Exception as e:
            logger.error(f"Error executing script {menu_item.script}: {e}")
            return True
            
    elif menu_item.path and not menu_item.is_external():
        # Try to dynamically resolve and launch the path
        try:
            return _launch_from_path(menu_item.path)
        except Exception as e:
            logger.error(f"Error launching path {menu_item.path}: {e}")
            return True
    else:
        logger.warning(f"No launch method defined for {menu_item.title}")
        return True


def _launch_from_path(path: str) -> bool:
    """
    Dynamically resolve and launch a function or module from a path string.
    
    Supports various path formats:
    - "module.function" - imports module and calls function
    - "package.module.function" - imports from package and calls function
    - "function_name" - looks for function in current scope or common modules
    
    Args:
        path: String path to the function or module to launch
        
    Returns:
        bool: True to return to menu (always true now)
    """
    try:
        # Handle dot-separated paths like "terminaide.terminarcade.snake.play_snake"
        if "." in path:
            parts = path.split(".")
            function_name = parts[-1]
            module_path = ".".join(parts[:-1])
            
            # Import the module
            if module_path in sys.modules:
                module = importlib.reload(sys.modules[module_path])
            else:
                module = importlib.import_module(module_path)
            
            # Reset module-level state if present (for games)
            if hasattr(module, 'exit_requested'):
                module.exit_requested = False
            if hasattr(module, 'stdscr'):
                module.stdscr = None
            
            # Get and call the function
            if hasattr(module, function_name):
                function = getattr(module, function_name)
                function()
                return True
            else:
                logger.error(f"Function {function_name} not found in module {module_path}")
                return True
        else:
            # Single name - try common patterns
            # For backwards compatibility with terminarcade games
            if path in ["snake", "tetris", "pong", "asteroids"]:
                # Try top-level terminarcade first, then fall back to old path
                try:
                    module_path = f"terminarcade.{path}"
                    importlib.import_module(module_path)
                except ImportError:
                    module_path = f"terminaide.terminarcade.{path}"
                function_name = f"play_{path}"
                
                if module_path in sys.modules:
                    module = importlib.reload(sys.modules[module_path])
                else:
                    module = importlib.import_module(module_path)
                
                # Reset module-level state
                if hasattr(module, 'exit_requested'):
                    module.exit_requested = False
                if hasattr(module, 'stdscr'):
                    module.stdscr = None
                
                function = getattr(module, function_name)
                function()
                return True
            else:
                logger.warning(f"Don't know how to launch path: {path}")
                return True
                
    except Exception as e:
        logger.error(f"Error launching from path {path}: {e}")
        return True


def show_curses_menu(auto_index: AutoIndex) -> Optional[str]:
    """
    Display the curses menu and launch selected items.

    Args:
        auto_index: The AutoIndex instance to display

    Returns:
        str: The path of the last selected item, or None if user exited
    """
    global exit_requested
    last_selection = None

    # Set up signal handler for clean exit
    signal.signal(signal.SIGINT, handle_exit)

    try:
        while True:
            # Show menu
            choice = curses.wrapper(lambda stdscr: _index_menu_loop(stdscr, auto_index))

            # Exit if requested or choice is exit
            if choice == "exit" or exit_requested or choice is None:
                return last_selection
            
            # If choice is an AutoMenuItem, launch it
            if hasattr(choice, 'launch'):
                last_selection = choice.path
                launch_menu_item(choice)  # Always returns True now
                # Continue the loop (show menu again)
            else:
                # Fallback for non-AutoMenuItem objects
                return choice

    except Exception as e:
        logger.error(f"Error in AutoIndex: {e}")
        return last_selection
    finally:
        exit_requested = True
        cleanup()


def _index_menu_loop(stdscr_param, auto_index: AutoIndex):
    """Main menu interface for curses mode.

    Args:
        stdscr_param: The curses window.
        auto_index: The AutoIndex instance

    Returns:
        str: Selected menu item path or "exit".
    """
    global stdscr, exit_requested
    stdscr = stdscr_param
    exit_requested = False

    # Set up signal handler for SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, handle_exit)

    # Configure terminal
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLUE, -1)    # Title (keeping blue for ASCII art)
    curses.init_pair(2, curses.COLOR_WHITE, -1)   # Instructions & Subtitle (white)
    curses.init_pair(3, curses.COLOR_CYAN, -1)    # Supertitle
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)    # Unselected
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)   # Selected
    curses.init_pair(6, curses.COLOR_GREEN, -1)   # Menu labels (green)
    curses.init_pair(7, curses.COLOR_WHITE, -1)   # Epititle (using white for gray effect)
    curses.init_pair(8, curses.COLOR_WHITE, -1)   # Epititle dim (white with dim = gray)

    curses.curs_set(0)  # Hide cursor

    # Setup screen
    stdscr.clear()
    
    # Current state
    current_group = 0
    current_option = 0
    previous_option = 0
    
    # Get screen dimensions
    my, mx = stdscr.getmaxyx()

    # Generate ASCII art from title
    if auto_index.title:
        ascii_art = terminascii(auto_index.title)
        if ascii_art:
            title_lines = ascii_art.split("\n")
        else:
            title_lines = [auto_index.title]
    else:
        title_lines = ["Index"]

    # Remove any empty trailing lines
    while title_lines and not title_lines[-1].strip():
        title_lines.pop()

    # Calculate layout positions
    current_y = 1

    # Draw supertitle if provided
    if auto_index.supertitle:
        safe_addstr(
            stdscr,
            current_y,
            (mx - len(auto_index.supertitle)) // 2,
            auto_index.supertitle,
            curses.color_pair(3) | curses.A_BOLD,
        )
        current_y += 2

    # Draw title
    for i, line in enumerate(title_lines):
        if len(line) <= mx:
            safe_addstr(
                stdscr,
                current_y + i,
                (mx - len(line)) // 2,
                line,
                curses.color_pair(1) | curses.A_BOLD,
            )
    current_y += len(title_lines) + 1

    # Draw subtitle if provided
    if auto_index.subtitle:
        safe_addstr(
            stdscr,
            current_y,
            (mx - len(auto_index.subtitle)) // 2,
            auto_index.subtitle,
            curses.color_pair(2),  # White for subtitle
        )
        current_y += 2

    # Store menu start position
    menu_start_y = current_y

    def draw_menu():
        """Draw the current menu group."""
        nonlocal current_y
        y_pos = menu_start_y

        # Clear menu area (rough estimate)
        for clear_y in range(menu_start_y, my - 3):
            safe_addstr(stdscr, clear_y, 0, " " * mx)

        current_menu = auto_index.groups[current_group]
        
        # Draw group label
        group_label = current_menu.label
        safe_addstr(
            stdscr,
            y_pos,
            (mx - len(group_label)) // 2,
            group_label,
            curses.color_pair(6) | curses.A_BOLD,  # Green for menu labels
        )
        y_pos += 2

        # Calculate button layout
        options = [item.title for item in current_menu.menu_items]
        button_padding = 4
        button_width = max(len(o) for o in options) + 6
        total_buttons_width = (button_width * len(options)) + (
            button_padding * (len(options) - 1)
        )

        # Center the row of buttons
        start_x = max(0, (mx - total_buttons_width) // 2)
        menu_y = y_pos

        # Draw menu options horizontally
        for i, option in enumerate(options):
            button_x = start_x + (i * (button_width + button_padding))
            if button_x + button_width > mx:
                break  # Skip if button would go off screen
                
            st = curses.color_pair(5) if i == current_option else curses.color_pair(4)

            # Center the text within the button
            text_padding = (button_width - len(option)) // 2
            button_text = (
                " " * text_padding
                + option
                + " " * (button_width - len(option) - text_padding)
            )

            safe_addstr(stdscr, menu_y, button_x, button_text, st | curses.A_BOLD)

        return menu_y + 2

    # Initial menu draw
    draw_menu()

    # Draw epititle at bottom if provided
    if auto_index.epititle:
        # Split epititle into lines for multiline support
        epititle_lines = auto_index.epititle.split('\n')
        
        # Calculate starting position (bottom up)
        total_lines = len(epititle_lines)
        start_y = my - total_lines - 1
        
        # Draw each line centered
        for i, line in enumerate(epititle_lines):
            y_pos = start_y + i
            x_pos = (mx - len(line)) // 2
            safe_addstr(
                stdscr,
                y_pos,
                x_pos,
                line,
                curses.color_pair(8) | curses.A_DIM | curses.A_ITALIC,
            )

    # Main menu loop
    while True:
        if exit_requested:
            break

        # Update menu selection if changed
        if current_option != previous_option:
            draw_menu()
            previous_option = current_option

        stdscr.refresh()

        try:
            # Get keypress
            k = stdscr.getch()

            if k in [ord("q"), ord("Q"), 27]:  # q, Q, or ESC
                break
            elif k in [curses.KEY_LEFT, ord("a"), ord("A")] and current_option > 0:
                current_option -= 1
            elif (
                k in [curses.KEY_RIGHT, ord("d"), ord("D")]
                and current_option < len(auto_index.groups[current_group].menu_items) - 1
            ):
                current_option += 1
            elif k in [curses.KEY_ENTER, ord("\n"), ord("\r")]:
                # Launch the selected menu item
                selected_item = auto_index.groups[current_group].menu_items[current_option]
                return selected_item
            elif len(auto_index.groups) > 1 and _check_cycle_key(k, auto_index):
                # Cycle to next group
                current_group = (current_group + 1) % len(auto_index.groups)
                current_option = 0
                previous_option = -1  # Force redraw
                draw_menu()
        except KeyboardInterrupt:
            break

    return "exit"


def _check_cycle_key(key, auto_index: AutoIndex) -> bool:
    """Check if the pressed key matches the cycle key combination."""
    # For simplicity, we'll just check for the key character
    # In a full implementation, you'd need to track modifier states
    if not hasattr(auto_index, 'cycle_key'):
        return False
        
    try:
        _, cycle_char = auto_index.cycle_key.lower().split("+")
        return key == ord(cycle_char.lower()) or key == ord(cycle_char.upper())
    except (ValueError, IndexError):
        return False