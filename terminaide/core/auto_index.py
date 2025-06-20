# terminaide/core/auto_index.py

"""
Auto Index functionality for Terminaide.

This module provides the AutoIndex class which creates either HTML or Curses-based
index pages based on a type parameter, offering a single API for both web and
terminal menu systems.
"""

import curses
import signal
import sys
import logging
import subprocess
import importlib
from typing import Optional, List, Dict, Any, Union, Literal, Callable
from pathlib import Path

from .termin_ascii import termin_ascii

logger = logging.getLogger("terminaide")

# Global state for signal handling (curses mode)
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


def is_ascii_art(text: str) -> bool:
    """
    Detect if a string contains ASCII art by checking for multiple lines.
    
    Args:
        text: The text to analyze
        
    Returns:
        True if the text appears to be ASCII art (multi-line), False otherwise
    """
    return '\n' in text and len(text.split('\n')) > 1


class BaseMenuItem:
    """Base menu item with path, title, and optional execution parameters."""

    def __init__(self, path: str, title: str, function=None, script=None, launcher_args=None):
        """
        Initialize a base menu item.

        Args:
            path: The URL path (can be internal route or external URL)
            title: Display title for the menu item
            function: Python function to execute when selected (optional, used by AutoIndex with type="curses")
            script: Python script path to execute when selected (optional, used by AutoIndex with type="curses")
            launcher_args: Additional arguments for the launcher (optional, used by AutoIndex with type="curses")
        """
        self.path = path
        self.title = title
        # Optional fields used by AutoIndex with type="curses", ignored when type="html"
        self.function = function
        self.script = script
        self.launcher_args = launcher_args or {}

    def is_external(self) -> bool:
        """Check if this is an external URL."""
        return self.path.startswith(("http://", "https://"))

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {"path": self.path, "title": self.title}


class BaseMenuGroup:
    """Base group of menu items with a label."""

    def __init__(self, label: str, options: List[Dict[str, Any]]):
        """
        Initialize a menu group.

        Args:
            label: The label shown for this group of menu items
            options: List of menu items as dictionaries
        """
        self.label = label
        self.menu_items = [self._create_menu_item(item) for item in options]

    def _create_menu_item(self, item):
        """Create a menu item from dict. Override in subclasses for specialized items."""
        if isinstance(item, BaseMenuItem):
            return item
        else:
            # Create BaseMenuItem from dict
            return BaseMenuItem(
                path=item.get('path', ''),
                title=item.get('title', ''),
                function=item.get('function'),
                script=item.get('script'),
                launcher_args=item.get('launcher_args', {})
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "label": self.label,
            "options": [item.to_dict() for item in self.menu_items],
        }


class BaseIndex:
    """
    Base configuration for index/menu pages.

    This class provides common functionality for both HTML and Curses index
    implementations, including menu parsing, validation, and utility methods.
    """

    def __init__(
        self,
        # Content
        menu: Union[List[Dict[str, Any]], Dict[str, Any]],
        subtitle: Optional[str] = None,
        epititle: Optional[str] = None,
        # Title options
        title: Optional[str] = None,
        supertitle: Optional[str] = None,
        # Assets
        preview_image: Optional[Union[str, Path]] = None,
        # Additional args for subclass compatibility
        **kwargs
    ):
        """
        Initialize a BaseIndex.

        Args:
            menu: Either:
                - A list of menu groups (for single menu or when cycle_key not needed)
                - A dict with 'groups' and 'cycle_key' keys (for multiple menus with cycling)
                  Example: {"cycle_key": "shift+g", "groups": [{"label": "...", "options": [...]}]}
            subtitle: Text paragraph below the title
            epititle: Optional text shown below the menu items. Supports newlines for multi-line display.
            title: Title text (defaults to 'Index')
            supertitle: Regular text above title
            preview_image: Path to preview image

        Raises:
            ValueError: If menu is empty or has invalid structure
        """
        # Parse and validate menu structure
        self._parse_and_validate_menu(menu)
        
        # Store text/title options
        self.subtitle = subtitle
        self.epititle = epititle
        self.title = title or "Index"
        self.supertitle = supertitle

        # Handle preview image
        if preview_image:
            self.preview_image = Path(preview_image)
        else:
            self.preview_image = None

    def _parse_and_validate_menu(self, menu):
        """Parse and validate the menu structure."""
        # Parse menu structure
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

        # Convert menu groups - subclasses can override _create_menu_group
        self.groups = [self._create_menu_group(g["label"], g["options"]) for g in menu_groups]

    def _create_menu_group(self, label: str, options: List[Dict[str, Any]]):
        """Create a menu group. Override in subclasses for specialized groups."""
        return BaseMenuGroup(label, options)

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

    def get_all_menu_items(self) -> List[BaseMenuItem]:
        """
        Get all menu items as a flat list.

        Returns:
            List of all BaseMenuItem objects across all groups
        """
        all_items = []
        for group in self.groups:
            all_items.extend(group.menu_items)
        return all_items

    def __repr__(self) -> str:
        """String representation for debugging."""
        item_count = len(self.get_all_menu_items())
        group_count = len(self.groups)
        class_name = self.__class__.__name__
        return (
            f"{class_name}(title='{self.title}', "
            f"items={item_count}, groups={group_count})"
        )


class AutoMenuItem(BaseMenuItem):
    """Extended BaseMenuItem that can handle both HTML and Curses behavior."""
    
    def __init__(self, path: str, title: str, function=None, script=None, launcher_args=None):
        """
        Initialize an AutoMenuItem.
        
        Args:
            path: The URL path (for HTML) or launch target (for Curses)
            title: Display title for the menu item
            function: Python function to execute when selected (Curses mode)
            script: Python script path to execute when selected (Curses mode)
            launcher_args: Additional arguments for the launcher (Curses mode)
        """
        super().__init__(path, title, function, script, launcher_args)
    
    def launch(self) -> bool:
        """
        Launch this menu item (Curses mode only).
        
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


class AutoMenuGroup(BaseMenuGroup):
    """Group of AutoMenuItem objects with a label."""
    
    def _create_menu_item(self, item):
        """Create an AutoMenuItem from dict or existing item."""
        if isinstance(item, AutoMenuItem):
            return item
        else:
            # Create AutoMenuItem from dict
            return AutoMenuItem(
                path=item.get('path', ''),
                title=item.get('title', ''),
                function=item.get('function'),
                script=item.get('script'),
                launcher_args=item.get('launcher_args', {})
            )


class AutoIndex(BaseIndex):
    """
    Unified configuration for index/menu pages with automatic type selection.

    AutoIndex provides a single API for creating both HTML web pages and
    terminal-based curses menus. The behavior is determined by the 'type'
    parameter.

    When type="html", paths in menu items can be:
    - Internal routes (e.g., "/terminal", "/admin")
    - External URLs (e.g., "https://example.com")

    When type="curses", paths in menu items can be:
    - Python functions (passed directly)
    - Script paths (e.g., "script.py")
    - Module paths (e.g., "module.function")
    """

    def __init__(
        self,
        type: Literal["html", "curses"],
        # Content
        menu: Union[List[Dict[str, Any]], Dict[str, Any]],
        subtitle: Optional[str] = None,
        epititle: Optional[str] = None,
        # Title options
        title: Optional[str] = None,
        supertitle: Optional[str] = None,
        # Assets (only used for HTML)
        preview_image: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize an AutoIndex.

        Args:
            type: The type of index to create - "html" for web pages, "curses" for terminal menus
            menu: Either:
                - A list of menu groups (for single menu or when cycle_key not needed)
                - A dict with 'groups' and 'cycle_key' keys (for multiple menus with cycling)
                  Example: {"cycle_key": "shift+g", "groups": [{"label": "...", "options": [...]}]}
            subtitle: Text paragraph below the title
            epititle: Optional text shown below the menu items. Supports newlines for multi-line display.
            title: Title text (defaults to 'Index')
            supertitle: Regular text above title
            preview_image: Path to preview image for social media (HTML only)

        Raises:
            ValueError: If type is not "html" or "curses"
            ValueError: If menu is empty or has invalid structure
        """
        # Validate type parameter
        if type not in ["html", "curses"]:
            raise ValueError(f"type must be 'html' or 'curses', got: {type}")
        
        self.index_type = type
        
        # Initialize base class
        super().__init__(
            menu=menu,
            subtitle=subtitle,
            epititle=epititle,
            title=title,
            supertitle=supertitle,
            preview_image=preview_image
        )
        
        # Set default cycle_key for HTML (different from base)
        if self.index_type == "html" and hasattr(self, 'cycle_key') and self.cycle_key == "shift+g":
            self.cycle_key = "shift+p"
    
    def _create_menu_group(self, label: str, options: List[Dict[str, Any]]):
        """Create appropriate menu group based on index type."""
        return AutoMenuGroup(label, options)
    
    def get_all_menu_items(self) -> List[AutoMenuItem]:
        """
        Get all menu items as a flat list.

        Returns:
            List of all AutoMenuItem objects across all groups
        """
        all_items = []
        for group in self.groups:
            all_items.extend(group.menu_items)
        return all_items
    
    def to_template_context(self) -> Dict[str, Any]:
        """
        Convert to dictionary for template rendering (HTML only).

        Returns:
            Dictionary with all data needed for Jinja2 template

        Raises:
            AttributeError: If called on a curses-type index
        """
        if self.index_type != "html":
            raise AttributeError("to_template_context() is only available for HTML indexes")
        
        # Simple logic: title gets converted to ASCII art
        title_ascii = None
        
        if self.title and self.title != "Index":
            if is_ascii_art(self.title):
                # Title is already ASCII art - use it directly
                title_ascii = self.title
            else:
                # Generate ASCII art from title text
                title_ascii = termin_ascii(self.title)

        # Prepare groups data for JavaScript
        groups_data = [group.to_dict() for group in self.groups]
        has_multiple_groups = len(self.groups) > 1

        # Count total items for grid sizing hints
        total_items = len(self.get_all_menu_items())

        return {
            "page_title": self.title,
            "title_ascii": title_ascii,
            "supertitle": self.supertitle,
            "subtitle": self.subtitle,
            "epititle": self.epititle,
            "has_multiple_groups": has_multiple_groups,
            "groups_json": groups_data,
            "cycle_key": self.cycle_key,
            "total_items": total_items,
            "title": self.title,
        }
    
    def _index_menu_loop(self, stdscr_param):
        """Main menu interface for curses mode.

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

        # Generate ASCII art from title
        if self.title:
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
        draw_menu()

        # Draw epititle at bottom if provided
        if self.epititle:
            # Split epititle into lines for multiline support
            epititle_lines = self.epititle.split('\n')
            
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
        Display the curses menu and launch selected items (Curses only).

        Returns:
            str: The path of the last selected item, or None if user exited

        Raises:
            AttributeError: If called on an HTML-type index
        """
        if self.index_type != "curses":
            raise AttributeError("show() is only available for Curses indexes")
        
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
                
                # If choice is an AutoMenuItem, launch it
                if isinstance(choice, AutoMenuItem):
                    last_selection = choice.path
                    choice.launch()  # Always returns True now
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
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        item_count = len(self.get_all_menu_items())
        group_count = len(self.groups)
        return (
            f"AutoIndex(type='{self.index_type}', title='{self.title}', "
            f"items={item_count}, groups={group_count})"
        )