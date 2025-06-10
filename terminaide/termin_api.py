# termin-api.py

"""Complete public API for terminaide: Serve Python CLI applications in the browser using ttyd.

This module serves as the single source of truth for all public API components:

Core Functions:
- serve_function: Serve a Python function in a browser terminal
- serve_script: Serve a Python script file in a terminal  
- serve_apps: Integrate multiple terminals into a FastAPI application

UI Components:
- HtmlIndex: Create navigable web index pages
- CursesIndex: Create terminal-based index pages

Utilities:
- termin_ascii: Generate ASCII banners
- terminarcade: Collection of terminal games
"""

import logging
from pathlib import Path
from fastapi import FastAPI
from typing import Optional, Dict, Any, Union, List, Callable

from .core.app_config import TerminaideConfig, build_config
from .core.app_factory import ServeWithConfig
from .core.index_html import HtmlIndex
from .core.index_curses import CursesIndex
from .core.termin_ascii import termin_ascii

logger = logging.getLogger("terminaide")


# Common configuration parameters documentation
COMMON_KWARGS_DOC = """
    - port: Web server port (default: 8000)
    - title: Terminal window title (default: auto-generated)
    - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
    - debug: Enable debug mode (default: True)
    - forward_env: Control environment variable forwarding (default: True)
    - ttyd_options: Options for the ttyd process
    - template_override: Custom HTML template path
    - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
    - preview_image: Custom preview image for social media sharing (default: None)
    - configure_logging: Whether to configure Terminaide's logging handlers (default: True)
"""

################################################################################
# Helper Functions
################################################################################

def _prepare_config(
    config: Optional[TerminaideConfig],
    desktop: bool,
    desktop_width: int,
    desktop_height: int,
    banner: Union[bool, str],
    **kwargs
) -> TerminaideConfig:
    """Prepare configuration with common parameters."""
    # Add desktop parameters to kwargs if provided
    if desktop:
        kwargs["desktop"] = desktop
    if "desktop_width" not in kwargs:
        kwargs["desktop_width"] = desktop_width
    if "desktop_height" not in kwargs:
        kwargs["desktop_height"] = desktop_height
    # Add banner parameter to kwargs
    kwargs["banner"] = banner
    
    return build_config(config, kwargs)


def _auto_generate_title(cfg: TerminaideConfig, mode: str, target: Any, kwargs: Dict) -> None:
    """Auto-generate title if not specified by user."""
    if "title" in kwargs or (cfg.title != "Terminal"):
        return
    
    if mode == "function":
        cfg.title = f"{target.__name__}()"
    elif mode == "script":
        # Check if we're coming from serve_function with a default title
        if hasattr(cfg, "_original_function_name"):
            cfg.title = f"{cfg._original_function_name}()"
        else:
            cfg.title = Path(target).name

################################################################################
# Public API
################################################################################


def serve_function(
    func: Callable,
    config: Optional[TerminaideConfig] = None,
    desktop: bool = False,
    desktop_width: int = 1200,
    desktop_height: int = 800,
    banner: Union[bool, str] = True,
    **kwargs,
) -> None:
    f"""Serve a Python function in a browser terminal or desktop window.

    This function creates a web-accessible terminal that runs the provided Python function.

    Args:
        func: The function to serve in the terminal
        config: Configuration options for the terminal
        desktop: If True, open in a desktop window instead of browser (default: False)
        desktop_width: Width of desktop window in pixels (default: 1200)
        desktop_height: Height of desktop window in pixels (default: 800)
        banner: Controls banner display. True shows Rich panel, False disables banner,
               string value prints the string directly (default: True)
        **kwargs: Additional configuration overrides:
{COMMON_KWARGS_DOC}
    """
    cfg = _prepare_config(config, desktop, desktop_width, desktop_height, banner, **kwargs)
    cfg._target = func
    cfg._mode = "function"
    
    _auto_generate_title(cfg, "function", func, kwargs)
    ServeWithConfig.serve(cfg)


def serve_script(
    script_path: Union[str, Path],
    config: Optional[TerminaideConfig] = None,
    desktop: bool = False,
    desktop_width: int = 1200,
    desktop_height: int = 800,
    banner: Union[bool, str] = True,
    **kwargs,
) -> None:
    f"""Serve a Python script in a browser terminal or desktop window.

    This function creates a web-accessible terminal that runs the provided Python script.

    Args:
        script_path: Path to the script file to serve
        config: Configuration options for the terminal
        desktop: If True, open in a desktop window instead of browser (default: False)
        desktop_width: Width of desktop window in pixels (default: 1200)
        desktop_height: Height of desktop window in pixels (default: 800)
        banner: Controls banner display. True shows Rich panel, False disables banner,
               string value prints the string directly (default: True)
        **kwargs: Additional configuration overrides:
{COMMON_KWARGS_DOC}
    """
    cfg = _prepare_config(config, desktop, desktop_width, desktop_height, banner, **kwargs)
    cfg._target = Path(script_path)
    cfg._mode = "script"
    
    _auto_generate_title(cfg, "script", cfg._target, kwargs)
    ServeWithConfig.serve(cfg)


def serve_apps(
    app: FastAPI,
    terminal_routes: Dict[
        str, Union[str, Path, List, Dict[str, Any], Callable, HtmlIndex]
    ],
    config: Optional[TerminaideConfig] = None,
    desktop: bool = False,
    desktop_width: int = 1200,
    desktop_height: int = 800,
    banner: Union[bool, str] = True,
    **kwargs,
) -> None:
    """Integrate multiple terminals and index pages into a FastAPI application.

    This function configures a FastAPI application to serve multiple terminal instances
    and/or index pages at different routes.

    Args:
        app: FastAPI application to extend
        terminal_routes: Dictionary mapping paths to scripts, functions, or index pages. Each value can be:
            - A string or Path object pointing to a script file
            - A Python callable function object
            - An HtmlIndex instance for creating navigable menu pages
            - A list [script_path, arg1, arg2, ...] for scripts with arguments
            - A dictionary with advanced configuration:
                - For scripts: {"client_script": "path.py", "args": [...], ...}
                - For functions: {"function": callable_func, ...}
                - Other options: "title", "port", "preview_image", etc.
        config: Configuration options for the terminals
        desktop: If True, open in a desktop window instead of browser (default: False)
                Note: Desktop mode for serve_apps is not yet implemented
        desktop_width: Width of desktop window in pixels (default: 1200)
        desktop_height: Height of desktop window in pixels (default: 800)
        banner: Controls banner display. True shows Rich panel, False disables banner,
               string value prints the string directly (default: True)
        **kwargs: Additional configuration overrides:
{COMMON_KWARGS_DOC}
            Additional serve_apps specific options:
            - ttyd_port: Base port for ttyd processes (default: 7681)
            - mount_path: Base path for terminal mounting (default: "/")
            - preview_image: Default preview image for social media sharing (default: None)
                            Can also be specified per route in terminal_routes config.

    Examples:
        ```python
        from fastapi import FastAPI
        from terminaide import serve_apps, HtmlIndex

        app = FastAPI()

        @app.get("/")
        async def root():
            return {"message": "Welcome to my terminal app"}

        # Define a function to serve in a terminal
        def greeting():
            name = input("What's your name? ")
            print(f"Hello, {name}!")
            favorite = input("What's your favorite programming language? ")
            print(f"{favorite} is a great choice!")

        serve_apps(
            app,
            terminal_routes={
                # Simple index page at root (single menu, no cycling)
                "/": HtmlIndex(
                    title="CLI TOOLS",
                    subtitle="Select a tool to get started.",
                    menu=[
                        {
                            "label": "Use arrow keys to navigate, Enter to select",
                            "options": [
                                {"path": "/deploy", "title": "DEPLOY"},
                                {"path": "/monitor", "title": "MONITOR"},
                                {"path": "/logs", "title": "LOGS"},
                                {"path": "https://github.com/myorg", "title": "GITHUB"},
                            ]
                        }
                    ]
                ),

                # Script-based terminals
                "/deploy": "scripts/deploy.py",
                "/monitor": ["scripts/monitor.py", "--verbose"],
                "/logs": {
                    "client_script": "scripts/logs.py",
                    "title": "System Logs"
                },

                # Function-based terminals
                "/hello": greeting,
                "/admin": {
                    "function": greeting,
                    "title": "Admin Greeting Terminal",
                    "preview_image": "admin_preview.png"
                },

                # Index page with multiple menus and cycling
                "/tools": HtmlIndex(
                    title="TOOLS",
                    menu={
                        "cycle_key": "shift+g",
                        "groups": [
                            {
                                "label": "Basic Tools",
                                "options": [
                                    {"path": "/tools/format", "title": "FORMAT"},
                                    {"path": "/tools/lint", "title": "LINT"},
                                ]
                            },
                            {
                                "label": "Advanced Tools",
                                "options": [
                                    {"path": "/tools/profile", "title": "PROFILE"},
                                    {"path": "/tools/debug", "title": "DEBUG"},
                                ]
                            }
                        ]
                    },
                    epititle="[shift+g to cycle tool categories]"
                )
            }
        )
        ```

    Note:
        Desktop mode for serve_apps is not yet implemented. Desktop mode currently
        supports serve_function and serve_script only.
    """
    if not terminal_routes:
        logger.warning(
            "No terminal routes provided to serve_apps(). No terminals will be served."
        )
        return

    cfg = _prepare_config(config, desktop, desktop_width, desktop_height, banner, **kwargs)
    cfg._target = terminal_routes
    cfg._app = app
    cfg._mode = "apps"

    ServeWithConfig.serve(cfg)


# Export all public API components
__all__ = [
    # Core API
    "serve_function",
    "serve_script", 
    "serve_apps",
    # UI components
    "HtmlIndex",
    "CursesIndex",
    # Utilities
    "termin_ascii",
]
