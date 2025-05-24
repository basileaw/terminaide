# termin-api.py

"""Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application, with four distinct API paths:

1. serve_function: simplest entry point - run a function in a terminal
2. serve_script: simple path - run a Python script in a terminal
3. serve_apps: advanced path - integrate multiple terminals into a FastAPI application
4. meta_serve: advanced path - run a server that serves terminal instances in a browser terminal
"""

import os
import inspect
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
    desktop: bool = False,
    desktop_width: int = 1200,
    desktop_height: int = 800,
    **kwargs,
) -> None:
    """Serve a Python function in a browser terminal or desktop window.

    This function creates a web-accessible terminal that runs the provided Python function.

    Args:
        func: The function to serve in the terminal
        config: Configuration options for the terminal
        desktop: If True, open in a desktop window instead of browser (default: False)
        desktop_width: Width of desktop window in pixels (default: 1200)
        desktop_height: Height of desktop window in pixels (default: 800)
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
            - preview_image: Custom preview image for social media sharing (default: None)

    Note:
        Desktop mode requires pywebview and requests libraries. Install with:
        pip install pywebview requests
    """
    # Add desktop parameters to kwargs if provided
    if desktop:
        kwargs["desktop"] = desktop
    if "desktop_width" not in kwargs:
        kwargs["desktop_width"] = desktop_width
    if "desktop_height" not in kwargs:
        kwargs["desktop_height"] = desktop_height

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
    desktop: bool = False,
    desktop_width: int = 1200,
    desktop_height: int = 800,
    **kwargs,
) -> None:
    """Serve a Python script in a browser terminal or desktop window.

    This function creates a web-accessible terminal that runs the provided Python script.

    Args:
        script_path: Path to the script file to serve
        config: Configuration options for the terminal
        desktop: If True, open in a desktop window instead of browser (default: False)
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
            - preview_image: Custom preview image for social media sharing (default: None)

    Note:
        Desktop mode requires pywebview and requests libraries. Install with:
        pip install pywebview requests
    """
    # Add desktop parameters to kwargs if provided
    if desktop:
        kwargs["desktop"] = desktop
    if "desktop_width" not in kwargs:
        kwargs["desktop_width"] = desktop_width
    if "desktop_height" not in kwargs:
        kwargs["desktop_height"] = desktop_height

    cfg = build_config(config, kwargs)
    cfg._target = Path(script_path)
    cfg._mode = "script"

    # Auto-generate title if not specified
    if "title" not in kwargs and (config is None or config.title == "Terminal"):
        # Check if we're coming from serve_function with a default title
        if hasattr(cfg, "_original_function_name"):
            cfg.title = f"{cfg._original_function_name}()"
        else:
            script_name = Path(script_path).name
            cfg.title = f"{script_name}"

    ServeWithConfig.serve(cfg)


def serve_apps(
    app: FastAPI,
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any], Callable]],
    config: Optional[TerminaideConfig] = None,
    desktop: bool = False,
    desktop_width: int = 1200,
    desktop_height: int = 800,
    **kwargs,
) -> None:
    """Integrate multiple terminals into a FastAPI application.

    This function configures a FastAPI application to serve multiple terminal instances
    at different routes.

    Args:
        app: FastAPI application to extend
        terminal_routes: Dictionary mapping paths to scripts or functions. Each value can be:
            - A string or Path object pointing to a script file
            - A Python callable function object
            - A list [script_path, arg1, arg2, ...] for scripts with arguments
            - A dictionary with advanced configuration:
                - For scripts: {"client_script": "path.py", "args": [...], ...}
                - For functions: {"function": callable_func, ...}
                - Other options: "title", "port", "preview_image", etc.
        config: Configuration options for the terminals
        desktop: If True, open in a desktop window instead of browser (default: False)
                Note: Desktop mode for serve_apps is not yet implemented
        **kwargs: Additional configuration overrides:
            - port: Web server port (default: 8000)
            - title: Default terminal window title (default: auto-generated)
            - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
            - debug: Enable debug mode (default: True)
            - ttyd_port: Base port for ttyd processes (default: 7681)
            - mount_path: Base path for terminal mounting (default: "/")
            - forward_env: Control environment variable forwarding (default: True)
            - ttyd_options: Options for the ttyd processes
            - template_override: Custom HTML template path
            - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
            - preview_image: Default preview image for social media sharing (default: None)
                            Can also be specified per route in terminal_routes config.

    Examples:
        ```python
        from fastapi import FastAPI
        from terminaide import serve_apps

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
                # Script-based terminals
                "/cli1": "script1.py",
                "/cli2": ["script2.py", "--arg1", "value"],
                "/cli3": {
                    "client_script": "script3.py",
                    "title": "Advanced CLI"
                },

                # Function-based terminals
                "/hello": greeting,
                "/admin": {
                    "function": greeting,
                    "title": "Admin Greeting Terminal",
                    "preview_image": "admin_preview.png"
                }
            }
        )
        ```

    Note:
        Desktop mode for serve_apps is not yet implemented. Desktop mode currently
        supports serve_function, serve_script, and meta_serve only.
    """
    if not terminal_routes:
        logger.warning(
            "No terminal routes provided to serve_apps(). No terminals will be served."
        )
        return

    # Add desktop parameters to kwargs if provided
    if desktop:
        kwargs["desktop"] = desktop
    if "desktop_width" not in kwargs:
        kwargs["desktop_width"] = desktop_width
    if "desktop_height" not in kwargs:
        kwargs["desktop_height"] = desktop_height

    cfg = build_config(config, kwargs)
    cfg._target = terminal_routes
    cfg._app = app
    cfg._mode = "apps"

    ServeWithConfig.serve(cfg)


def meta_serve(
    target: Union[Callable, str, Path],
    app_dir: Optional[Union[str, Path]] = None,
    desktop: bool = False,
    desktop_width: int = 1200,
    desktop_height: int = 800,
    **kwargs,
) -> None:
    """Serve a meta-server (a server that serves terminal instances) in a browser terminal or desktop window,
    preserving correct directory context for script resolution.

    This function creates a web-accessible terminal that runs a server function or script which itself
    serves terminal instances. This enables a "meta-server" where both the server process
    and the terminals it manages are accessible via web browsers or a desktop window.

    Args:
        target: The function or script that starts your server (typically a function using serve_apps
                or a script file that starts a server)
        app_dir: The directory containing your application (defaults to the directory
                 of the file where the function is defined or the script is located)
        desktop: If True, open in a desktop window instead of browser (default: False)
        **kwargs: Additional configuration overrides:
            - port: Web server port (default: 8000)
            - title: Terminal window title (default: "{target_name} Server")
            - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
            - debug: Enable debug mode (default: True)
            - reload: Enable auto-reload on code changes (default: False)
            - forward_env: Control environment variable forwarding (default: True)
            - ttyd_options: Options for the ttyd process
            - template_override: Custom HTML template path
            - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
            - preview_image: Custom preview image for social media sharing (default: None)

    Examples:
        ```python
        from fastapi import FastAPI
        from terminaide import serve_apps, meta_serve

        # Example 1: Meta-serve a function
        def run_server():
            app = FastAPI()

            @app.get("/")
            async def root():
                return {"message": "Welcome to my terminal app"}

            serve_apps(
                app,
                terminal_routes={"/cli": "my_script.py"}
            )

        # Run the server function in a browser terminal
        meta_serve(run_server)

        # Run the server function in a desktop window
        meta_serve(run_server, desktop=True)

        # Example 2: Meta-serve a script
        meta_serve("server_script.py")

        # Meta-serve a script in desktop mode
        meta_serve("server_script.py", desktop=True)
        ```

    Note:
        Desktop mode requires pywebview and requests libraries. Install with:
        pip install pywebview requests
    """
    # Add desktop parameter to kwargs if provided
    if desktop:
        kwargs["desktop"] = desktop
    if "desktop_width" not in kwargs:
        kwargs["desktop_width"] = desktop_width
    if "desktop_height" not in kwargs:
        kwargs["desktop_height"] = desktop_height

    cfg = build_config(None, kwargs)
    cfg._target = target
    cfg._mode = "meta"

    # Determine target name for title generation
    if callable(target):
        target_name = target.__name__
    else:
        target_name = Path(target).stem

    # Auto-generate title if not specified
    if "title" not in kwargs and (cfg is None or cfg.title == "Terminal"):
        cfg.title = f"{target_name} Server"

    # If app_dir is not specified, try to determine it from the target
    if app_dir is None:
        try:
            if callable(target):
                # Get the source file of the function
                source_file = inspect.getsourcefile(target)
                if source_file:
                    app_dir = os.path.dirname(os.path.abspath(source_file))
                    logger.debug(f"Detected app_dir from function source: {app_dir}")
            else:
                # Get the directory of the script file
                script_path = Path(target)
                if not script_path.is_absolute():
                    script_path = Path.cwd() / script_path
                if script_path.exists():
                    app_dir = script_path.parent
                    logger.debug(f"Detected app_dir from script path: {app_dir}")
                else:
                    logger.warning(f"Script not found: {script_path}")
        except Exception as e:
            logger.warning(f"Could not determine app_dir from target: {e}")

    # Store the app_dir in the config for use by the wrapper script generator
    if app_dir:
        cfg._app_dir = Path(app_dir)

    ServeWithConfig.serve(cfg)
