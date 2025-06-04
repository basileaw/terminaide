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

import logging
from pathlib import Path
from .termin_api import serve_function, serve_script, serve_apps, meta_serve
from .core.data_models import TTYDConfig, ScriptConfig, ThemeConfig, TTYDOptions
from .core.index_html import HtmlIndex
from .core.utils import termin_ascii

from .terminarcade import play as terminarcade


# Get package-level logger (configuration happens when serve_* functions are called)
logger = logging.getLogger("terminaide")

# Ensure ttyd_bin directory exists on import
ttyd_bin_dir = Path(__file__).parent / "core" / "ttyd_bin"
ttyd_bin_dir.mkdir(exist_ok=True)

__all__ = [
    # New API
    "serve_function",
    "serve_script",
    "serve_apps",
    "meta_serve",
    # Index page support
    "HtmlIndex",
    # ASCII banner generation
    "termin_ascii",
    # Configuration objects
    "TTYDConfig",
    "ScriptConfig",
    "ThemeConfig",
    "TTYDOptions",
    # Games
    "terminarcade",
]
