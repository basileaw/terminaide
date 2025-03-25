"""
terminaide: Serve Python CLI applications in the browser using ttyd.

This package provides tools to easily serve Python CLI applications through
a browser-based terminal using ttyd. It handles binary installation and
management automatically across supported platforms.

The package supports multi-script routing, allowing different scripts
to be served on different routes.

Supported Platforms:
- Linux x86_64 (Docker containers)
- macOS ARM64 (Apple Silicon)
"""

import logging
from .serve import serve_terminals, simple_serve
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

# Configure package-level logging
logging.getLogger("terminaide").addHandler(logging.NullHandler())

__all__ = [
    # Main functionality
    "serve_terminals",
    "simple_serve",
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