# terminaide/core/index_curses.py

"""
Curses-based index page functionality for Terminaide.

This module provides the CursesIndex class which creates terminal-based
navigable menu pages with ASCII art titles, keyboard navigation, and optional
grouping for organizing terminal routes.
"""

import curses
import signal
import sys
import logging
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

from .index_html import MenuItem, MenuGroup
from .utils import termin_ascii
import subprocess
import importlib

logger = logging.getLogger("terminaide")

# Global state for signal handling
stdscr = None
exit_requested = False


def handle_exit(sig, frame):
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


class CursesMenuItem(MenuItem):
    """Extended MenuItem that can launch functions or scripts."""
    
    def __init__(self, path: str, title: str, function=None, script=None, launcher_args=None):
        """
        Initialize a CursesMenuItem.
        
        Args:
            path: The URL path (for compatibility with MenuItem)
            title: Display title for the menu item
            function: Python function to execute when selected
            script: Python script path to execute when selected
            launcher_args: Additional arguments for the launcher
        """
        super().__init__(path, title)
        self.function = function
        self.script = script
        self.launcher_args = launcher_args or {}
    
    def launch(self) -> bool:
        """
        Launch this menu item.
        
        Returns:
            bool: True to return to menu (always true now)
        """
        if self.function:
            try:
                self.function()
                return True  # Always return to menu
            except Exception as e:
                logger.error(f"Error executing function {self.function.__name__}: {e}")
                return True
                
        elif self.script:
            try:
                # Execute script
                subprocess.run([sys.executable, self.script], 
                              capture_output=False, 
                              check=False)
                return True  # Always return to menu
            except Exception as e:
                logger.error(f"Error executing script {self.script}: {e}")
                return True
                
        elif self.path and not self.is_external():
            # Try to dynamically resolve and launch the path
            try:
                return self._launch_from_path(self.path)
            except Exception as e:
                logger.error(f"Error launching path {self.path}: {e}")
                return True
        else:
            logger.warning(f"No launch method defined for {self.title}")
            return True
    
    def _launch_from_path(self, path: str) -> bool:
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


class CursesMenuGroup:
    """Group of CursesMenuItem objects with a label."""
    
    def __init__(self, label: str, options: List[Dict[str, Any]]):
        """
        Initialize a menu group.
        
        Args:
            label: The label shown for this group of menu items
            options: List of menu items as dictionaries
        """
        self.label = label
        self.menu_items = []
        
        for item in options:
            if isinstance(item, CursesMenuItem):
                self.menu_items.append(item)
            else:
                # Create CursesMenuItem from dict
                self.menu_items.append(CursesMenuItem(
                    path=item.get('path', ''),
                    title=item.get('title', ''),
                    function=item.get('function'),
                    script=item.get('script'),
                    launcher_args=item.get('launcher_args', {})
                ))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "label": self.label,
            "options": [item.to_dict() for item in self.menu_items],
        }


class CursesIndex:
    """
    Configuration for a curses-based index/menu page.

    CursesIndex allows creating navigable menu pages with ASCII art titles,
    keyboard navigation, and optional grouping. It can be used as an alternative
    to HtmlIndex for terminal-based interfaces.
    """

    def __init__(
        self,
        # Content
        menu: Union[List[Dict[str, Any]], Dict[str, Any]],
        subtitle: Optional[str] = None,
        epititle: Optional[str] = None,
        # Title/ASCII options
        title: Optional[str] = None,
        page_title: Optional[str] = None,
        ascii_art: Optional[str] = None,
        supertitle: Optional[str] = None,
        # Assets (not used in curses but kept for API compatibility)
        preview_image: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize a CursesIndex.

        Args:
            menu: Either:
                - A list of menu groups (for single menu or when cycle_key not needed)
                - A dict with 'groups' and 'cycle_key' keys (for multiple menus with cycling)
                  Example: {"cycle_key": "shift+g", "groups": [{"label": "...", "options": [...]}]}
            subtitle: Text paragraph below the title
            epititle: Optional text shown below the menu items
            title: Text to convert to ASCII art using ansi-shadow font
            page_title: Not used in curses but kept for API compatibility
            ascii_art: Pre-made ASCII art (alternative to generated)
            supertitle: Regular text above ASCII art
            preview_image: Not used in curses but kept for API compatibility

        Raises:
            ValueError: If menu is empty or has invalid structure
        """
        # Parse menu structure (reuse HtmlIndex logic)
        if isinstance(menu, dict):
            # Dict format with cycle_key
            if "groups" not in menu:
                raise ValueError("Menu dict must contain 'groups' key")
            if "cycle_key" not in menu:
                raise ValueError("Menu dict must contain 'cycle_key' key")

            menu_groups = menu["groups"]
            self.cycle_key = menu["cycle_key"]

            # Validate cycle_key
            self._validate_cycle_key()
        else:
            # List format (no cycle_key)
            menu_groups = menu
            self.cycle_key = "shift+g"  # Default, won't be used if single group

        # Validate menu structure
        if not menu_groups:
            raise ValueError("Menu must contain at least one group")

        for i, group in enumerate(menu_groups):
            if not isinstance(group, dict):
                raise ValueError(f"Menu group at index {i} must be a dictionary")
            if "label" not in group:
                raise ValueError(
                    f"Menu group at index {i} missing required 'label' key"
                )
            if "options" not in group:
                raise ValueError(
                    f"Menu group at index {i} missing required 'options' key"
                )
            if not isinstance(group["options"], list):
                raise ValueError(f"Menu group at index {i} 'options' must be a list")
            if not group["options"]:
                raise ValueError(
                    f"Menu group at index {i} must have at least one option"
                )

        # Convert menu groups
        self.groups = [CursesMenuGroup(g["label"], g["options"]) for g in menu_groups]

        # Store text/title options
        self.subtitle = subtitle
        self.epititle = epititle
        self.title = title
        self.page_title = page_title or title or "Index"
        self.ascii_art = ascii_art
        self.supertitle = supertitle

        # Handle preview image (not used in curses but stored for compatibility)
        if preview_image:
            self.preview_image = Path(preview_image)
        else:
            self.preview_image = None

    def _validate_cycle_key(self) -> None:
        """Validate the cycle key format."""
        valid_modifiers = {"shift", "ctrl", "alt", "meta"}
        parts = self.cycle_key.lower().split("+")

        if len(parts) != 2:
            raise ValueError(
                f"cycle_key must be in format 'modifier+key', got: {self.cycle_key}"
            )

        modifier, key = parts
        if modifier not in valid_modifiers:
            raise ValueError(
                f"Invalid modifier in cycle_key. Must be one of: {valid_modifiers}"
            )

        if not key or len(key) != 1:
            raise ValueError(
                f"Invalid key in cycle_key. Must be a single character, got: {key}"
            )

    def get_all_menu_items(self) -> List[CursesMenuItem]:
        """
        Get all menu items as a flat list.

        Returns:
            List of all CursesMenuItem objects across all groups
        """
        all_items = []
        for group in self.groups:
            all_items.extend(group.menu_items)
        return all_items

    def _index_menu_loop(self, stdscr_param):
        """Main menu interface.

        Args:
            stdscr_param: The curses window.

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

        # Generate or use existing ASCII art
        if self.ascii_art:
            title_lines = self.ascii_art.split("\n")
        elif self.title:
            ascii_art = termin_ascii(self.title)
            if ascii_art:
                title_lines = ascii_art.split("\n")
            else:
                title_lines = [self.title]
        else:
            title_lines = ["Index"]

        # Remove any empty trailing lines
        while title_lines and not title_lines[-1].strip():
            title_lines.pop()

        # Calculate layout positions
        current_y = 1

        # Draw supertitle if provided
        if self.supertitle:
            safe_addstr(
                stdscr,
                current_y,
                (mx - len(self.supertitle)) // 2,
                self.supertitle,
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
        if self.subtitle:
            safe_addstr(
                stdscr,
                current_y,
                (mx - len(self.subtitle)) // 2,
                self.subtitle,
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

            current_menu = self.groups[current_group]
            
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
        menu_end_y = draw_menu()

        # Draw epititle at bottom if provided
        if self.epititle:
            safe_addstr(
                stdscr,
                my - 2,  # Near bottom of window
                (mx - len(self.epititle)) // 2,
                self.epititle,
                curses.color_pair(8) | curses.A_DIM | curses.A_ITALIC,  # Gray/dim with italic
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
                    and current_option < len(self.groups[current_group].menu_items) - 1
                ):
                    current_option += 1
                elif k in [curses.KEY_ENTER, ord("\n"), ord("\r")]:
                    # Launch the selected menu item
                    selected_item = self.groups[current_group].menu_items[current_option]
                    return selected_item
                elif len(self.groups) > 1 and self._check_cycle_key(k):
                    # Cycle to next group
                    current_group = (current_group + 1) % len(self.groups)
                    current_option = 0
                    previous_option = -1  # Force redraw
                    draw_menu()
            except KeyboardInterrupt:
                break

        return "exit"

    def _check_cycle_key(self, key) -> bool:
        """Check if the pressed key matches the cycle key combination."""
        # For simplicity, we'll just check for the key character
        # In a full implementation, you'd need to track modifier states
        if not hasattr(self, 'cycle_key'):
            return False
            
        try:
            _, cycle_char = self.cycle_key.lower().split("+")
            return key == ord(cycle_char.lower()) or key == ord(cycle_char.upper())
        except (ValueError, IndexError):
            return False

    def show(self) -> Optional[str]:
        """
        Display the curses menu and launch selected items.

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
                choice = curses.wrapper(self._index_menu_loop)

                # Exit if requested or choice is exit
                if choice == "exit" or exit_requested or choice is None:
                    return last_selection
                
                # If choice is a CursesMenuItem, launch it
                if isinstance(choice, CursesMenuItem):
                    last_selection = choice.path
                    choice.launch()  # Always returns True now
                    # Continue the loop (show menu again)
                else:
                    # Fallback for non-CursesMenuItem objects
                    return choice

        except Exception as e:
            logger.error(f"Error in CursesIndex: {e}")
            return last_selection
        finally:
            exit_requested = True
            cleanup()

    def __repr__(self) -> str:
        """String representation for debugging."""
        item_count = len(self.get_all_menu_items())
        group_count = len(self.groups)
        return (
            f"CursesIndex(title='{self.title}', "
            f"items={item_count}, groups={group_count})"
        )