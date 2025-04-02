# core/config.py

"""
Core configuration module for Terminaide.

This module contains shared configuration classes and utilities
used by different parts of the Terminaide library. It serves as
a central point of configuration to avoid circular dependencies.
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, Union, Tuple, List, Callable, Awaitable

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .settings import TTYDConfig, ScriptConfig, ThemeConfig, TTYDOptions
from .manager import TTYDManager
from .proxy import ProxyManager
from ..exceptions import TemplateError, ConfigurationError

logger = logging.getLogger("terminaide")

@dataclass
class TerminaideConfig:
    """Unified configuration for all Terminaide serving modes."""
    
    # Common configuration options
    port: int = 8000
    title: str = "Terminal"
    theme: Dict[str, Any] = field(default_factory=lambda: {"background": "black", "foreground": "white"})
    debug: bool = True
    reload: bool = False
    forward_env: Union[bool, List[str], Dict[str, Optional[str]]] = True
    
    # Display options
    banner_label: Optional[str] = None
    
    # Advanced configuration
    ttyd_options: Dict[str, Any] = field(default_factory=dict)
    template_override: Optional[Path] = None
    trust_proxy_headers: bool = True
    mount_path: str = "/"
    
    # Proxy settings
    ttyd_port: int = 7681  # Base port for ttyd processes
    
    # Internal fields (not exposed directly)
    _target: Optional[Union[Callable, Path, Dict[str, Any]]] = None
    _app: Optional[FastAPI] = None
    _mode: str = "function"  # "function", "script", or "apps"


def build_config(config: Optional[TerminaideConfig], overrides: Dict[str, Any]) -> TerminaideConfig:
    """Build a config object from the provided config and overrides."""
    if config is None:
        config = TerminaideConfig()
    
    # Apply overrides
    for key, value in overrides.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    return config


def setup_templates(config: TerminaideConfig) -> Tuple[Jinja2Templates, str]:
    """Set up the Jinja2 templates for the HTML interface."""
    if config.template_override:
        template_dir = config.template_override.parent
        template_file = config.template_override.name
    else:
        template_dir = Path(__file__).parent.parent / "templates"
        template_file = "terminal.html"
    
    if not template_dir.exists():
        raise TemplateError(str(template_dir), "Template directory not found")
    
    templates = Jinja2Templates(directory=str(template_dir))
    
    if not (template_dir / template_file).exists():
        raise TemplateError(template_file, "Template file not found")
    
    return templates, template_file


def configure_routes(
    app: FastAPI,
    config: TTYDConfig,
    ttyd_manager: TTYDManager,
    proxy_manager: ProxyManager,
    templates: Jinja2Templates,
    template_file: str) -> None:
    """Define routes for TTYD: health, interface, websocket, and proxy."""
    
    @app.get(f"{config.mount_path}/health")
    async def health_check():
        return {
            "ttyd": ttyd_manager.check_health(),
            "proxy": proxy_manager.get_routes_info()
        }

    for script_config in config.script_configs:
        route_path = script_config.route_path
        terminal_path = config.get_terminal_path_for_route(route_path)
        title = script_config.title or config.title
        
        @app.get(route_path, response_class=HTMLResponse)
        async def terminal_interface(
            request: Request,
            route_path=route_path,
            terminal_path=terminal_path,
            title=title
        ):
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

        @app.websocket(f"{terminal_path}/ws")
        async def terminal_ws(websocket: WebSocket, route_path=route_path):
            await proxy_manager.proxy_websocket(websocket, route_path=route_path)

        @app.api_route(
            f"{terminal_path}/{{path:path}}",
            methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"]
        )
        async def proxy_terminal_request(request: Request, path: str, route_path=route_path):
            return await proxy_manager.proxy_http(request)


def create_script_configs(
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any]]]) -> List[ScriptConfig]:
    """Convert the terminal_routes dictionary into a list of ScriptConfig objects."""
    script_configs = []
    has_root_path = terminal_routes and "/" in terminal_routes
    
    for route_path, script_spec in terminal_routes.items():
        if isinstance(script_spec, dict) and "client_script" in script_spec:
            script_value = script_spec["client_script"]
            if isinstance(script_value, list) and len(script_value) > 0:
                script_path = script_value[0]
                args = script_value[1:]
            else:
                script_path = script_value
                args = []
            
            if "args" in script_spec:
                args = script_spec["args"]
            
            cfg_data = {
                "route_path": route_path,
                "client_script": script_path,
                "args": args
            }
            
            if "title" in script_spec:
                cfg_data["title"] = script_spec["title"]
            
            if "port" in script_spec:
                cfg_data["port"] = script_spec["port"]
            
            script_configs.append(ScriptConfig(**cfg_data))
        
        elif isinstance(script_spec, list) and len(script_spec) > 0:
            script_path = script_spec[0]
            args = script_spec[1:]
            script_configs.append(
                ScriptConfig(route_path=route_path, client_script=script_path, args=args)
            )
        
        else:
            script_path = script_spec
            script_configs.append(
                ScriptConfig(route_path=route_path, client_script=script_path, args=[])
            )

    if not has_root_path:
        default_client_path = Path(__file__).parent.parent / "core" / "default_client.py"
        script_configs.append(
            ScriptConfig(route_path="/", client_script=default_client_path, title="Terminaide (Intro)")
        )
    
    if not script_configs:
        raise ConfigurationError("No valid script configuration provided")
    
    return script_configs


def configure_app(app: FastAPI, config: TTYDConfig):
    """Configure the FastAPI app with the TTYDManager, ProxyManager, and routes."""
    mode = "multi-script" if config.is_multi_script else "single-script"
    logger.info(f"Configuring ttyd service with {config.mount_path} mounting ({mode} mode)")
    
    ttyd_manager = TTYDManager(config)
    proxy_manager = ProxyManager(config)
    
    package_dir = Path(__file__).parent.parent
    static_dir = package_dir / "static"
    static_dir.mkdir(exist_ok=True)
    
    app.mount(config.static_path, StaticFiles(directory=str(static_dir)), name="static")
    
    templates, template_file = setup_templates(config)
    app.state.terminaide_templates = templates
    app.state.terminaide_template_file = template_file
    app.state.terminaide_config = config
    
    configure_routes(app, config, ttyd_manager, proxy_manager, templates, template_file)
    
    return ttyd_manager, proxy_manager


@asynccontextmanager
async def terminaide_lifespan(app: FastAPI, config: TTYDConfig):
    """Lifespan context manager for the TTYDManager and ProxyManager."""
    ttyd_manager, proxy_manager = configure_app(app, config)
    
    mode = "multi-script" if config.is_multi_script else "single-script"
    logger.info(
        f"Starting ttyd service (mounting: "
        f"{'root' if config.is_root_mounted else 'non-root'}, mode: {mode})"
    )
    
    ttyd_manager.start()
    try:
        yield
    finally:
        logger.info("Cleaning up ttyd service...")
        ttyd_manager.stop()
        await proxy_manager.cleanup()


async def default_client_middleware(request: Request, call_next):
    """Middleware to serve the default client when a route isn't matched."""
    response = await call_next(request)
    
    if request.url.path == "/" and response.status_code == 404:
        templates = request.app.state.terminaide_templates
        template_file = request.app.state.terminaide_template_file
        config = request.app.state.terminaide_config
        terminal_path = config.get_terminal_path_for_route("/")
        
        logger.info("No route matched root path, serving default client via middleware")
        
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
    return response


def convert_terminaide_config_to_ttyd_config(config: TerminaideConfig, script_path: Path = None) -> TTYDConfig:
    """Convert a TerminaideConfig to a TTYDConfig."""
    if script_path is None and config._target is not None and isinstance(config._target, Path):
        script_path = config._target

    terminal_routes = {}
    if config._mode == "apps" and isinstance(config._target, dict):
        terminal_routes = config._target
    elif script_path is not None:
        terminal_routes = {"/": script_path}
    
    script_configs = create_script_configs(terminal_routes)
    
    # Convert theme dict to ThemeConfig
    theme_config = ThemeConfig(**(config.theme or {}))
    
    # Convert ttyd_options dict to TTYDOptions
    ttyd_options_config = TTYDOptions(**(config.ttyd_options or {}))
    
    return TTYDConfig(
        client_script=script_configs[0].client_script if script_configs else Path(__file__).parent.parent / "core" / "default_client.py",
        mount_path=config.mount_path,
        port=config.ttyd_port,
        theme=theme_config,
        ttyd_options=ttyd_options_config,
        template_override=config.template_override,
        title=config.title,
        debug=config.debug,
        script_configs=script_configs,
        forward_env=config.forward_env
    )