# app_runner.py

"""
Application runner implementation for Terminaide.

This module contains the ServeWithConfig class that handles running applications
in different Terminaide modes (function, script, apps).
"""

import os
import sys
import time
import signal
import logging
import uvicorn
import tempfile
import subprocess
import webview
from pathlib import Path
from fastapi import FastAPI
from typing import Dict, Any, Union
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware

from .app_config import (
    TerminaideConfig,
    convert_terminaide_config_to_ttyd_config,
    terminaide_lifespan,
    smart_resolve_path,
)
from .app_wrappers import (
    generate_function_wrapper,
)

logger = logging.getLogger("terminaide")


class _ProxyHeaderMiddleware(BaseHTTPMiddleware):
    """
    Middleware that detects and respects common proxy headers for HTTPS, enabling
    terminaide to work correctly behind load balancers and proxies.
    """

    async def dispatch(self, request, call_next):
        # Check X-Forwarded-Proto (most common)
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto == "https":
            original_scheme = request.scope.get("scheme", "unknown")
            request.scope["scheme"] = "https"

            # Log this detection once per deployment to help with debugging
            logger.debug(
                f"HTTPS detected via X-Forwarded-Proto header "
                f"(original scheme: {original_scheme})"
            )

        # Check Forwarded header (RFC 7239)
        forwarded = request.headers.get("forwarded")
        if forwarded and "proto=https" in forwarded.lower():
            request.scope["scheme"] = "https"

        # AWS Elastic Load Balancer sometimes uses this
        elb_proto = request.headers.get("x-forwarded-protocol")
        if elb_proto == "https":
            request.scope["scheme"] = "https"

        return await call_next(request)


class ServeWithConfig:
    """Class responsible for handling the serving implementation for different modes."""

    @staticmethod
    def add_proxy_middleware_if_needed(app: FastAPI, config: TerminaideConfig) -> None:
        """
        Adds proxy header middleware if trust_proxy_headers=True in config.
        This ensures that X-Forwarded-Proto from proxies like ngrok is respected,
        preventing mixed-content errors behind HTTPS tunnels or load balancers.
        """

        if config.trust_proxy_headers:
            try:
                if not any(
                    m.cls.__name__ == "_ProxyHeaderMiddleware"
                    for m in getattr(app, "user_middleware", [])
                ):
                    app.add_middleware(_ProxyHeaderMiddleware)
                    logger.info("Added proxy header middleware for HTTPS detection")

            except Exception as e:
                logger.warning(f"Failed to add middleware: {e}")

    @classmethod
    def display_banner(cls, mode, banner_value):
        """Display a banner based on the banner parameter value.
        
        Args:
            mode: The serving mode (function, script, apps)
            banner_value: True for Rich panel, False for no banner, or a string to print directly
        """
        if os.environ.get("TERMINAIDE_BANNER_SHOWN") == "1":
            return
        os.environ["TERMINAIDE_BANNER_SHOWN"] = "1"
        
        # Handle string banner - print it directly
        if isinstance(banner_value, str):
            print(banner_value)
            logger.debug(f"Starting Terminaide in {mode.upper()} mode")
            return
        
        # Handle boolean False - no banner
        if banner_value is False:
            logger.debug(f"Starting Terminaide in {mode.upper()} mode (banner disabled)")
            return

        # Handle boolean True - show Rich panel
        try:
            from rich.console import Console
            from rich.panel import Panel

            mode_colors = {
                "function": "dark_orange",
                "script": "blue",
                "apps": "magenta",
            }
            color = mode_colors.get(mode, "yellow")
            mode_upper = mode.upper()

            console = Console(highlight=False)
            panel = Panel(
                f"TERMINAIDE {mode_upper} SERVER",
                border_style=color,
                expand=False,
                padding=(0, 1),
            )
            console.print(panel)
        except ImportError:
            mode_upper = mode.upper()
            banner = f"== TERMINAIDE SERVING IN {mode_upper} MODE =="
            print(f"\033[1m\033[92m{banner}\033[0m")

        logger.debug(f"Starting Terminaide in {mode.upper()} mode")

    @classmethod
    def _wait_for_server(cls, url: str, timeout: int = 15) -> bool:
        """Wait for the server to be ready by checking health endpoint."""
        try:
            import requests
        except ImportError:
            logger.error(
                "requests library required for desktop mode. Install with: pip install requests"
            )
            return False

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Try health endpoint first
                try:
                    response = requests.get(f"{url}/health", timeout=2)
                    if response.status_code == 200:
                        logger.debug(f"Server ready at {url}")
                        return True
                except requests.exceptions.RequestException:
                    pass

                # Fallback: try root endpoint
                try:
                    response = requests.get(url, timeout=2)
                    if response.status_code == 200:
                        logger.debug(f"Server ready at {url} (via root endpoint)")
                        return True
                except requests.exceptions.RequestException:
                    pass

            except Exception:
                pass
            time.sleep(0.5)

        logger.error(f"Server at {url} did not become ready within {timeout} seconds")
        return False

    @classmethod
    def serve_desktop(cls, config: TerminaideConfig) -> None:
        """Serve the application in a desktop window using pywebview."""
        logger.info(f"Starting desktop application: {config.title}")

        # Build the appropriate server command based on mode
        if config._mode == "apps":
            logger.error("Desktop mode for serve_apps is not yet implemented")
            print(
                "\033[91mError: Desktop mode for serve_apps is not yet implemented.\033[0m"
            )
            print(
                "Desktop mode currently supports serve_function and serve_script only."
            )
            return
        
        try:
            # Import generate_desktop_server_command here to avoid circular dependency
            from .app_factory import generate_desktop_server_command
            server_command = generate_desktop_server_command(config)
        except ValueError as e:
            logger.error(str(e))
            return
        
        # Create subprocess command to start the terminaide server
        server_args = [
            sys.executable,
            "-c",
            server_command,
        ]

        # Start the server subprocess
        logger.debug(f"Starting server subprocess for desktop mode")
        server_process = subprocess.Popen(
            server_args, cwd=Path.cwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        try:
            # Wait for server to be ready
            server_url = f"http://localhost:{config.port}"

            # Check if subprocess is still running before health check
            if server_process.poll() is not None:
                stdout, stderr = server_process.communicate()
                logger.error(
                    f"Server subprocess exited early with code: {server_process.returncode}"
                )
                if stderr:
                    logger.error(f"Server error: {stderr.decode()}")
                print("\033[91mError: Server failed to start\033[0m")
                return

            if not cls._wait_for_server(server_url, timeout=15):
                server_process.terminate()
                stdout, stderr = server_process.communicate(timeout=5)
                logger.error("Server failed to start")
                if stderr:
                    logger.error(f"Server stderr: {stderr.decode()}")
                print("\033[91mError: Server failed to start within timeout\033[0m")
                return

            logger.info(f"Server ready at {server_url}")

            # Create and show the desktop window
            logger.info(f"Opening desktop window: {config.title}")
            webview.create_window(
                title=config.title,
                url=server_url,
                width=config.desktop_width,
                height=config.desktop_height,
            )

            # This blocks until the window is closed
            webview.start()

            logger.info("Desktop window closed")

        except Exception as e:
            logger.error(f"Desktop application error: {e}")
            print(f"\033[91mDesktop application error: {e}\033[0m")
        finally:
            # Clean up: kill the server process when window closes
            logger.debug("Terminating server subprocess")
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Server process did not terminate gracefully, killing")
                server_process.kill()
                server_process.wait()

            logger.info("Desktop application cleanup complete")

    @classmethod
    def serve(cls, config) -> None:
        """Serves the application based on the configuration mode."""
        # Configure logging based on config
        from .log_config import setup_package_logging
        setup_package_logging(configure=config.configure_logging)
        
        # Display banner based on config.banner value
        if config.banner:
            cls.display_banner(config._mode, config.banner)

        # Check if desktop mode is requested
        if config.desktop:
            cls.serve_desktop(config)
            return

        if config._mode == "function":
            cls.serve_function(config)
        elif config._mode == "script":
            cls.serve_script(config)
        elif config._mode == "apps":
            cls.serve_apps(config)
        else:
            raise ValueError(f"Unknown serving mode: {config._mode}")

    @classmethod
    def serve_function(cls, config) -> None:
        """Implementation for serving a function."""
        if config.reload:
            # Reload mode - set environment variables and delegate to uvicorn
            func = config._target
            # Import from app_factory to avoid circular dependency
            from .app_factory import set_reload_env_vars
            extra_vars = {
                "TERMINAIDE_FUNC_NAME": func.__name__,
                "TERMINAIDE_FUNC_MOD": func.__module__ if func.__module__ else "",
            }
            set_reload_env_vars(config, "function", extra_vars)

            uvicorn.run(
                "terminaide.termin_api:function_app_factory",
                factory=True,
                host="0.0.0.0",
                port=config.port,
                reload=True,
                log_level="info" if config.debug else "warning",
            )
        else:
            # Direct mode - use local generate_function_wrapper
            func = config._target
            ephemeral_path = generate_function_wrapper(func)

            # Import from app_factory to avoid circular dependency
            from .app_factory import copy_config_attributes
            script_config = copy_config_attributes(config)
            script_config._target = ephemeral_path
            script_config._mode = "function"
            script_config._original_function_name = func.__name__

            logger.debug(
                f"Using title: {script_config.title} for function {func.__name__}"
            )

            cls.serve_script(script_config)

    @classmethod
    def serve_script(cls, config) -> None:
        """Implementation for serving a script."""
        script_path = config._target
        if not isinstance(script_path, Path):
            script_path = Path(script_path)

        script_path = smart_resolve_path(script_path)
        if not script_path.exists():
            print(f"\033[91mError: Script not found: {script_path}\033[0m")
            return

        if config.reload:
            # Import from app_factory to avoid circular dependency
            from .app_factory import set_reload_env_vars
            extra_vars = {"TERMINAIDE_SCRIPT_PATH": str(script_path)}
            set_reload_env_vars(config, config._mode, extra_vars)

            uvicorn.run(
                "terminaide.termin_api:script_app_factory",
                factory=True,
                host="0.0.0.0",
                port=config.port,
                reload=True,
                log_level="info" if config.debug else "warning",
            )
        else:
            # Direct mode
            ttyd_config = convert_terminaide_config_to_ttyd_config(config, script_path)
            # Import from app_factory to avoid circular dependency
            from .app_factory import create_app_with_lifespan
            app = create_app_with_lifespan(config.title, config, ttyd_config)

            def handle_exit(sig, frame):
                print("\033[93mShutting down...\033[0m")
                sys.exit(0)

            signal.signal(signal.SIGINT, handle_exit)
            signal.signal(signal.SIGTERM, handle_exit)

            uvicorn.run(
                app,
                host="0.0.0.0",
                port=config.port,
                log_level="info" if config.debug else "warning",
            )

    @classmethod
    def serve_apps(cls, config) -> None:
        """Implementation for serving multiple apps."""
        # Display banner if enabled, for consistency with other serve methods
        if config.banner:
            cls.display_banner(config._mode, config.banner)

        app = config._app
        terminal_routes = config._target

        # Process function-based routes to generate ephemeral script wrappers
        ttyd_config = convert_terminaide_config_to_ttyd_config(config)

        # Generate wrapper scripts for all function-based routes
        for script_config in ttyd_config.script_configs:
            if script_config.is_function_based:
                func = script_config.function_object
                if func is not None:
                    logger.debug(
                        f"Generating wrapper script for function '{func.__name__}' at route {script_config.route_path}"
                    )
                    wrapper_path = generate_function_wrapper(func)
                    script_config.set_function_wrapper_path(wrapper_path)
                    logger.debug(
                        f"Function '{func.__name__}' will use wrapper script at {wrapper_path}"
                    )

        # Add middleware silently, we'll log during startup
        if config.trust_proxy_headers:
            try:
                if not any(
                    m.cls.__name__ == "_ProxyHeaderMiddleware"
                    for m in getattr(app, "user_middleware", [])
                ):
                    app.add_middleware(_ProxyHeaderMiddleware)
                    # Store the flag for logging during lifespan startup
                    app.state.terminaide_middleware_added = True

            except Exception as e:
                logger.warning(f"Failed to add proxy header middleware: {e}")

        # Rest of the method remains the same...
        sentinel_attr = "_terminaide_lifespan_attached"
        if getattr(app.state, sentinel_attr, False):
            return

        setattr(app.state, sentinel_attr, True)

        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def terminaide_merged_lifespan(_app: FastAPI):
            # Log middleware addition at startup (after banner has been shown)
            if getattr(_app.state, "terminaide_middleware_added", False):
                logger.info("Added proxy header middleware for HTTPS detection")
                # Clear the flag so we don't log again
                delattr(_app.state, "terminaide_middleware_added")

            if original_lifespan is not None:
                async with original_lifespan(_app):
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield
            else:
                async with terminaide_lifespan(_app, ttyd_config):
                    yield

        app.router.lifespan_context = terminaide_merged_lifespan