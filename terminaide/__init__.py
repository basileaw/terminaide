# terminaide/__init__.py

"""
terminaide: Serve Python CLI applications in the browser using ttyd.

This package provides tools to easily serve Python CLI applications through
a browser-based terminal using ttyd. It handles binary installation and
management automatically across supported platforms.

The package offers three entry points with increasing complexity:
1. serve_function: The simplest way to serve a Python function in a browser terminal
2. serve_script: Simple path to serve a Python script file in a terminal
3. serve_apps: Advanced path to integrate multiple terminals into a FastAPI application

Supported Platforms:
- Linux x86_64 (Docker containers)
- macOS ARM64 (Apple Silicon)
"""

import sys
import logging
from pathlib import Path
from .termin_api import serve_function, serve_script, serve_apps
from .core.data_models import TTYDConfig, ScriptConfig, ThemeConfig, TTYDOptions
from .core.ttyd_installer import setup_ttyd, get_platform_info
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
    DuplicateRouteError
)

# ANSI color codes similar to uvicorn's
COLORS = {
    'DEBUG': '\033[36m',     # Cyan
    'INFO': '\033[32m',      # Green
    'WARNING': '\033[33m',   # Yellow
    'ERROR': '\033[31m',     # Red
    'CRITICAL': '\033[41m',  # Red background
    'RESET': '\033[0m'       # Reset colors
}

class ColorAlignedFormatter(logging.Formatter):
    def format(self, record):
        levelname = record.levelname
        # Ensure the level name + padding + colon takes exactly 10 characters
        padding_length = max(1, 9 - len(levelname))
        padding = ' ' * padding_length
        
        # Add colors if the system supports it
        if sys.stdout.isatty():  # Only apply colors if running in a terminal
            colored_levelname = f"{COLORS.get(levelname, '')}{levelname}{COLORS['RESET']}"
            return f"{colored_levelname}:{padding}{record.getMessage()}"
        else:
            return f"{levelname}:{padding}{record.getMessage()}"

# Configure package-level logging
logger = logging.getLogger("terminaide")
handler = logging.StreamHandler()
handler.setFormatter(ColorAlignedFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Ensure bin directory exists on import
bin_dir = Path(__file__).parent / "core" / "bin"
bin_dir.mkdir(exist_ok=True)

__all__ = [
    # New API
    "serve_function",
    "serve_script", 
    "serve_apps",
    
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
    "DuplicateRouteError"
]