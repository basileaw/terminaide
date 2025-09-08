# index.py

"""Unified index functionality for HTML and terminal interfaces."""

import curses
import signal
import sys
import logging
import subprocess
import importlib
from typing import Optional, List, Dict, Any, Union, Literal
from pathlib import Path
from functools import lru_cache

from .terminascii import terminascii

logger = logging.getLogger("terminaide")

# Global state for signal handling (curses mode)
stdscr = None
exit_requested = False


# Base Classes


class BaseMenuItem:
    """Base menu item with path, title, and optional execution parameters."""

    __slots__ = ("path", "title", "function", "script", "launcher_args", "new_tab")

    def __init__(
        self, path: str, title: str, function=None, script=None, launcher_args=None, new_tab=None
    ):
        self.path = path
        self.title = title
        self.function = function
        self.script = script
        self.launcher_args = launcher_args or {}
        self.new_tab = new_tab

    def is_external(self) -> bool:
        """Check if this is an external URL."""
        return self.path.startswith(("http://", "https://"))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"path": self.path, "title": self.title}
        if self.new_tab is not None:
            result["new_tab"] = self.new_tab
        return result


class BaseIndex:
    """Base configuration for index/menu pages."""

    __slots__ = (
        "menu_items",
        "subtitle",
        "epititle",
        "epititle_item",
        "title",
        "supertitle",
        "preview_image",
        "instructions",
        "_all_items_cache",
    )

    def __init__(
        self,
        menu: Union[List[Dict[str, Any]], Dict[str, Any]],
        subtitle: Optional[str] = None,
        epititle: Optional[Union[str, Dict[str, Any]]] = None,
        title: Optional[str] = None,
        supertitle: Optional[str] = None,
        preview_image: Optional[Union[str, Path]] = None,
        instructions: Optional[str] = None,
    ):
        self._all_items_cache = None
        self._parse_and_validate_menu(menu)
        self.subtitle = subtitle
        self._parse_epititle(epititle)
        self.title = title or "Index"
        self.supertitle = supertitle
        self.preview_image = Path(preview_image) if preview_image else None
        self.instructions = instructions

    def _parse_and_validate_menu(self, menu):
        """Parse and validate the menu structure."""
        if not isinstance(menu, list):
            raise ValueError("Menu must be a list of menu items")
        
        if not menu:
            raise ValueError("Menu must contain at least one item")
        
        for i, item in enumerate(menu):
            if not isinstance(item, dict):
                raise ValueError(f"Menu item at index {i} must be a dictionary")
            if "title" not in item:
                raise ValueError(f"Menu item at index {i} missing required 'title' key")
            
            # Must have one of: path, function, or script
            if not any(key in item for key in ["path", "function", "script"]):
                raise ValueError(f"Menu item at index {i} must have 'path', 'function', or 'script'")
        
        # Create menu items directly
        self.menu_items = [self._create_menu_item(item) for item in menu]
    
    def _parse_epititle(self, epititle):
        """Parse and validate epititle - can be string or dict."""
        if epititle is None:
            self.epititle = None
            self.epititle_item = None
        elif isinstance(epititle, str):
            # Backward compatibility - simple string
            self.epititle = epititle
            self.epititle_item = None
        elif isinstance(epititle, dict):
            # New format - structured like menu item
            # Validate required fields
            if "title" not in epititle:
                raise ValueError("Epititle dict must have 'title' key")
            
            # Check if it's an external URL
            if "url" in epititle:
                # External link - no function/script needed
                self.epititle = None  # Will be handled as epititle_item
                self.epititle_item = BaseMenuItem(
                    path=epititle.get("url", ""),
                    title=epititle.get("title", ""),
                    new_tab=epititle.get("new_tab", True)
                )
            else:
                # Terminal route - must have path and either function or script
                if "path" not in epititle:
                    raise ValueError("Epititle dict must have 'path' key for terminal routes")
                if not any(key in epititle for key in ["function", "script"]):
                    raise ValueError("Epititle dict must have 'function' or 'script' for terminal routes")
                
                self.epititle = None  # Will be handled as epititle_item
                self.epititle_item = self._create_menu_item(epititle)
        else:
            raise ValueError("Epititle must be a string or dict")

    def _create_menu_item(self, item):
        """Create a menu item from dict. Override in subclasses for specialized items."""
        if isinstance(item, BaseMenuItem):
            return item
            
        # Start with existing launcher_args
        launcher_args = item.get("launcher_args", {}).copy()
        
        # Move route-specific configs into launcher_args if they exist
        route_configs = ["keyboard_mapping", "dynamic", "args_param", "preview_image", "port"]
        for config_key in route_configs:
            if config_key in item:
                launcher_args[config_key] = item[config_key]
        
        return BaseMenuItem(
            path=item.get("path", ""),
            title=item.get("title", ""),
            function=item.get("function"),
            script=item.get("script"),
            launcher_args=launcher_args,
            new_tab=item.get("new_tab"),
        )

    def get_all_menu_items(self) -> List[BaseMenuItem]:
        """Get all menu items as a flat list."""
        if self._all_items_cache is None:
            self._all_items_cache = self.menu_items
        return self._all_items_cache

    def __repr__(self) -> str:
        """String representation for debugging."""
        item_count = len(self.get_all_menu_items())
        class_name = self.__class__.__name__
        return f"{class_name}(title='{self.title}', items={item_count})"


# Auto Classes


class AutoMenuItem(BaseMenuItem):
    """Extended BaseMenuItem that can handle both HTML and Curses behavior."""

    __slots__ = ()

    def launch(self) -> bool:
        """Launch this menu item (Curses mode only)."""
        return launch_menu_item(self)


class AutoIndex(BaseIndex):
    """Unified configuration for index/menu pages with automatic type selection."""

    __slots__ = ("index_type", "_template_context_cache")

    def __init__(
        self,
        type: Literal["html", "curses"],
        menu: Union[List[Dict[str, Any]], Dict[str, Any]],
        subtitle: Optional[str] = None,
        epititle: Optional[str] = None,
        title: Optional[str] = None,
        supertitle: Optional[str] = None,
        preview_image: Optional[Union[str, Path]] = None,
        instructions: Optional[str] = None,
    ):
        if type not in ("html", "curses"):  # Use tuple for faster membership test
            raise ValueError(f"type must be 'html' or 'curses', got: {type}")

        self.index_type = type
        self._template_context_cache = None
        super().__init__(
            menu=menu,
            subtitle=subtitle,
            epititle=epititle,
            title=title,
            supertitle=supertitle,
            preview_image=preview_image,
            instructions=instructions,
        )


    def _create_menu_item(self, item):
        """Create an AutoMenuItem from dict or existing item."""
        if isinstance(item, AutoMenuItem):
            return item
            
        # Extract explicit fields
        explicit_fields = {"path", "title", "function", "script", "launcher_args", "new_tab"}
        
        # Collect launcher_args from explicit launcher_args plus any extra fields
        launcher_args = item.get("launcher_args", {}).copy()
        
        # Add any extra fields (like keyboard_mapping, dynamic, args_param, etc.) to launcher_args
        for key, value in item.items():
            if key not in explicit_fields:
                launcher_args[key] = value
        
        return AutoMenuItem(
            path=item.get("path", ""),
            title=item.get("title", ""),
            function=item.get("function"),
            script=item.get("script"),
            launcher_args=launcher_args,
            new_tab=item.get("new_tab"),
        )

    def get_all_menu_items(self) -> List[AutoMenuItem]:
        """Get all menu items as a flat list."""
        if self._all_items_cache is None:
            self._all_items_cache = self.menu_items
        return self._all_items_cache

    def to_template_context(self) -> Dict[str, Any]:
        """Convert to dictionary for template rendering (HTML only)."""
        if self._template_context_cache is None:
            self._template_context_cache = get_template_context(self)
        return self._template_context_cache

    def show(self) -> Optional[str]:
        """Display the curses menu and launch selected items (Curses only)."""
        if self.index_type != "curses":
            raise AttributeError("show() is only available for Curses indexes")
        return show_curses_menu(self)

    def extract_routes(self) -> Dict[str, Any]:
        """Extract terminal route definitions from menu items and epititle.
        
        Returns a dictionary mapping paths to route configurations for any
        menu items or epititle that have function or script definitions.
        """
        routes = {}
        
        # Extract routes from menu items
        for item in self.get_all_menu_items():
            # Skip external URLs and items without function/script
            if item.is_external() or (not item.function and not item.script):
                continue
                
            # Build route specification
            route_spec = {}
            
            if item.function:
                route_spec["function"] = item.function
            elif item.script:
                route_spec["script"] = item.script
                
            # Always include title
            route_spec["title"] = item.title
            
            # Include launcher_args if present (for dynamic routes, args_param, etc.)
            if item.launcher_args:
                route_spec.update(item.launcher_args)
                
            routes[item.path] = route_spec
        
        # Extract route from epititle if it has function/script
        if self.epititle_item and not self.epititle_item.is_external():
            if self.epititle_item.function or self.epititle_item.script:
                route_spec = {}
                
                if self.epititle_item.function:
                    route_spec["function"] = self.epititle_item.function
                elif self.epititle_item.script:
                    route_spec["script"] = self.epititle_item.script
                    
                route_spec["title"] = self.epititle_item.title
                
                if self.epititle_item.launcher_args:
                    route_spec.update(self.epititle_item.launcher_args)
                    
                routes[self.epititle_item.path] = route_spec
            
        return routes

    def __repr__(self) -> str:
        """String representation for debugging."""
        item_count = len(self.get_all_menu_items())
        return f"AutoIndex(type='{self.index_type}', title='{self.title}', items={item_count})"


# Curses Implementation


def handle_exit(*_):
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
    except Exception:
        pass


def safe_addstr(win, y, x, text, attr=0):
    """Safely add a string to the screen, handling boundary conditions."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    text = text[: w - x] if w - x > 0 else ""
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def launch_menu_item(menu_item: AutoMenuItem) -> bool:
    """Launch a menu item (Curses mode only). Always returns True to return to menu."""
    try:
        if menu_item.function:
            menu_item.function()
        elif menu_item.script:
            subprocess.run(
                [sys.executable, menu_item.script], capture_output=False, check=False
            )
        elif menu_item.path and not menu_item.is_external():
            return _launch_from_path(menu_item.path)
        else:
            logger.warning(f"No launch method defined for {menu_item.title}")
    except Exception as e:
        target = getattr(
            menu_item.function, "__name__", menu_item.script or menu_item.path
        )
        logger.error(f"Error launching {target}: {e}")
    return True


# Pre-compiled set for faster membership testing
_GAME_PATHS = frozenset(["snake", "tetris", "pong", "asteroids"])


def _launch_from_path(path: str) -> bool:
    """Dynamically resolve and launch a function or module from a path string."""
    try:
        if "." in path:
            parts = path.split(".")
            function_name = parts[-1]
            module_path = ".".join(parts[:-1])

            module = sys.modules.get(module_path)
            if module is not None:
                module = importlib.reload(module)
            else:
                module = importlib.import_module(module_path)

            # Reset module-level state if present (for games)
            for attr in ("exit_requested", "stdscr"):
                if hasattr(module, attr):
                    setattr(module, attr, False if attr == "exit_requested" else None)

            if hasattr(module, function_name):
                getattr(module, function_name)()
                return True
            else:
                logger.error(
                    f"Function {function_name} not found in module {module_path}"
                )
                return True
        else:
            # Single name - try common patterns for backwards compatibility with terminarcade games
            if path in _GAME_PATHS:
                try:
                    module_path = f"terminarcade.{path}"
                    importlib.import_module(module_path)
                except ImportError:
                    module_path = f"terminaide.terminarcade.{path}"
                function_name = f"play_{path}"

                module = sys.modules.get(module_path)
                if module is not None:
                    module = importlib.reload(module)
                else:
                    module = importlib.import_module(module_path)

                # Reset module-level state
                for attr in ("exit_requested", "stdscr"):
                    if hasattr(module, attr):
                        setattr(
                            module, attr, False if attr == "exit_requested" else None
                        )

                getattr(module, function_name)()
                return True
            else:
                logger.warning(f"Don't know how to launch path: {path}")
                return True
    except Exception as e:
        logger.error(f"Error launching from path {path}: {e}")
        return True


def show_curses_menu(auto_index: AutoIndex) -> Optional[str]:
    """Display the curses menu and launch selected items."""
    global exit_requested
    last_selection = None

    signal.signal(signal.SIGINT, handle_exit)

    try:
        while True:
            choice = curses.wrapper(lambda stdscr: _index_menu_loop(stdscr, auto_index))

            if choice == "exit" or exit_requested or choice is None:
                return last_selection

            if hasattr(choice, "launch"):
                last_selection = choice.path
                launch_menu_item(choice)
            else:
                return choice

    except Exception as e:
        logger.error(f"Error in AutoIndex: {e}")
        return last_selection
    finally:
        exit_requested = True
        cleanup()


def _index_menu_loop(stdscr_param, auto_index: AutoIndex):
    """Main menu interface for curses mode."""
    global stdscr, exit_requested
    stdscr = stdscr_param
    exit_requested = False

    signal.signal(signal.SIGINT, handle_exit)

    # Configure terminal
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLUE, -1)  # Title
    curses.init_pair(2, curses.COLOR_WHITE, -1)  # Instructions & Subtitle
    curses.init_pair(3, curses.COLOR_CYAN, -1)  # Supertitle
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Unselected
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selected
    curses.init_pair(6, curses.COLOR_GREEN, -1)  # Menu labels
    curses.init_pair(7, curses.COLOR_WHITE, -1)  # Epititle
    curses.init_pair(8, curses.COLOR_WHITE, -1)  # Epititle dim

    curses.curs_set(0)  # Hide cursor
    stdscr.clear()

    # Current state
    current_option = 0
    previous_option = 0

    # Get screen dimensions
    my, mx = stdscr.getmaxyx()

    # Generate ASCII art from title
    if auto_index.title:
        ascii_art = terminascii(auto_index.title)
        if ascii_art:
            title_lines = ascii_art.split("\n")
            # Remove empty trailing lines in one pass
            while title_lines and not title_lines[-1].strip():
                title_lines.pop()
        else:
            title_lines = [auto_index.title]
    else:
        title_lines = ["Index"]

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
            curses.color_pair(2),
        )
        current_y += 2

    # Store menu start position
    menu_start_y = current_y

    def draw_menu():
        """Draw the menu."""
        nonlocal current_y
        y_pos = menu_start_y

        # Clear menu area
        for clear_y in range(menu_start_y, my - 3):
            safe_addstr(stdscr, clear_y, 0, " " * mx)

        # Draw instructions if provided
        if auto_index.instructions:
            safe_addstr(
                stdscr,
                y_pos,
                (mx - len(auto_index.instructions)) // 2,
                auto_index.instructions,
                curses.color_pair(6) | curses.A_BOLD,
            )
            y_pos += 2

        # Calculate button layout
        menu_items = auto_index.get_all_menu_items()
        options = [item.title for item in menu_items]
        button_padding = 4
        button_width = max(len(o) for o in options) + 6
        num_options = len(options)
        total_buttons_width = (button_width * num_options) + (
            button_padding * (num_options - 1)
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
        epititle_lines = auto_index.epititle.split("\n")
        total_lines = len(epititle_lines)
        start_y = my - total_lines - 1

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
            k = stdscr.getch()

            if k in [ord("q"), ord("Q"), 27]:  # q, Q, or ESC
                break
            elif k in [curses.KEY_LEFT, ord("a"), ord("A")] and current_option > 0:
                current_option -= 1
            elif (
                k in [curses.KEY_RIGHT, ord("d"), ord("D")]
                and current_option < len(auto_index.get_all_menu_items()) - 1
            ):
                current_option += 1
            elif k in [curses.KEY_ENTER, ord("\n"), ord("\r")]:
                selected_item = auto_index.get_all_menu_items()[current_option]
                return selected_item
        except KeyboardInterrupt:
            break

    return "exit"


# HTML Implementation


@lru_cache(maxsize=128)
def is_ascii_art(text: str) -> bool:
    """Detect if a string contains ASCII art by checking for multiple lines."""
    return "\n" in text and len(text.split("\n")) > 1


def get_template_context(auto_index: AutoIndex) -> Dict[str, Any]:
    """Convert AutoIndex to dictionary for template rendering (HTML only)."""
    if auto_index.index_type != "html":
        raise AttributeError(
            "get_template_context() is only available for HTML indexes"
        )

    # Generate ASCII art for title
    title_ascii = None
    if auto_index.title and auto_index.title != "Index":
        title_ascii = (
            auto_index.title
            if is_ascii_art(auto_index.title)
            else terminascii(auto_index.title)
        )

    # Prepare menu items data for JavaScript
    menu_items = [item.to_dict() for item in auto_index.get_all_menu_items()]
    total_items = len(menu_items)
    
    # Prepare epititle data - either string or structured data
    epititle_data = None
    if auto_index.epititle:
        # Simple string format (backward compatibility)
        epititle_data = {"type": "text", "content": auto_index.epititle}
    elif auto_index.epititle_item:
        # Structured format - could be link or terminal route
        epititle_data = {
            "type": "link",
            "title": auto_index.epititle_item.title,
            "path": auto_index.epititle_item.path,
            "is_external": auto_index.epititle_item.is_external(),
            "new_tab": auto_index.epititle_item.new_tab if auto_index.epititle_item.new_tab is not None else True
        }

    return {
        "page_title": auto_index.title,
        "title_ascii": title_ascii,
        "supertitle": auto_index.supertitle,
        "subtitle": auto_index.subtitle,
        "epititle": epititle_data,  # Now structured data instead of just string
        "instructions": auto_index.instructions,
        "menu_items": menu_items,
        "total_items": total_items,
        "title": auto_index.title,
    }
