# logger.py

"""Logging configuration and terminal output formatting for Terminaide."""

import sys
import logging
import hashlib
from typing import Dict, Optional
from pathlib import Path


# Enhanced ANSI color codes for logging levels
LEVEL_COLORS = {
    "DEBUG": "\033[36m",  # Cyan
    "INFO": "\033[32m",  # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "CRITICAL": "\033[41m",  # Red background
    "RESET": "\033[0m",  # Reset colors
}


class ColorAlignedFormatter(logging.Formatter):
    """Logging formatter that adds colors and aligns log levels."""

    def format(self, record):
        levelname = record.levelname
        # Ensure the level name + padding + colon takes exactly 10 characters
        padding_length = max(1, 9 - len(levelname))
        padding = " " * padding_length

        # Add colors if the system supports it
        if sys.stdout.isatty():  # Only apply colors if running in a terminal
            colored_levelname = (
                f"{LEVEL_COLORS.get(levelname, '')}{levelname}{LEVEL_COLORS['RESET']}"
            )
            return f"{colored_levelname}:{padding}{record.getMessage()}"
        else:
            return f"{levelname}:{padding}{record.getMessage()}"


class RouteColorManager:
    """Manages consistent color assignments and formatting for routes."""

    # Bright, distinguishable colors for route titles
    ROUTE_COLORS = [
        "\033[94m",  # Bright Blue
        "\033[95m",  # Bright Magenta
        "\033[96m",  # Bright Cyan
        "\033[93m",  # Bright Yellow
        "\033[91m",  # Bright Red
        "\033[92m",  # Bright Green
        "\033[97m",  # Bright White
        "\033[35m",  # Magenta
        "\033[34m",  # Blue
        "\033[36m",  # Cyan
        "\033[33m",  # Yellow
        "\033[31m",  # Red
        "\033[32m",  # Green
        "\033[37m",  # White
        "\033[90m",  # Bright Black (Gray)
        "\033[38;5;208m",  # Orange
        "\033[38;5;165m",  # Pink
        "\033[38;5;51m",  # Light Cyan
        "\033[38;5;226m",  # Light Yellow
        "\033[38;5;46m",  # Light Green
    ]

    RESET = "\033[0m"

    def __init__(self):
        self._route_colors: Dict[str, str] = {}
        self._color_enabled = sys.stdout.isatty()

    def get_route_color(self, route_path: str) -> str:
        """Get a consistent color for a route based on its path."""
        if not self._color_enabled:
            return ""

        if route_path not in self._route_colors:
            # Use hash to get consistent color assignment
            hash_value = int(hashlib.md5(route_path.encode()).hexdigest()[:8], 16)
            color_index = hash_value % len(self.ROUTE_COLORS)
            self._route_colors[route_path] = self.ROUTE_COLORS[color_index]

        return self._route_colors[route_path]

    def colorize_title(self, title: str, route_path: str) -> str:
        """Colorize a route title with its assigned color."""
        if not self._color_enabled:
            return title
        color = self.get_route_color(route_path)
        return f"{color}{title}{self.RESET}"

    def format_route_info(
        self,
        route_path: str,
        title: str,
        script_config,
        port: Optional[int] = None,
        pid: Optional[int] = None,
    ) -> tuple[str, str]:
        """Create a standardized route info string with consistent formatting.

        Returns:
            tuple: (main_line, script_line) for separate logging
        """
        colored_title = self.colorize_title(title, route_path)
        route_type = "function" if script_config.is_function_based else "script"

        # Format the main info line in the new style
        main_line = f"Serving '{colored_title}' {route_type}"

        if pid:
            # Colorize PID in cyan like uvicorn
            if self._color_enabled:
                colored_pid = f"\033[36m{pid}\033[0m"  # Cyan color
                main_line += f" [{colored_pid}]"
            else:
                main_line += f" [{pid}]"

        if port:
            main_line += f" on port {port}"

        main_line += f" at '{route_path}'"

        # Format the script path line
        script_info = (
            str(script_config.effective_script_path)
            if script_config.effective_script_path
            else "function"
        )
        script_line = f"Script path: {script_info}"

        return main_line, script_line


# Global instance
route_color_manager = RouteColorManager()


# Legacy compatibility functions (used by __init__.py)
def get_route_color(route_path: str) -> str:
    """Get a consistent color for a route based on its path."""
    return route_color_manager.get_route_color(route_path)


def colorize_route_title(title: str, route_path: str) -> str:
    """Colorize a route title with its assigned color."""
    return route_color_manager.colorize_title(title, route_path)


def setup_package_logging(log_level="info"):
    """Configure package-level logging for Terminaide.

    Args:
        log_level: Logging level as string ("debug", "info", "warning", "error", "critical")
                  or None to skip configuration. Defaults to "info".
    """
    logger = logging.getLogger("terminaide")

    if log_level is not None:
        # Only add handler if none exist (avoid duplicate handlers)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(ColorAlignedFormatter())
            logger.addHandler(handler)

            # Convert string level to logging constant
            level_map = {
                "debug": logging.DEBUG,
                "info": logging.INFO,
                "warning": logging.WARNING,
                "error": logging.ERROR,
                "critical": logging.CRITICAL,
            }
            logger.setLevel(level_map.get(log_level.lower(), logging.INFO))
            logger.propagate = False  # Prevent propagation to root logger

    return logger
