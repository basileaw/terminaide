# serve.py

"""Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application, with three distinct API paths:

1. serve_function: simplest entry point - run a function in a terminal
2. serve_script: simple path - run a Python script in a terminal  
3. serve_apps: advanced path - integrate multiple terminals into a FastAPI application
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, Request, WebSocket
from typing import Optional, Dict, Any, Union, Tuple, List, Callable

from .core.manager import TTYDManager
from .core.proxy import ProxyManager
from .core.settings import TTYDConfig, ScriptConfig
from .core.app_factory import ServeWithConfig, AppFactory
from .exceptions import TemplateError, ConfigurationError

logger = logging.getLogger("terminaide")

# Make the factory functions accessible from the original paths for backward compatibility
function_app_factory = AppFactory.function_app_factory
script_app_factory = AppFactory.script_app_factory

@dataclass
class TerminaideConfig:
    """Unified configuration for all Terminaide serving modes."""
    
    # Common configuration options
    port: int = 8000
    title: str = "Terminal"
    theme: Dict[str, Any] = field(default_factory=lambda: {"background": "black", "foreground": "white"})
    debug: bool = False
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

def development_config(**overrides) -> TerminaideConfig:
    """Create a configuration optimized for development."""
    return TerminaideConfig(
        debug=True,
        reload=True,
        **overrides
    )

def demo_config(**overrides) -> TerminaideConfig:
    """Create a configuration optimized for demos."""
    return TerminaideConfig(
        theme={"background": "#002b36", "foreground": "#839496"},
        debug=True,
        **overrides
    )

def production_config(**overrides) -> TerminaideConfig:
    """Create a configuration optimized for production use."""
    return TerminaideConfig(
        debug=False,
        reload=False,
        trust_proxy_headers=True,
        **overrides
    )

################################################################################
# Helper Functions
################################################################################

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
        template_dir = Path(__file__).parent / "templates"
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
        default_client_path = Path(__file__).parent / "default_client.py"
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
    
    package_dir = Path(__file__).parent
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
    from .core.settings import ThemeConfig, TTYDOptions
    
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
        client_script=script_configs[0].client_script if script_configs else Path(__file__).parent / "default_client.py",
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


################################################################################
# Public API
################################################################################

def serve_function(
    func: Callable,
    config: Optional[TerminaideConfig] = None,
    **kwargs) -> None:
    """Serve a Python function in a browser terminal.
    
    This function creates a web-accessible terminal that runs the provided Python function.
    
    Args:
        func: The function to serve in the terminal
        config: Configuration options for the terminal
        **kwargs: Additional configuration overrides:
            - port: Web server port (default: 8000)
            - title: Terminal window title (default: "{func_name}() Terminal")
            - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
            - debug: Enable debug mode (default: False)
            - reload: Enable auto-reload on code changes (default: False)
            - forward_env: Control environment variable forwarding (default: True)
            - ttyd_options: Options for the ttyd process
            - template_override: Custom HTML template path
            - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
    
    Example:
        ```python
        from terminaide import serve_function
        
        def hello():
            name = input("What's your name? ")
            print(f"Hello, {name}!")
        
        serve_function(hello, port=8000, debug=True)
        ```
    """
    cfg = build_config(config, kwargs)
    cfg._target = func
    cfg._mode = "function"
    
    # Auto-generate title if not specified
    if "title" not in kwargs and (config is None or config.title == "Terminal"):
        cfg.title = f"{func.__name__}() Terminal"
    
    ServeWithConfig.serve(cfg)


def serve_script(
    script_path: Union[str, Path],
    config: Optional[TerminaideConfig] = None,
    **kwargs) -> None:
    """Serve a Python script in a browser terminal.
    
    This function creates a web-accessible terminal that runs the provided Python script.
    
    Args:
        script_path: Path to the script file to serve
        config: Configuration options for the terminal
        **kwargs: Additional configuration overrides:
            - port: Web server port (default: 8000)
            - title: Terminal window title (default: "Terminal")
            - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
            - debug: Enable debug mode (default: False)
            - reload: Enable auto-reload on code changes (default: False)
            - banner_label: Custom label for terminal banner (default: script filename)
            - forward_env: Control environment variable forwarding (default: True)
            - ttyd_options: Options for the ttyd process
            - template_override: Custom HTML template path
            - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
    
    Example:
        ```python
        from terminaide import serve_script
        
        serve_script("my_script.py", port=8000, debug=True)
        ```
    """
    cfg = build_config(config, kwargs)
    cfg._target = Path(script_path)
    cfg._mode = "script"
    
    # Auto-generate banner if not specified
    if "banner_label" not in kwargs and (config is None or config.banner_label is None):
        cfg.banner_label = Path(script_path).name
    
    ServeWithConfig.serve(cfg)


def serve_apps(
    app: FastAPI,
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any]]],
    config: Optional[TerminaideConfig] = None,
    **kwargs) -> None:
    """Integrate multiple terminals into a FastAPI application.
    
    This function configures a FastAPI application to serve multiple terminal instances
    at different routes.
    
    Args:
        app: FastAPI application to extend
        terminal_routes: Dictionary mapping paths to scripts
        config: Configuration options for the terminals
        **kwargs: Additional configuration overrides:
            - port: Web server port (default: 8000)
            - title: Default terminal window title (default: "Terminal")
            - theme: Terminal theme colors (default: {"background": "black", "foreground": "white"})
            - debug: Enable debug mode (default: False)
            - ttyd_port: Base port for ttyd processes (default: 7681)
            - mount_path: Base path for terminal mounting (default: "/")
            - forward_env: Control environment variable forwarding (default: True)
            - ttyd_options: Options for the ttyd processes
            - template_override: Custom HTML template path
            - trust_proxy_headers: Trust X-Forwarded-Proto headers (default: True)
    
    Example:
        ```python
        from fastapi import FastAPI
        from terminaide import serve_apps
        
        app = FastAPI()
        
        @app.get("/")
        def root():
            return {"message": "Hello World"}
        
        serve_apps(
            app,
            terminal_routes={
                "/cli1": "script1.py",
                "/cli2": ["script2.py", "--arg1", "value"]
            }
        )
        ```
    """
    cfg = build_config(config, kwargs)
    cfg._target = terminal_routes
    cfg._app = app
    cfg._mode = "apps"
    
    ServeWithConfig.serve(cfg)