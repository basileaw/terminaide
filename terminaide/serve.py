# terminaide/serve.py

"""
Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application. It now supports multiple script configurations,
allowing different scripts to be served on different routes.

All side effects (like spawning ttyd processes) happen only when the server truly starts.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union, Tuple, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core.manager import TTYDManager
from .core.proxy import ProxyManager
from .core.settings import TTYDConfig, ScriptConfig, ThemeConfig, TTYDOptions
from .exceptions import TemplateError, ConfigurationError

logger = logging.getLogger("terminaide")


def _setup_templates(config: TTYDConfig) -> Tuple[Jinja2Templates, str]:
    """
    Configure template handling for the terminal interface.
    Returns (templates, template_file).
    """
    if config.template_override:
        template_dir = config.template_override.parent
        template_file = config.template_override.name
    else:
        # Default location: "templates" folder next to this file
        template_dir = Path(__file__).parent / "templates"
        template_file = "terminal.html"

    if not template_dir.exists():
        raise TemplateError(str(template_dir), "Template directory not found")

    templates = Jinja2Templates(directory=str(template_dir))

    # Check if the file exists
    if not (template_dir / template_file).exists():
        raise TemplateError(template_file, "Template file not found")

    return templates, template_file


def _configure_routes(
    app: FastAPI,
    config: TTYDConfig,
    ttyd_manager: TTYDManager,
    proxy_manager: ProxyManager,
    templates: Jinja2Templates,
    template_file: str
) -> None:
    """
    Define all routes for the TTYD service: health, interface, websocket, proxy.
    Now supports multiple script configurations.
    """

    @app.get(f"{config.mount_path}/health")
    async def health_check():
        """Health check endpoint providing status of all ttyd processes."""
        return {
            "ttyd": ttyd_manager.check_health(),
            "proxy": proxy_manager.get_routes_info()
        }
    
    # Configure routes for each script configuration
    for script_config in config.script_configs:
        route_path = script_config.route_path
        terminal_path = config.get_terminal_path_for_route(route_path)
        title = script_config.title or config.title
        
        # HTML interface route
        @app.get(route_path, response_class=HTMLResponse)
        async def terminal_interface(
            request: Request, 
            route_path=route_path,  # Capture for closure
            terminal_path=terminal_path,  # Capture for closure 
            title=title  # Capture for closure
        ):
            """Serve the HTML terminal interface for a specific route."""
            try:
                return templates.TemplateResponse(
                    template_file,
                    {
                        "request": request,
                        "mount_path": terminal_path,
                        "theme": config.theme.model_dump(),
                        "title": title
                    }
                )
            except Exception as e:
                logger.error(f"Template rendering error for route {route_path}: {e}")
                raise TemplateError(template_file, str(e))
        
        # Terminal WebSocket route
        @app.websocket(f"{terminal_path}/ws")
        async def terminal_ws(
            websocket: WebSocket,
            route_path=route_path  # Capture for closure
        ):
            """Handle WebSocket connections for a specific terminal route."""
            await proxy_manager.proxy_websocket(websocket, route_path=route_path)
        
        # Terminal HTTP proxy route
        @app.api_route(
            f"{terminal_path}/{{path:path}}",
            methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"]
        )
        async def proxy_terminal_request(
            request: Request, 
            path: str,
            route_path=route_path  # Capture for closure
        ):
            """Proxy ttyd-specific HTTP requests for a specific terminal route."""
            return await proxy_manager.proxy_http(request)


def _configure_app(app: FastAPI, config: TTYDConfig):
    """
    Perform all TTYD setup: managers, routes, static files, etc.
    Now supports multiple script configurations.
    """
    mode = "multi-script" if config.is_multi_script else "single-script"
    logger.info(f"Configuring ttyd service with {config.mount_path} mounting ({mode} mode)")

    ttyd_manager = TTYDManager(config)
    proxy_manager = ProxyManager(config)

    # Mount static assets
    package_dir = Path(__file__).parent
    static_dir = package_dir / "static"
    static_dir.mkdir(exist_ok=True)

    app.mount(
        config.static_path,
        StaticFiles(directory=str(static_dir)),
        name="static"
    )

    templates, template_file = _setup_templates(config)
    _configure_routes(app, config, ttyd_manager, proxy_manager, templates, template_file)

    # We'll return these managers so we can manage their lifecycle in a lifespan
    return ttyd_manager, proxy_manager


@asynccontextmanager
async def _terminaide_lifespan(app: FastAPI, config: TTYDConfig):
    """
    Custom lifespan context that:
      - Configures TTYD at startup
      - Starts the TTYD processes
      - Cleans up TTYD on shutdown
    """

    # Actually do all route/static config (which logs "Configuring ttyd service..." etc.)
    ttyd_manager, proxy_manager = _configure_app(app, config)

    mode = "multi-script" if config.is_multi_script else "single-script"
    logger.info(
        f"Starting ttyd service (mounting: "
        f"{'root' if config.is_root_mounted else 'non-root'}, "
        f"mode: {mode})"
    )
    ttyd_manager.start()

    try:
        yield  # Wait here while the app runs
    finally:
        logger.info("Cleaning up ttyd service...")
        ttyd_manager.stop()
        await proxy_manager.cleanup()


def _create_script_configs(
    client_script: Optional[Union[str, Path]],
    script_routes: Optional[Dict[str, Union[str, Path]]] = None
) -> List[ScriptConfig]:
    """
    Create script configurations from client_script and script_routes.
    
    Args:
        client_script: Default script for the root path (can be None if script_routes provided)
        script_routes: Dictionary mapping routes to script paths
        
    Returns:
        List of ScriptConfig objects
        
    Raises:
        ConfigurationError: If no valid script configuration is provided
    """
    script_configs = []
    
    # Add default client script for root path
    if client_script is not None:
        script_configs.append(
            ScriptConfig(
                route_path="/",
                client_script=client_script
            )
        )
    
    # Add script routes
    if script_routes:
        for route_path, script_path in script_routes.items():
            script_configs.append(
                ScriptConfig(
                    route_path=route_path,
                    client_script=script_path
                )
            )
    
    # Ensure we have at least one script config
    if not script_configs:
        raise ConfigurationError("No valid script configuration provided")
        
    return script_configs


def serve_tty(
    app: FastAPI,
    client_script: Optional[Union[str, Path]] = None,
    *,
    script_routes: Optional[Dict[str, Union[str, Path]]] = None,
    mount_path: str = "/",
    port: int = 7681,
    theme: Optional[Dict[str, Any]] = None,
    ttyd_options: Optional[Dict[str, Any]] = None,
    template_override: Optional[Union[str, Path]] = None,
    title: str = "Terminal",
    debug: bool = False
) -> None:
    """
    Attach a custom lifespan to the app for serving terminal interfaces.
    
    This function configures terminaide to serve one or more terminal interfaces
    through ttyd. It supports both single-script and multi-script configurations.
    
    Args:
        app: FastAPI application to attach the lifespan to
        client_script: Path to the script to run in the terminal (for single script)
        script_routes: Dictionary mapping routes to script paths (for multi-script)
        mount_path: Base path where terminal will be mounted
        port: Base port for ttyd processes
        theme: Terminal theme configuration
        ttyd_options: Options for ttyd processes
        template_override: Custom template path
        title: Default title for terminal interface
        debug: Enable debug mode
        
    Example:
        Single script:
            serve_tty(app, client_script="script.py")
            
        Multiple scripts:
            serve_tty(
                app,
                script_routes={
                    "/": "default.py",
                    "/snake": "snake.py",
                    "/chat": "chat.py"
                }
            )
    """
    used_demo = False

    # If neither client_script nor script_routes provided, use demo
    if client_script is None and not script_routes:
        # Use built-in demo if not provided
        demo_path = Path(__file__).parent / "demos" / "instructions.py"
        client_script = demo_path
        used_demo = True
        # If the title is default, change it
        if title == "Terminal":
            title = "Terminaide Demo"
    
    # Create script configurations
    script_configs = _create_script_configs(client_script, script_routes)
    
    # Create TTYDConfig
    config = TTYDConfig(
        client_script=script_configs[0].client_script,  # Use first script as default
        mount_path=mount_path,
        port=port,
        theme=ThemeConfig(**(theme or {"background": "black"})),
        ttyd_options=TTYDOptions(**(ttyd_options or {})),
        template_override=template_override,
        title=title,
        debug=debug,
        script_configs=script_configs
    )

    # Sentinel to ensure we don't attach the lifespan multiple times
    sentinel_attr = "_terminaide_lifespan_attached"
    if getattr(app.state, sentinel_attr, False):
        return
    setattr(app.state, sentinel_attr, True)

    # We keep the original lifespan to merge it
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def terminaide_merged_lifespan(_app: FastAPI):
        # If user didn't provide a script, log once we are truly at startup
        if used_demo:
            logger.info("No client script provided, using built-in demo at startup")

        # Merge user's lifespan with terminaide's
        if original_lifespan is not None:
            async with original_lifespan(_app):
                async with _terminaide_lifespan(_app, config):
                    yield
        else:
            async with _terminaide_lifespan(_app, config):
                yield

    # Attach our merged lifespan
    app.router.lifespan_context = terminaide_merged_lifespan