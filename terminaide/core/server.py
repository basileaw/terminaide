# server.py

"""
Application runner implementation for Terminaide.

This module contains the ServeWithConfig class that handles running applications
in different Terminaide modes (function, script, apps).
"""

import os
import sys
import signal
import logging
import uvicorn
from pathlib import Path
from fastapi import FastAPI
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware

from .config import (
    TerminaideConfig,
    convert_terminaide_config_to_ttyd_config,
    terminaide_lifespan,
    smart_resolve_path,
)
from .wrappers import (
    generate_function_wrapper,
    get_or_ensure_function_wrapper,
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
            logger.debug(
                f"Starting Terminaide in {mode.upper()} mode (banner disabled)"
            )
            return

        # Handle boolean True - show Rich panel
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.align import Align

            mode_colors = {
                "function": "dark_orange",
                "script": "blue",
                "apps": "magenta",
            }
            color = mode_colors.get(mode, "yellow")
            mode_upper = mode.upper()
            console = Console(highlight=False)

            # Center the content within the panel
            centered_content = Align.center(f"TERMINAIDE {mode_upper} SERVER")
            panel = Panel(
                centered_content,
                border_style=color,
                expand=True,
                padding=(0, 1),
            )
            console.print(panel)
        except ImportError:
            mode_upper = mode.upper()
            banner = f"== TERMINAIDE SERVING IN {mode_upper} MODE =="
            print(f"\033[1m\033[92m{banner}\033[0m")

        logger.debug(f"Starting Terminaide in {mode.upper()} mode")

    @classmethod
    def serve(cls, config) -> None:
        """Serves the application based on the configuration mode."""
        # Configure logging based on config
        from .logger import setup_package_logging

        setup_package_logging(log_level=config.log_level)
        
        logger.debug(f"Logging configured with log_level={config.log_level}, level={logger.level}")

        # Display banner based on config.banner value
        if config.banner:
            cls.display_banner(config._mode, config.banner)

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
        # Direct mode - use lazy validation for reliable wrapper access
        func = config._target
        ephemeral_path = get_or_ensure_function_wrapper(func, args=config.args, config=config)

        # Import from factory to avoid circular dependency
        from .factory import copy_config_attributes

        script_config = copy_config_attributes(config)
        script_config._target = ephemeral_path
        script_config._mode = "function"
        script_config._original_function_name = func.__name__

        logger.debug(f"Using title: {script_config.title} for function {func.__name__}")

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

        # Direct mode
        ttyd_config = convert_terminaide_config_to_ttyd_config(config, script_path)
        # Import from factory to avoid circular dependency
        from .factory import create_app_with_lifespan

        app = create_app_with_lifespan(config.title, config, ttyd_config)

        def handle_exit(sig, _):
            print("\033[93mShutting down...\033[0m")
            
            # Clean up ephemeral files on graceful shutdown
            try:
                from .wrappers import cleanup_own_ephemeral_files
                cleanup_own_ephemeral_files()
            except ImportError:
                pass  # Graceful fallback if import fails
            
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=config.port,
            log_level=config.log_level or "info",
        )

    @classmethod
    def serve_apps(cls, config) -> None:
        """Implementation for serving multiple apps."""
        # Display banner if enabled, for consistency with other serve methods
        if config.banner:
            cls.display_banner(config._mode, config.banner)

        logger.debug(f"serve_apps called with log_level={config.log_level}")
        
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
                    wrapper_path = get_or_ensure_function_wrapper(func, args=script_config.args, config=config)
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
