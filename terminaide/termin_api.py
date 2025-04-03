# termin-api.py

"""Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application, with three distinct API paths:

1. serve_function: simplest entry point - run a function in a terminal
2. serve_script: simple path - run a Python script in a terminal  
3. serve_apps: advanced path - integrate multiple terminals into a FastAPI application
"""

import logging
from pathlib import Path
from fastapi import FastAPI
from typing import Optional, Dict, Any, Union, List, Callable

from .core.app_config import TerminaideConfig, build_config
from .core.app_factory import ServeWithConfig, AppFactory

logger = logging.getLogger("terminaide")

# Make the factory functions accessible from the original paths for backward compatibility
function_app_factory = AppFactory.function_app_factory
script_app_factory = AppFactory.script_app_factory

################################################################################
# Public API
################################################################################

def serve_function(
    func: Callable,
    config: Optional[TerminaideConfig] = None,
    **kwargs) -> None:
    """Serve a Python function in a browser terminal.
    
    This function creates a web-accessible terminal that runs the provided Python function.
    
    Args:
        func: The function to serve in the terminal
        config: Configuration options for the terminal
        **kwargs: Additional configuration overrides:
            - port: Web server port (default: 8000)
            - title: Terminal window title (default: "{func_name}()")
            - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
            - debug: Enable debug mode (default: True)
            - reload: Enable auto-reload on code changes (default: False)
            - forward_env: Control environment variable forwarding (default: True)
            - ttyd_options: Options for the ttyd process
            - template_override: Custom HTML template path
            - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
    """
    cfg = build_config(config, kwargs)
    cfg._target = func
    cfg._mode = "function"
    
    # Auto-generate title if not specified
    if "title" not in kwargs and (config is None or config.title == "Terminal"):
        cfg.title = f"{func.__name__}()"
    
    ServeWithConfig.serve(cfg)


def serve_script(
    script_path: Union[str, Path],
    config: Optional[TerminaideConfig] = None,
    **kwargs) -> None:
    """Serve a Python script in a browser terminal.
    
    This function creates a web-accessible terminal that runs the provided Python script.
    
    Args:
        script_path: Path to the script file to serve
        config: Configuration options for the terminal
        **kwargs: Additional configuration overrides:
            - port: Web server port (default: 8000)
            - title: Terminal window title (default: "Script Name")
            - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
            - debug: Enable debug mode (default: True)
            - reload: Enable auto-reload on code changes (default: False)
            - forward_env: Control environment variable forwarding (default: True)
            - ttyd_options: Options for the ttyd process
            - template_override: Custom HTML template path
            - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
    """
    cfg = build_config(config, kwargs)
    cfg._target = Path(script_path)
    cfg._mode = "script"
    
    # Auto-generate title if not specified
    if "title" not in kwargs and (config is None or config.title == "Terminal"):
        # Check if we're coming from serve_function with a default title
        if hasattr(cfg, '_original_function_name'):
            cfg.title = f"{cfg._original_function_name}()"
        else:
            script_name = Path(script_path).name
            cfg.title = f"{script_name}"
    
    ServeWithConfig.serve(cfg)


def serve_apps(
    app: FastAPI,
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any]]],
    config: Optional[TerminaideConfig] = None,
    **kwargs) -> None:
    """Integrate multiple terminals into a FastAPI application.
    
    This function configures a FastAPI application to serve multiple terminal instances
    at different routes.
    
    Args:
        app: FastAPI application to extend
        terminal_routes: Dictionary mapping paths to scripts
        config: Configuration options for the terminals
        **kwargs: Additional configuration overrides:
            - port: Web server port (default: 8000)
            - title: Default terminal window title (default: auto-generated based on script name)
            - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
            - debug: Enable debug mode (default: True)
            - ttyd_port: Base port for ttyd processes (default: 7681)
            - mount_path: Base path for terminal mounting (default: "/")
            - forward_env: Control environment variable forwarding (default: True)
            - ttyd_options: Options for the ttyd processes
            - template_override: Custom HTML template path
            - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
    """
    if not terminal_routes:
        logger.warning("No terminal routes provided to serve_apps(). No terminals will be served.")
        return
        
    cfg = build_config(config, kwargs)
    cfg._target = terminal_routes
    cfg._app = app
    cfg._mode = "apps"
    
    ServeWithConfig.serve(cfg)