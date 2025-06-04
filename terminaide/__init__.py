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
from .core.utils import termin_ascii
from .core.logging import setup_package_logging, get_route_color, colorize_route_title
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


# Get package-level logger (configuration happens when serve_* functions are called)
logger = logging.getLogger("terminaide")

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
