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
from .serve import serve_terminal, _configure_app  # Import only definitions, no side effects
from .core.settings import TTYDConfig, ScriptConfig, ThemeConfig, TTYDOptions
from .installer import setup_ttyd, get_platform_info
from .demos import run as demo_run
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
    "serve_terminal",
    "TTYDConfig",
    "ScriptConfig",
    "ThemeConfig",
    "TTYDOptions",

    # Binary management
    "setup_ttyd",
    "get_platform_info",

    # Demo functionality
    "demo_run",

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

# Optional: Provide a convenience alias if desired
demos = demo_run