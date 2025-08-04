# terminaide/__init__.py

"""terminaide: Serve Python CLI applications in the browser using ttyd.

This package provides tools to easily serve Python CLI applications through
a browser-based terminal using ttyd. It handles binary installation and
management automatically across supported platforms.

Public API:
- serve_function(): Serve a Python function in a browser terminal
- serve_script(): Serve a Python script file in a terminal  
- serve_apps(): Integrate multiple terminals into a FastAPI application
- AutoIndex: Create navigable index pages (HTML or Curses)
- terminascii(): Generate ASCII banners
- Monitor: Process output monitoring with rich terminal interface

Supported Platforms:
- Linux x86_64 (Docker containers)
- macOS ARM64 (Apple Silicon)
"""

import logging
from pathlib import Path
from fastapi import FastAPI
from typing import Optional, Dict, Any, Union, List, Callable

from .core.config import TerminaideConfig, build_config
from .core.factory import ServeWithConfig
from .core.index import AutoIndex
from .core.terminascii import terminascii
from .core.monitor import ServerMonitor

# Get package-level logger (configuration happens when serve_* functions are called)
logger = logging.getLogger("terminaide")

################################################################################
# Shared Helper Functions
################################################################################


def _prepare_config(
    config: Optional[TerminaideConfig], banner: Union[bool, str], **kwargs
) -> TerminaideConfig:
    """Prepare configuration with common parameters."""
    kwargs["banner"] = banner
    return build_config(config, kwargs)


def _auto_generate_title(
    cfg: TerminaideConfig, mode: str, target: Any, kwargs: Dict
) -> None:
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
# APIs
################################################################################


def serve_script(
    script_path: Union[str, Path],
    port: int = 8000,
    title: Optional[str] = None,
    theme: Optional[Dict[str, str]] = None,
    log_level: Optional[str] = "info",
    args: Optional[List[str]] = None,
    dynamic: bool = False,
    args_param: str = "args",
) -> None:
    """Serve a Python script in a browser terminal.

    Creates a web-accessible terminal that runs the provided Python script.

    Args:
        script_path: Path to the script file to serve
        port: Web server port (default: 8000)
        title: Terminal window title (default: auto-generated from script name)
        theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
        log_level: Logging level ("debug", "info", "warning", "error", None) (default: "info")
        args: Command-line arguments to pass to the script (default: None)
        dynamic: Enable dynamic arguments via URL query parameters (default: False)
        args_param: Name of the query parameter for dynamic arguments (default: "args")

    Examples:
        Basic usage:
            serve_script("my_script.py")

        With custom configuration:
            serve_script("my_script.py", port=8080, title="My Script")
            serve_script("my_script.py", theme={"background": "navy"})
            serve_script("my_script.py", log_level="debug")
        
        With arguments:
            serve_script("deploy.py", args=["--verbose", "--dry-run"])
            serve_script("cli.py", dynamic=True)  # Args from URL: /cli?args=value1,value2
            serve_script("cli.py", dynamic=True, args_param="with")  # Args from URL: /cli?with=value1,value2
    """
    kwargs = {}
    if port != 8000:
        kwargs["port"] = port
    if title is not None:
        kwargs["title"] = title
    if theme is not None:
        kwargs["theme"] = theme
    if log_level != "info":
        kwargs["log_level"] = log_level
    if args is not None:
        kwargs["args"] = args
    if dynamic:
        kwargs["dynamic"] = dynamic
    if args_param != "args":
        kwargs["args_param"] = args_param

    cfg = _prepare_config(None, True, **kwargs)
    cfg._target = Path(script_path)
    cfg._mode = "script"

    _auto_generate_title(cfg, "script", cfg._target, kwargs)
    ServeWithConfig.serve(cfg)


def serve_function(
    func: Callable,
    port: int = 8000,
    title: Optional[str] = None,
    theme: Optional[Dict[str, str]] = None,
    log_level: Optional[str] = "info",
    args: Optional[List[str]] = None,
    dynamic: bool = False,
    args_param: str = "args",
) -> None:
    """Serve a Python function in a browser terminal.

    Creates a web-accessible terminal that runs the provided Python function.

    Args:
        func: The function to serve in the terminal
        port: Web server port (default: 8000)
        title: Terminal window title (default: auto-generated from function name)
        theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
        log_level: Logging level ("debug", "info", "warning", "error", None) (default: "info")
        args: Command-line arguments to pass to the function via sys.argv (default: None)
        dynamic: Enable dynamic arguments via URL query parameters (default: False)
        args_param: Name of the query parameter for dynamic arguments (default: "args")

    Examples:
        Basic usage:
            serve_function(my_function)

        With custom configuration:
            serve_function(my_function, port=8080, title="My CLI Tool")
            serve_function(my_function, theme={"background": "navy", "foreground": "white"})
            serve_function(my_function, log_level="debug")
        
        With arguments (compatible with Click, Fire, argparse):
            serve_function(my_cli_function, args=["--verbose", "--output", "result.txt"])
            serve_function(my_cli_function, dynamic=True)  # Args from URL: /func?args=verbose,output
            serve_function(my_cli_function, dynamic=True, args_param="with")  # Args from URL: /func?with=verbose,output

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
    if log_level != "info":
        kwargs["log_level"] = log_level
    if args is not None:
        kwargs["args"] = args
    if dynamic:
        kwargs["dynamic"] = dynamic
    if args_param != "args":
        kwargs["args_param"] = args_param

    cfg = _prepare_config(None, True, **kwargs)
    cfg._target = func
    cfg._mode = "function"

    _auto_generate_title(cfg, "function", func, kwargs)
    ServeWithConfig.serve(cfg)


def serve_apps(
    app: FastAPI,
    terminal_routes: Dict[
        str, Union[str, Path, List, Dict[str, Any], Callable, AutoIndex]
    ],
    config: Optional[TerminaideConfig] = None,
    banner: Union[bool, str] = True,
    log_level: Optional[str] = "info",
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
        log_level: Logging level ("debug", "info", "warning", "error", None) (default: "info")
        **kwargs: Additional configuration overrides

    Terminal Routes Configuration:
        Each value in terminal_routes can be:
        - String/Path: Script file path
        - Callable: Python function
        - AutoIndex: Navigable menu page (HTML or Curses) that can also define routes
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

        AutoIndex with embedded route definitions (no duplication):
            serve_apps(app, {
                "/": AutoIndex(
                    type="html",
                    title="My Tools",
                    menu=[
                        {"path": "/calculator", "title": "Calculator", "function": calc_fn},
                        {"path": "/logs", "title": "View Logs", "script": "logs.py"},
                        {"path": "/admin", "title": "Admin", "function": admin_fn, 
                         "launcher_args": {"preview_image": "admin.png"}}
                    ]
                )
            })

        Advanced configuration:
            serve_apps(app, {
                "/deploy": ["deploy.py", "--verbose"],
                "/admin": {
                    "function": admin_function,
                    "title": "Admin Terminal",
                    "preview_image": "admin.png"
                },
                "/cli": {
                    "script": "cli.py",
                    "dynamic": True,
                    "args_param": "with"  # Use ?with=arg1,arg2 instead of ?args=arg1,arg2
                }
            }, log_level="debug")

    Note:
        For simple single-terminal applications, consider using serve_function
        or serve_script instead.
    """
    if not terminal_routes:
        logger.warning(
            "No terminal routes provided to serve_apps(). No terminals will be served."
        )
        return

    if log_level != "info":
        kwargs["log_level"] = log_level
    
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
# terminascii - Generate ASCII banners
# ServerMonitor - Process output monitoring with rich terminal interface

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
    "terminascii",
    "ServerMonitor",
]