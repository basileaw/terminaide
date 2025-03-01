# terminaide/serve.py

"""
Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application. It handles both root ("/") and non-root
("/path") mounting configurations while maintaining a clean, simple API for users.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core.manager import TTYDManager
from .core.proxy import ProxyManager
from .core.settings import TTYDConfig
from .exceptions import TemplateError

logger = logging.getLogger("terminaide")

def _setup_templates(app: FastAPI, config: TTYDConfig) -> Tuple[Jinja2Templates, str]:
    """
    Configure template handling for the terminal interface.
    
    This function sets up the template system, handling both default and custom
    templates while ensuring proper path resolution.

    Args:
        app: FastAPI application instance
        config: Current configuration

    Returns:
        Tuple of (Templates instance, template filename)

    Raises:
        TemplateError: If template directory or file is not found
    """
    if config.template_override:
        template_dir = config.template_override.parent
        template_file = config.template_override.name
    else:
        template_dir = Path(__file__).parent / "templates"
        template_file = "terminal.html"

    if not template_dir.exists():
        raise TemplateError(str(template_dir), "Template directory not found")

    templates = Jinja2Templates(directory=str(template_dir))
    
    # Verify template exists
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
    Set up all routes for the ttyd service.
    
    This function configures all necessary routes for the terminal service,
    adapting the routing based on whether we're using root or non-root mounting.

    Args:
        app: FastAPI application instance
        config: Current configuration
        ttyd_manager: TTYd process manager
        proxy_manager: Proxy manager for ttyd connections
        templates: Template engine instance
        template_file: Name of the template file to use
    """
    @app.get(f"{config.mount_path}/health")
    async def health_check():
        """Health check endpoint providing service status."""
        return {
            "ttyd": ttyd_manager.check_health(),
            "proxy": proxy_manager.get_routes_info()
        }

    @app.get(config.mount_path, response_class=HTMLResponse)
    async def terminal_interface(request: Request):
        """
        Serve the terminal interface.
        
        This endpoint serves the main HTML interface, properly configured
        for the current mounting path.
        """
        try:
            return templates.TemplateResponse(
                template_file,
                {
                    "request": request,
                    "mount_path": config.terminal_path,
                    "theme": config.theme.model_dump(),
                    "title": config.title
                }
            )
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            raise TemplateError(template_file, str(e))

    @app.websocket(f"{config.terminal_path}/ws")
    async def terminal_ws(websocket: WebSocket):
        """Handle WebSocket connections for the terminal."""
        await proxy_manager.proxy_websocket(websocket)

    # Proxy terminal-specific paths
    @app.api_route(
        f"{config.terminal_path}/{{path:path}}",
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"]
    )
    async def proxy_terminal_request(request: Request, path: str):
        """Proxy ttyd-specific HTTP requests."""
        return await proxy_manager.proxy_http(request)

def _configure_app(app: FastAPI, config: TTYDConfig) -> None:
    """
    Configure FastAPI application with ttyd functionality.
    
    This function sets up all necessary components for the terminal service,
    including process management, proxying, static files, and routing.

    Args:
        app: FastAPI application instance
        config: Configuration for the terminal service
    """
    logger.info(f"Configuring ttyd service with {config.mount_path} mounting")
    
    # Initialize managers
    ttyd_manager = TTYDManager(config)
    proxy_manager = ProxyManager(config)
    
    # Set up static files
    package_dir = Path(__file__).parent
    static_dir = package_dir / "static"
    static_dir.mkdir(exist_ok=True)
    
    # Mount static files at the appropriate path based on configuration
    app.mount(
        config.static_path,
        StaticFiles(directory=str(static_dir)),
        name="static"
    )
    
    # Set up templates
    templates, template_file = _setup_templates(app, config)
    
    # Configure routes
    _configure_routes(
        app,
        config,
        ttyd_manager,
        proxy_manager,
        templates,
        template_file
    )
    
    # Store original lifespan
    original_lifespan = app.router.lifespan_context
    
    # Set up lifespan for process management
    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        """Manage the complete lifecycle of the terminal service."""
        logger.info(
            f"Starting ttyd service (mounting: {'root' if config.is_root_mounted else 'non-root'})"
        )
        ttyd_manager.start()
        try:
            if original_lifespan:
                async with original_lifespan(app):
                    yield
            else:
                yield
        finally:
            logger.info("Cleaning up ttyd service...")
            ttyd_manager.stop()
            await proxy_manager.cleanup()
    
    app.router.lifespan_context = combined_lifespan
    logger.info(
        f"ttyd service configured successfully at {config.mount_path} "
        f"(terminal: {config.terminal_path})"
    )

def serve_tty(
    app: FastAPI, 
    client_script: Union[str, Path],
    *,
    mount_path: str = "/",  # Default to root mounting
    port: int = 7681,
    theme: Optional[Dict[str, str]] = None,
    ttyd_options: Optional[Dict[str, Any]] = None,
    template_override: Optional[Union[str, Path]] = None,
    title: str = "Terminal",  # Default title
    debug: bool = False
) -> None:
    """
    Configure FastAPI application with ttyd functionality.
    
    This function is the main entry point for the terminaide package. It sets up
    a terminal service within your FastAPI application, providing a browser-based
    terminal interface to your Python script.
    
    The terminal can be mounted either at the root path ("/") or at a custom path
    ("/your/path"). When mounted at root, the terminal interface appears directly
    at your domain root, creating a cleaner user experience.

    Args:
        app: FastAPI application instance
        client_script: Path to Python script to run in terminal
        mount_path: URL path where to mount terminal (default: "/")
        port: Port for ttyd process (default: 7681)
        theme: Terminal theme configuration (default: {"background": "black"})
        ttyd_options: Additional ttyd process options
        template_override: Custom HTML template path
        title: Custom title for the terminal page (default: "Terminal")
        debug: Enable development mode with auto-reload

    Example for root mounting:
        ```python
        from fastapi import FastAPI
        from terminaide import serve_tty

        app = FastAPI()
        serve_tty(app, "client.py")  # Terminal at /
        ```

    Example for custom path:
        ```python
        serve_tty(
            app,
            "client.py",
            mount_path="/terminal",  # Terminal at /terminal
            theme={"background": "#1a1a1a"},
            title="My Custom Terminal"
        )
        ```
    """
    config = TTYDConfig(
        client_script=client_script,
        mount_path=mount_path,
        port=port,
        theme=theme or {"background": "black"},
        ttyd_options=ttyd_options or {},
        template_override=template_override,
        title=title,
        debug=debug
    )
    
    _configure_app(app, config)