# terminaide/serve.py

"""
Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application. It now supports multiple script configurations,
allowing different scripts to be served on different routes.

The implementation uses a middleware-based approach to ensure that user-defined routes
take precedence over the demo, even when those routes are defined after calling serve_terminal().

All side effects (like spawning ttyd processes) happen only when the server truly starts.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union, Tuple, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
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
        
        # Register HTML interface route for ALL paths, including root when explicitly configured
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


def _create_script_configs(
    client_script: Optional[Union[str, Path, List]],
    terminal_routes: Optional[Dict[str, Union[str, Path, List, Dict[str, Any]]]] = None
) -> List[ScriptConfig]:
    """
    Create script configurations from client_script and terminal_routes.
    
    Args:
        client_script: Default script for the root path. Can be:
            - A string or Path object pointing to the script
            - A list where the first element is the script path and remaining elements are arguments
        terminal_routes: Dictionary mapping routes to script configurations. Values can be:
            - A string or Path object pointing to the script
            - A list where the first element is the script path and remaining elements are arguments
            - A dict with keys like "client_script" (required), "title", "args" (optional)
        
    Returns:
        List of ScriptConfig objects
        
    Raises:
        ConfigurationError: If no valid script configuration is provided
    """
    script_configs = []
    
    # Check if root path is explicitly defined in terminal_routes
    has_root_path = terminal_routes and "/" in terminal_routes
    
    # Add default client script for root path if provided and root not already defined
    if client_script is not None and not has_root_path:
        # Handle case where client_script is a list [script_path, arg1, arg2, ...]
        if isinstance(client_script, list) and len(client_script) > 0:
            script_path = client_script[0]
            args = client_script[1:] if len(client_script) > 1 else []
        else:
            # Traditional case - just a script path
            script_path = client_script
            args = []
            
        script_configs.append(
            ScriptConfig(
                route_path="/",
                client_script=script_path,
                args=args
            )
        )
    
    # Add terminal routes
    if terminal_routes:
        for route_path, script_spec in terminal_routes.items():
            # Handle different script_spec formats
            
            # Case 1: script_spec is a dictionary with configuration options
            if isinstance(script_spec, dict) and "client_script" in script_spec:
                # Get the script path and args
                script_value = script_spec["client_script"]
                
                if isinstance(script_value, list) and len(script_value) > 0:
                    script_path = script_value[0]
                    args = script_value[1:] if len(script_value) > 1 else []
                else:
                    script_path = script_value
                    args = []
                
                # Use explicit args if provided
                if "args" in script_spec:
                    args = script_spec["args"]
                
                # Create config with all available fields
                config_kwargs = {
                    "route_path": route_path,
                    "client_script": script_path,
                    "args": args
                }
                
                # Add optional title if provided
                if "title" in script_spec:
                    config_kwargs["title"] = script_spec["title"]
                
                # Add optional port if provided
                if "port" in script_spec:
                    config_kwargs["port"] = script_spec["port"]
                
                script_configs.append(ScriptConfig(**config_kwargs))
            
            # Case 2: script_spec is a list [script_path, arg1, arg2, ...]
            elif isinstance(script_spec, list) and len(script_spec) > 0:
                script_path = script_spec[0]
                args = script_spec[1:] if len(script_spec) > 1 else []
                
                script_configs.append(
                    ScriptConfig(
                        route_path=route_path,
                        client_script=script_path,
                        args=args
                    )
                )
                
            # Case 3: script_spec is a string or Path object
            else:
                script_path = script_spec
                args = []
                
                script_configs.append(
                    ScriptConfig(
                        route_path=route_path,
                        client_script=script_path,
                        args=args
                    )
                )
    
    # Always add the demo to root path if no explicit root is defined
    # This ensures it's properly configured and started with other processes
    if not has_root_path and client_script is None:
        demo_path = Path(__file__).parent / "demos" / "instructions.py"
        script_configs.append(
            ScriptConfig(
                route_path="/",
                client_script=demo_path,
                title="Terminaide (Instructions)"
            )
        )
    
    # Ensure we have at least one script config
    if not script_configs:
        raise ConfigurationError("No valid script configuration provided")
        
    return script_configs


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
    
    # Store references in app.state for middleware access
    app.state.terminaide_templates = templates
    app.state.terminaide_template_file = template_file
    app.state.terminaide_config = config
    
    # Configure routes for all explicit script configurations
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


async def _demo_middleware(request: Request, call_next):
    """
    Middleware that serves the demo at the root path if no other route handles it.
    
    This middleware lets users define their own root routes after calling serve_terminal(),
    while still providing the helpful demo when no user route is defined.
    """
    # First, let the request go through the normal routing process
    response = await call_next(request)
    
    # If the path is root and no route was found (404), serve the demo
    if request.url.path == "/" and response.status_code == 404:
        # Access stored templates and config from app.state
        templates = request.app.state.terminaide_templates
        template_file = request.app.state.terminaide_template_file
        config = request.app.state.terminaide_config
        
        # Get the terminal path for the root route
        terminal_path = config.get_terminal_path_for_route("/")
        
        # Log that we're serving the demo via middleware
        logger.info("No route matched root path, serving demo via middleware")
        
        # Serve the demo interface template
        try:
            return templates.TemplateResponse(
                template_file,
                {
                    "request": request,
                    "mount_path": terminal_path,
                    "theme": config.theme.model_dump(),
                    "title": "Terminaide (Instructions)"
                }
            )
        except Exception as e:
            logger.error(f"Demo template rendering error: {e}")
            # Let the original 404 pass through if template rendering fails
    
    # Return the original response for all other cases
    return response


def serve_terminal(
    app: FastAPI,
    client_script: Optional[Union[str, Path]] = None,
    *,
    terminal_routes: Optional[Dict[str, Union[str, Path, List, Dict[str, Any]]]] = None,
    mount_path: str = "/",
    port: int = 7681,
    theme: Optional[Dict[str, Any]] = None,
    ttyd_options: Optional[Dict[str, Any]] = None,
    template_override: Optional[Union[str, Path]] = None,
    title: str = "Terminal",
    debug: bool = False,
    trust_proxy_headers: bool = True  # New parameter with default True
) -> None:
    """
    Attach a custom lifespan to the app for serving terminal interfaces.
    
    This function configures terminaide to serve one or more terminal interfaces
    through ttyd. It supports both single-script and multi-script configurations.
    
    Args:
        app: FastAPI application to attach the lifespan to
        client_script: Path to the script to run in the terminal (for single script)
        terminal_routes: Dictionary mapping routes to script configurations. Values can be:
            - A string or Path object pointing to the script
            - A list where the first element is the script path and remaining elements are arguments
            - A dict with keys like "client_script" (required), "title", "args" (optional)
        mount_path: Base path where terminal will be mounted
        port: Base port for ttyd processes
        theme: Terminal theme configuration
        ttyd_options: Options for ttyd processes
        template_override: Custom template path
        title: Default title for terminal interface
        debug: Enable debug mode
        trust_proxy_headers: Whether to trust X-Forwarded-Proto and similar headers
                            for HTTPS detection (default: True)
    """
    # Add ProxyHeaderMiddleware for HTTPS detection if enabled
    if trust_proxy_headers:
        try:
            from .middleware import ProxyHeaderMiddleware
            # Check if middleware is already added to avoid duplicates
            if not any(m.cls.__name__ == "ProxyHeaderMiddleware" for m in getattr(app, "user_middleware", [])):
                app.add_middleware(ProxyHeaderMiddleware)
                logger.info("Added proxy header middleware for HTTPS detection")
        except Exception as e:
            logger.warning(f"Failed to add proxy header middleware: {e}")
    
    # Create script configurations
    script_configs = _create_script_configs(client_script, terminal_routes)
    
    # Create TTYDConfig
    config = TTYDConfig(
        client_script=script_configs[0].client_script if script_configs else Path(__file__).parent / "demos" / "instructions.py",
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

    # Add our demo fallback middleware
    app.middleware("http")(_demo_middleware)

    # We keep the original lifespan to merge it
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def terminaide_merged_lifespan(_app: FastAPI):
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