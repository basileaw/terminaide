# terminaide/__init__.py

"""
terminaide: Serve Python CLI applications in the browser using ttyd.

This package provides tools to easily serve Python CLI applications through
a browser-based terminal using ttyd. It handles binary installation and
management automatically across supported platforms.

Supported Platforms:
- Linux x86_64 (Docker containers)
- macOS ARM64 (Apple Silicon)
"""

import logging
from fastapi import FastAPI
from pathlib import Path
from typing import Optional, Dict, Any, Union

# Configure package-level logging
logging.getLogger("terminaide").addHandler(logging.NullHandler())

# Core functionality
from .core.settings import TTYDConfig
from .serve import serve_tty, _configure_app

# Installation management
from .installer import setup_ttyd, get_platform_info

# Expose all exceptions
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
    ConfigurationError
)

__version__ = "0.2.0"  # Updated version number
__all__ = [
    # Main functionality
    "serve_tty",
    "TTYDConfig",
    
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
    "ConfigurationError"
]

# Type aliases for better documentation
ThemeConfig = Dict[str, str]
TTYDOptions = Dict[str, Any]

def serve_tty(
    app: FastAPI,
    client_script: Union[str, Path],
    *,
    mount_path: str = "/tty",
    port: int = 7681,
    theme: Optional[ThemeConfig] = None,
    ttyd_options: Optional[TTYDOptions] = None,
    template_override: Optional[Union[str, Path]] = None,
    debug: bool = False
) -> None:
    """
    Configure FastAPI application to serve a Python script through a browser-based terminal.

    This function automatically handles ttyd binary installation and setup for the
    current platform. Supported platforms are Linux x86_64 (for Docker) and
    macOS ARM64 (Apple Silicon).

    Args:
        app: FastAPI application instance
        client_script: Path to Python script to run in terminal
        mount_path: URL path to mount terminal (default: "/tty")
        port: Port for ttyd process (default: 7681)
        theme: Terminal theme configuration (default: {"background": "black"})
        ttyd_options: Additional ttyd process options
        template_override: Custom HTML template path
        debug: Enable development mode with auto-reload (default: False)

    Raises:
        InstallationError: If ttyd binary installation fails
        PlatformNotSupportedError: If running on an unsupported platform
        DependencyError: If required system libraries are missing
        TTYDStartupError: If ttyd fails to start
        ClientScriptError: If client script cannot be found or executed
        ConfigurationError: If provided configuration values are invalid

    Example:
        ```python
        from fastapi import FastAPI
        from terminaide import serve_tty

        app = FastAPI()
        
        # Basic usage
        serve_tty(app, "client.py")

        # Custom configuration
        serve_tty(
            app,
            "client.py",
            mount_path="/terminal",
            theme={"background": "#1a1a1a"},
            debug=True
        )
        ```

    Notes:
        - For Docker deployments, the package automatically handles ttyd installation
        - Binary installation happens on first use and is cached for subsequent runs
        - In Docker, required system libraries (libwebsockets, json-c) must be present
    """
    # Create configuration object
    config = TTYDConfig(
        client_script=client_script,
        mount_path=mount_path,
        port=port,
        theme=theme or {"background": "black"},
        ttyd_options=ttyd_options or {},
        template_override=template_override,
        debug=debug
    )
    
    # Configure the application with our ttyd setup
    _configure_app(app, config)