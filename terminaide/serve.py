# terminaide/serve.py

"""
Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application. It supports multiple script configurations,
allowing different scripts to be served on different routes.

The implementation uses a middleware-based approach to ensure that user-defined routes
take precedence over the default client, even when those routes are defined after calling 
serve_terminals().

All side effects (like spawning ttyd processes) happen only when the server truly starts.
"""

import logging
import sys
import platform
import signal
from pathlib import Path
from typing import Optional, Dict, Any, Union, Tuple, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core.manager import TTYDManager
from .core.proxy import ProxyManager
from .core.settings import TTYDConfig, ScriptConfig, ThemeConfig, TTYDOptions, smart_resolve_path
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
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any]]]
) -> List[ScriptConfig]:
    """
    Create script configurations from terminal_routes.
    
    Args:
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
    
    # Add terminal routes
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
    
    # If no explicit root is defined, use the default client
    if not has_root_path:
        default_client_path = Path(__file__).parent / "default_client.py"
        script_configs.append(
            ScriptConfig(
                route_path="/",
                client_script=default_client_path,
                title="Terminaide (Getting Started)"
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


async def _default_client_middleware(request: Request, call_next):
    """
    Middleware that serves the default client at the root path if no other route handles it.
    
    This middleware lets users define their own root routes after calling serve_terminals(),
    while still providing the default interface when no user route is defined.
    """
    # First, let the request go through the normal routing process
    response = await call_next(request)
    
    # If the path is root and no route was found (404), serve the default client
    if request.url.path == "/" and response.status_code == 404:
        # Access stored templates and config from app.state
        templates = request.app.state.terminaide_templates
        template_file = request.app.state.terminaide_template_file
        config = request.app.state.terminaide_config
        
        # Get the terminal path for the root route
        terminal_path = config.get_terminal_path_for_route("/")
        
        # Log that we're serving the default client via middleware
        logger.info("No route matched root path, serving default client via middleware")
        
        # Serve the default client interface template
        try:
            return templates.TemplateResponse(
                template_file,
                {
                    "request": request,
                    "mount_path": terminal_path,
                    "theme": config.theme.model_dump(),
                    "title": "Terminaide (Getting Started)"
                }
            )
        except Exception as e:
            logger.error(f"Default client template rendering error: {e}")
            # Let the original 404 pass through if template rendering fails
    
    # Return the original response for all other cases
    return response


def serve_terminals(
    app: FastAPI,
    *,
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any]]],
    mount_path: str = "/",
    port: int = 7681,
    theme: Optional[Dict[str, Any]] = None,
    ttyd_options: Optional[Dict[str, Any]] = None,
    template_override: Optional[Union[str, Path]] = None,
    title: str = "Terminal",
    debug: bool = False,
    trust_proxy_headers: bool = True
) -> None:
    """
    Attach a custom lifespan to the app for serving terminal interfaces.
    
    This function configures terminaide to serve one or more terminal interfaces
    through ttyd. It supports multi-script configurations.
    
    Args:
        app: FastAPI application to attach the lifespan to
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
    script_configs = _create_script_configs(terminal_routes)
    
    # Create TTYDConfig
    config = TTYDConfig(
        client_script=script_configs[0].client_script if script_configs else Path(__file__).parent / "default_client.py",
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

    # Add our default client fallback middleware
    app.middleware("http")(_default_client_middleware)

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


def simple_serve(
    script_path: Union[str, Path],
    port: int = 8000,
    title: str = "Terminal",
    theme: Optional[Dict[str, Any]] = None,
    debug: bool = False
) -> None:
    """
    A simplified function to serve a Python script in a browser terminal.
    
    This function creates a FastAPI app, configures a terminal at the root path,
    and starts the uvicorn server automatically. It's designed for beginners who
    just want to quickly serve a script without worrying about FastAPI or server setup.
    
    Args:
        script_path: Path to the script to run
        port: Port for the web server
        title: Title for the terminal window
        theme: Theme configuration
        debug: Enable debug mode
    """
    try:
        # Try to resolve the script path
        script_absolute_path = smart_resolve_path(script_path)
        
        if not script_absolute_path.exists():
            print(f"\033[91mError: Script not found: {script_path}\033[0m")
            print(f"Tried absolute path: {script_absolute_path}")
            print("Make sure the script exists and the path is correct.")
            return
        
        # Create a FastAPI app
        app = FastAPI(title=f"Terminaide - {title}")
        
        # Configure the terminal
        serve_terminals(
            app,
            terminal_routes={"/": script_absolute_path},
            port=7681,  # This is for ttyd, not the web server
            title=title,
            theme=theme,
            debug=debug
        )
        
        # Print a friendly message
        print("\033[92m" + "="*60 + "\033[0m")
        print(f"\033[92m Terminaide: Serving \033[1m{script_absolute_path.name}\033[0m\033[92m in a browser terminal\033[0m")
        print("\033[92m" + "="*60 + "\033[0m")
        print(f"\033[96m> URL: \033[1mhttp://localhost:{port}\033[0m")
        print("\033[96m> Press Ctrl+C to exit\033[0m")
        
        # Start the uvicorn server
        import uvicorn
        
        # Set up signal handling for graceful shutdown
        def handle_exit(sig, frame):
            print("\n\033[93mShutting down...\033[0m")
            sys.exit(0)
            
        signal.signal(signal.SIGINT, handle_exit)
        
        # Start uvicorn
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info" if debug else "warning")
        
    except Exception as e:
        print(f"\033[91mError starting terminal: {e}\033[0m")
        if debug:
            import traceback
            traceback.print_exc()