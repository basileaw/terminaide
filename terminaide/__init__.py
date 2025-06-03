# __init__.py

"""
terminaide: Serve Python CLI applications in the browser using ttyd.

This package provides tools to easily serve Python CLI applications through
a browser-based terminal using ttyd. It handles binary installation and
management automatically across supported platforms.

The package offers four entry points with increasing complexity:
1. serve_function: The simplest way to serve a Python function in a browser terminal
2. serve_script: Simple path to serve a Python script file in a terminal
3. serve_apps: Advanced path to integrate multiple terminals (both functions and scripts)
              and index pages into a FastAPI application
4. meta_serve: Advanced path to run a server that serves terminal instances in a browser terminal

Supported Platforms:
- Linux x86_64 (Docker containers)
- macOS ARM64 (Apple Silicon)
"""

import sys
import os
import logging
from pathlib import Path
from .termin_api import serve_function, serve_script, serve_apps, meta_serve
from .core.data_models import TTYDConfig, ScriptConfig, ThemeConfig, TTYDOptions
from .core.index_page import IndexPage
from .core.ttyd_installer import setup_ttyd, get_platform_info
from .core.ascii_utils import termin_ascii
from .core.exceptions import (
    terminaideError,
    BinaryError,
    InstallationError,
    PlatformNotSupportedError,
    DependencyError,
    DownloadError,
    TTYDStartupError,
    TTYDProcessError,
    ClientScriptError,
    TemplateError,
    ProxyError,
    ConfigurationError,
    RouteNotFoundError,
    PortAllocationError,
    ScriptConfigurationError,
    DuplicateRouteError,
)

# Try to import terminarcade as an optional subpackage
try:
    from .terminarcade import play as _terminarcade_play

    # Create a callable wrapper that defaults to "index" when called with "games"
    class TerminArcade:
        def __call__(self, mode="index"):
            if mode == "games":
                mode = "index"
            return _terminarcade_play(mode)

        # Make the module attributes accessible
        def __getattr__(self, name):
            import terminaide.terminarcade as _mod

            return getattr(_mod, name)

    terminarcade = TerminArcade()
except ImportError:
    terminarcade = None


import hashlib

# Enhanced ANSI color codes
COLORS = {
    "DEBUG": "\033[36m",  # Cyan
    "INFO": "\033[32m",  # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "CRITICAL": "\033[41m",  # Red background
    "RESET": "\033[0m",  # Reset colors
}

# Route color palette - bright, distinguishable colors
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
]


def get_route_color(route_path: str) -> str:
    """Get a consistent color for a route based on its path."""
    # Use hash to get consistent color assignment
    hash_value = int(hashlib.md5(route_path.encode()).hexdigest()[:8], 16)
    color_index = hash_value % len(ROUTE_COLORS)
    return ROUTE_COLORS[color_index]


def colorize_route_title(title: str, route_path: str) -> str:
    """Colorize a route title with its assigned color."""
    if not sys.stdout.isatty():  # Only apply colors if running in a terminal
        return title
    color = get_route_color(route_path)
    return f"{color}{title}{COLORS['RESET']}"


class ColorAlignedFormatter(logging.Formatter):
    def format(self, record):
        levelname = record.levelname
        # Ensure the level name + padding + colon takes exactly 10 characters
        padding_length = max(1, 9 - len(levelname))
        padding = " " * padding_length

        # Add colors if the system supports it
        if sys.stdout.isatty():  # Only apply colors if running in a terminal
            colored_levelname = (
                f"{COLORS.get(levelname, '')}{levelname}{COLORS['RESET']}"
            )
            return f"{colored_levelname}:{padding}{record.getMessage()}"
        else:
            return f"{levelname}:{padding}{record.getMessage()}"


# Configure package-level logging
logger = logging.getLogger("terminaide")
handler = logging.StreamHandler()
handler.setFormatter(ColorAlignedFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent propagation to root logger to avoid duplicate logs

# Ensure bin directory exists on import
bin_dir = Path(__file__).parent / "core" / "bin"
bin_dir.mkdir(exist_ok=True)

__all__ = [
    # New API
    "serve_function",
    "serve_script",
    "serve_apps",
    "meta_serve",
    # Index page support
    "IndexPage",
    # ASCII banner generation
    "termin_ascii",
    # Configuration objects
    "TTYDConfig",
    "ScriptConfig",
    "ThemeConfig",
    "TTYDOptions",
    # Binary management
    "setup_ttyd",
    "get_platform_info",
    # Exceptions
    "terminaideError",
    "BinaryError",
    "InstallationError",
    "PlatformNotSupportedError",
    "DependencyError",
    "DownloadError",
    "TTYDStartupError",
    "TTYDProcessError",
    "ClientScriptError",
    "TemplateError",
    "ProxyError",
    "ConfigurationError",
    "RouteNotFoundError",
    "PortAllocationError",
    "ScriptConfigurationError",
    "DuplicateRouteError",
]

# Add terminarcade to exports only if it's available
if terminarcade is not None:
    __all__.append("terminarcade")
