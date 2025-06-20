# termin_api.py

"""Complete public API for terminaide: Serve Python CLI applications in the browser using ttyd.

This module serves as the single source of truth for all public API components.
"""

import logging
from pathlib import Path
from fastapi import FastAPI
from typing import Optional, Dict, Any, Union, List, Callable

from .core.app_config import TerminaideConfig, build_config
from .core.app_factory import ServeWithConfig
from .core.index_api import AutoIndex
from .core.termin_ascii import termin_ascii
from .core.monitor import Monitor

logger = logging.getLogger("terminaide")

################################################################################
# Shared Helper Functions
################################################################################

def _prepare_config(
    config: Optional[TerminaideConfig],
    banner: Union[bool, str],
    **kwargs
) -> TerminaideConfig:
    """Prepare configuration with common parameters."""
    kwargs["banner"] = banner
    return build_config(config, kwargs)


def _auto_generate_title(cfg: TerminaideConfig, mode: str, target: Any, kwargs: Dict) -> None:
    """Auto-generate title if not specified by user."""
    if "title" in kwargs or (cfg.title != "Terminal"):
        return
    
    if mode == "function":
        cfg.title = f"{target.__name__}()"
    elif mode == "script":
        if hasattr(cfg, "_original_function_name"):
            cfg.title = f"{cfg._original_function_name}()"
        else:
            cfg.title = Path(target).name

################################################################################
# Solo Server API
################################################################################

def serve_function(
    func: Callable,
    port: int = 8000,
    title: Optional[str] = None,
    theme: Optional[Dict[str, str]] = None,
) -> None:
    """Serve a Python function in a browser terminal.

    Creates a web-accessible terminal that runs the provided Python function.

    Args:
        func: The function to serve in the terminal
        port: Web server port (default: 8000)
        title: Terminal window title (default: auto-generated from function name)
        theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})

    Examples:
        Basic usage:
            serve_function(my_function)
        
        With custom configuration:
            serve_function(my_function, port=8080, title="My CLI Tool")
            serve_function(my_function, theme={"background": "navy", "foreground": "white"})

    Note:
        For advanced configuration options like environment variables, authentication,
        or custom templates, use serve_apps() instead.
    """
    kwargs = {}
    if port != 8000:
        kwargs["port"] = port
    if title is not None:
        kwargs["title"] = title
    if theme is not None:
        kwargs["theme"] = theme
    
    cfg = _prepare_config(None, True, **kwargs)
    cfg._target = func
    cfg._mode = "function"
    
    _auto_generate_title(cfg, "function", func, kwargs)
    ServeWithConfig.serve(cfg)


def serve_script(
    script_path: Union[str, Path],
    port: int = 8000,
    title: Optional[str] = None,
    theme: Optional[Dict[str, str]] = None,
) -> None:
    """Serve a Python script in a browser terminal.

    Creates a web-accessible terminal that runs the provided Python script.

    Args:
        script_path: Path to the script file to serve
        port: Web server port (default: 8000)
        title: Terminal window title (default: auto-generated from script name)
        theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
    
    Examples:
        Basic usage:
            serve_script("my_script.py")
        
        With custom configuration:
            serve_script("my_script.py", port=8080, title="My Script")
            serve_script("my_script.py", theme={"background": "navy"})
    """
    kwargs = {}
    if port != 8000:
        kwargs["port"] = port
    if title is not None:
        kwargs["title"] = title
    if theme is not None:
        kwargs["theme"] = theme
    
    cfg = _prepare_config(None, True, **kwargs)
    cfg._target = Path(script_path)
    cfg._mode = "script"
    
    _auto_generate_title(cfg, "script", cfg._target, kwargs)
    ServeWithConfig.serve(cfg)

################################################################################
# Apps Server API
################################################################################

def serve_apps(
    app: FastAPI,
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any], Callable, AutoIndex]],
    config: Optional[TerminaideConfig] = None,
    banner: Union[bool, str] = True,
    **kwargs,
) -> None:
    """Integrate multiple terminals and index pages into a FastAPI application.

    Configures a FastAPI application to serve multiple terminal instances and/or 
    index pages at different routes.

    Args:
        app: FastAPI application to extend
        terminal_routes: Dictionary mapping paths to scripts, functions, or index pages
        config: Configuration options for the terminals
        banner: Controls banner display (default: True)
        **kwargs: Additional configuration overrides

    Terminal Routes Configuration:
        Each value in terminal_routes can be:
        - String/Path: Script file path
        - Callable: Python function
        - AutoIndex: Navigable menu page (HTML or Curses)
        - List: [script_path, arg1, arg2, ...] for scripts with arguments
        - Dict: Advanced configuration with "script"/"function" key plus options

    Common Configuration Options:
        - port: Web server port (default: 8000)
        - title: Terminal window title (default: auto-generated)
        - theme: Terminal theme colors
        - ttyd_port: Base port for ttyd processes (default: 7681)
        - mount_path: Base path for terminal mounting (default: "/")
        - preview_image: Default preview image for social media sharing

    Examples:
        Simple terminal routes:
            serve_apps(app, {
                "/script": "my_script.py",
                "/hello": my_function,
                "/": AutoIndex(type="html", title="MENU", menu=[...])
            })

        Advanced configuration:
            serve_apps(app, {
                "/deploy": ["deploy.py", "--verbose"],
                "/admin": {
                    "function": admin_function,
                    "title": "Admin Terminal",
                    "preview_image": "admin.png"
                }
            })

    Note:
        For simple single-terminal applications, consider using serve_function 
        or serve_script instead.
    """
    if not terminal_routes:
        logger.warning(
            "No terminal routes provided to serve_apps(). No terminals will be served."
        )
        return

    cfg = _prepare_config(config, banner, **kwargs)
    cfg._target = terminal_routes
    cfg._app = app
    cfg._mode = "apps"

    ServeWithConfig.serve(cfg)

################################################################################
# UI Components & Utilities
################################################################################

# UI Components are imported and re-exported
# AutoIndex - Create navigable index pages (HTML or Curses)

# Utilities are imported and re-exported  
# termin_ascii - Generate ASCII banners
# Monitor - Process output monitoring with rich terminal interface

################################################################################
# Public API Exports
################################################################################

__all__ = [
    # Solo Server API
    "serve_function",
    "serve_script", 
    # Apps Server API
    "serve_apps",
    # UI Components
    "AutoIndex",
    # Utilities
    "termin_ascii",
    "Monitor",
]
