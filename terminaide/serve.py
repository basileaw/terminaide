# terminaide/serve.py

"""
Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application. All side effects (like spawning the ttyd
process) happen only when the server truly starts.
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
    """

    @app.get(f"{config.mount_path}/health")
    async def health_check():
        return {
            "ttyd": ttyd_manager.check_health(),
            "proxy": proxy_manager.get_routes_info()
        }

    @app.get(config.mount_path, response_class=HTMLResponse)
    async def terminal_interface(request: Request):
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

    @app.api_route(
        f"{config.terminal_path}/{{path:path}}",
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"]
    )
    async def proxy_terminal_request(request: Request, path: str):
        """Proxy ttyd-specific HTTP requests."""
        return await proxy_manager.proxy_http(request)


def _configure_app(app: FastAPI, config: TTYDConfig):
    """
    Perform all TTYD setup: managers, routes, static files, etc.
    """
    logger.info(f"Configuring ttyd service with {config.mount_path} mounting")

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

    # We’ll return these managers so we can manage their lifecycle in a lifespan
    return ttyd_manager, proxy_manager


@asynccontextmanager
async def _terminaide_lifespan(app: FastAPI, config: TTYDConfig):
    """
    Custom lifespan context that:
      - Configures TTYD at startup
      - Starts the TTYD process
      - Cleans up TTYD on shutdown
    """

    # Actually do all route/static config (which logs "Configuring ttyd service..." etc.)
    ttyd_manager, proxy_manager = _configure_app(app, config)

    logger.info(
        f"Starting ttyd service (mounting: "
        f"{'root' if config.is_root_mounted else 'non-root'})"
    )
    ttyd_manager.start()

    try:
        yield  # Wait here while the app runs
    finally:
        logger.info("Cleaning up ttyd service...")
        ttyd_manager.stop()
        await proxy_manager.cleanup()


def serve_tty(
    app: FastAPI,
    client_script: Optional[Union[str, Path]] = None,
    *,
    mount_path: str = "/",
    port: int = 7681,
    theme: Optional[Dict[str, Any]] = None,
    ttyd_options: Optional[Dict[str, Any]] = None,
    template_override: Optional[Union[str, Path]] = None,
    title: str = "Terminal",
    debug: bool = False
) -> None:
    """
    Attach a single custom lifespan to the app, so TTYD is only set up at real startup,
    not on mere import. This yields a single line in user code:

        app = FastAPI()
        serve_tty(app)

    ...and no duplicate logs even if the module is imported multiple times.
    """

    used_demo = False
    if client_script is None:
        # Use built-in demo if not provided
        demo_path = Path(__file__).parent / "demos" / "instructions.py"
        client_script = demo_path
        used_demo = True
        # If the title is default, change it
        if title == "Terminal":
            title = "Terminaide Demo"

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

        # Merge user’s lifespan with terminaide’s
        if original_lifespan is not None:
            async with original_lifespan(_app):
                async with _terminaide_lifespan(_app, config):
                    yield
        else:
            async with _terminaide_lifespan(_app, config):
                yield

    # Attach our merged lifespan
    app.router.lifespan_context = terminaide_merged_lifespan

