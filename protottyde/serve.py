# protottyde/serve.py

"""
Main implementation for configuring and serving ttyd through FastAPI.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core.manager import TTYDManager
from .core.proxy import ProxyManager
from .core.settings import TTYDConfig
from .exceptions import TemplateError

logger = logging.getLogger("protottyde")

def _setup_templates(app: FastAPI, config: TTYDConfig) -> tuple[Jinja2Templates, str]:
    """Configure template handling."""
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
    """Set up all routes for the ttyd service."""
    
    @app.get(f"{config.mount_path}/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "ttyd": ttyd_manager.check_health(),
            "proxy": proxy_manager.get_routes_info()
        }

    @app.get(config.mount_path, response_class=HTMLResponse)
    async def terminal_interface(request: Request):
        """Serve the terminal interface."""
        try:
            return templates.TemplateResponse(
                template_file,
                {
                    "request": request,
                    "mount_path": f"{config.mount_path}/terminal",
                    "theme": config.theme.model_dump(),
                }
            )
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            raise TemplateError(template_file, str(e))

    @app.websocket(f"{config.mount_path}/terminal/ws")
    async def terminal_ws(websocket: WebSocket):
        """Handle WebSocket connections."""
        await proxy_manager.proxy_websocket(websocket)

    # Proxy terminal-specific paths
    @app.api_route(
        f"{config.mount_path}/terminal/{{path:path}}",
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"]
    )
    async def proxy_terminal_request(request: Request, path: str):
        """Proxy ttyd-specific HTTP requests."""
        return await proxy_manager.proxy_http(request)

def _configure_app(app: FastAPI, config: TTYDConfig) -> None:
    """
    Configure FastAPI application with ttyd functionality.
    """
    logger.info(f"Configuring ttyd service on {config.mount_path}")
    
    # Initialize managers
    ttyd_manager = TTYDManager(config)
    proxy_manager = ProxyManager(config)
    
    # Set up static files and templates
    package_dir = Path(__file__).parent
    static_dir = package_dir / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount(f"{config.mount_path}/static", StaticFiles(directory=str(static_dir)), name="static")
    
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
        """Combined lifespan handling."""
        logger.info("Starting ttyd process...")
        ttyd_manager.start()  # Start ttyd immediately
        try:
            if original_lifespan:
                async with original_lifespan(app):
                    yield
            else:
                yield
        finally:
            logger.info("Cleaning up ttyd...")
            ttyd_manager.stop()
            await proxy_manager.cleanup()
    
    app.router.lifespan_context = combined_lifespan
    logger.info("ttyd service configured successfully")

def serve_tty(
    app: FastAPI, 
    client_script: Union[str, Path],
    *,
    mount_path: str = "/tty",
    port: int = 7681,
    theme: Optional[Dict[str, str]] = None,
    ttyd_options: Optional[Dict[str, Any]] = None,
    template_override: Optional[Union[str, Path]] = None,
    debug: bool = False
) -> None:
    """
    Configure FastAPI application with ttyd functionality.
    
    Args:
        app: FastAPI application instance
        client_script: Path to Python script to run in terminal
        mount_path: URL path to mount terminal (default: "/tty")
        port: Port for ttyd process (default: 7681)
        theme: Terminal theme configuration (default: {"background": "black"})
        ttyd_options: Additional ttyd process options
        template_override: Custom HTML template path
        debug: Enable development mode with auto-reload
    """
    config = TTYDConfig(
        client_script=client_script,
        mount_path=mount_path,
        port=port,
        theme=theme or {"background": "black"},
        ttyd_options=ttyd_options or {},
        template_override=template_override,
        debug=debug
    )
    
    _configure_app(app, config)