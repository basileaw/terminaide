# protottyde/__init__.py

"""
Protottyde: Serve Python CLI applications in the browser using ttyd.

This package provides tools to easily serve Python CLI applications through
a browser-based terminal using ttyd.
"""

from fastapi import FastAPI
from pathlib import Path
from typing import Optional, Dict, Any, Union

from .core.settings import TTYDConfig
from .serve import serve_tty
from .exceptions import (
    TTYDNotFoundError,
    TTYDStartupError, 
    ClientScriptError
)

__version__ = "0.1.0"
__all__ = [
    "serve_tty",
    "TTYDConfig",
    "TTYDNotFoundError",
    "TTYDStartupError",
    "ClientScriptError"
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
        TTYDNotFoundError: If ttyd is not installed
        TTYDStartupError: If ttyd fails to start
        ClientScriptError: If client script cannot be found or executed
        ValueError: If provided configuration values are invalid

    Example:
        ```python
        from fastapi import FastAPI
        from protottyde import serve_tty

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
    """
    config = TTYDConfig(
        client_script=client_script,
        mount_path=mount_path,
        port=port,
        theme=theme or {"background": "black"},
        ttyd_options=ttyd_options or {},
        template_override=template_override,
        debug=debug
    )
    
    from .serve import _configure_app
    _configure_app(app, config)