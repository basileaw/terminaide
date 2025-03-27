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

import logging
from .serve import serve_function, serve_script, serve_apps
from .core.settings import TTYDConfig, ScriptConfig, ThemeConfig, TTYDOptions
from .installer import setup_ttyd, get_platform_info
from .exceptions import (
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

# For backward compatibility
from .serve import serve_script as simple_serve
from .serve import serve_apps as serve_terminals

# Configure package-level logging
logging.getLogger("terminaide").addHandler(logging.NullHandler())

__all__ = [
    # New API
    "serve_function",
    "serve_script", 
    "serve_apps",
    
    # For backward compatibility
    "simple_serve",
    "serve_terminals",
    
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

# Ensure bin directory exists on import
import os
from pathlib import Path
bin_dir = Path(__file__).parent / "bin"
bin_dir.mkdir(exist_ok=True)