# config.py

"""Core configuration module for Terminaide.

This module contains shared configuration classes and utilities used by different parts of the Terminaide library. It serves as a central point of configuration to avoid circular dependencies.
"""

import sys
import shutil
import logging
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, Request, WebSocket
from typing import Optional, Dict, Union, Tuple, List, Callable, Any

from .proxy import ProxyManager
from .terminal import TTYDManager
from .exceptions import TemplateError
from .models import (
    TTYDConfig,
    ThemeConfig,
    TTYDOptions,
    ScriptConfig,
    IndexPageConfig,
    create_route_configs,
)
from .validator import validate_and_recover_routes

logger = logging.getLogger("terminaide")


def smart_resolve_path(path: Union[str, Path, Callable]) -> Union[Path, Callable]:
    """Resolves a path using a predictable strategy:
    1. If it's a callable function, return it as-is
    2. First try the path as-is (absolute or relative to CWD)
    3. Then try relative to the main script being run (sys.argv[0])

    This approach is both flexible and predictable.
    """
    # If path is a callable function, return it directly
    if callable(path):
        return path

    original_path = Path(path)

    # Strategy 1: Use the path as-is (absolute or relative to CWD)
    if original_path.is_absolute() or original_path.exists():
        return original_path.absolute()

    # Strategy 2: Try relative to the main script being run
    try:
        main_script = Path(sys.argv[0]).absolute()
        main_script_dir = main_script.parent
        script_relative_path = main_script_dir / original_path
        if script_relative_path.exists():
            logger.debug(
                f"Found script at {script_relative_path} (relative to main script)"
            )
            return script_relative_path.absolute()
    except Exception as e:
        logger.debug(f"Error resolving path relative to main script: {e}")

    # Return the original if nothing was found
    return original_path


def copy_preview_image_to_static(preview_image: Path) -> str:
    """
    Copy a preview image to the cache assets directory and then to static directory.
    Returns the filename of the copied image in the static directory.
    """
    logger.debug(f"copy_preview_image_to_static called with: {preview_image}")

    if not preview_image or not preview_image.exists():
        logger.debug(f"Preview image doesn't exist, using default: {preview_image}")
        return "preview.png"  # Use default

    # Get both directories
    package_dir = Path(__file__).parent.parent
    assets_dir = package_dir / "cache" / "assets"
    static_dir = package_dir / "static"
    
    # Ensure both directories exist
    assets_dir.mkdir(exist_ok=True, parents=True)
    static_dir.mkdir(exist_ok=True)

    # Generate a unique filename based on the image content hash
    try:
        # Generate a hash of the file content to create a unique name
        file_hash = hashlib.md5(preview_image.read_bytes()).hexdigest()[:12]
        extension = preview_image.suffix.lower()

        # Only allow common image extensions
        if extension not in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
            logger.warning(
                f"Unsupported image extension: {extension}. Using default preview."
            )
            return "preview.png"

        new_filename = f"preview_{file_hash}{extension}"
        assets_path = assets_dir / new_filename
        static_path = static_dir / new_filename

        # Copy to assets directory first (source of truth)
        shutil.copy2(preview_image, assets_path)
        logger.debug(f"Copied preview image from {preview_image} to {assets_path}")
        
        # Then copy to static directory for serving
        shutil.copy2(assets_path, static_path)
        logger.debug(f"Copied preview image from {assets_path} to {static_path}")

        return new_filename
    except Exception as e:
        logger.warning(f"Failed to copy preview image: {e}. Using default preview.")
        return "preview.png"


@dataclass
class TerminaideConfig:
    """Unified configuration for all Terminaide serving modes."""

    # Common configuration options
    port: int = 8000
    title: str = "Terminal"
    theme: Dict[str, Any] = field(
        default_factory=lambda: {"background": "black", "foreground": "white"}
    )
    log_level: Optional[str] = "info"  # "debug", "info", "warning", "error", None
    banner: Union[bool, str] = True
    forward_env: Union[bool, List[str], Dict[str, Optional[str]]] = True

    # Advanced configuration
    ttyd_options: Dict[str, Any] = field(default_factory=dict)
    template_override: Optional[Path] = None
    trust_proxy_headers: bool = True
    mount_path: str = "/"

    # Preview image configuration
    preview_image: Optional[Path] = None

    # Script/function arguments
    args: Optional[List[str]] = None
    dynamic: bool = False
    args_param: str = "args"

    # Proxy settings
    ttyd_port: int = 7681  # Base port for ttyd processes
    
    # Cache configuration
    ephemeral_cache_dir: Optional[Path] = None  # Override for ephemeral script storage
    monitor_log_path: Optional[Path] = None  # Override for monitor log file location

    # Internal fields (not exposed directly)
    _target: Optional[Union[Callable, Path, Dict[str, Any]]] = None
    _app: Optional[FastAPI] = None
    _mode: str = "function"  # "function", "script", "apps", or "meta"


def build_config(
    config: Optional[TerminaideConfig], overrides: Dict[str, Any]
) -> TerminaideConfig:
    """Build a config object from the provided config and overrides."""
    if config is None:
        config = TerminaideConfig()

    # Handle backward compatibility for deprecated parameters
    if "debug" in overrides:
        logger.warning("'debug' parameter is deprecated. Use log_level='debug' instead.")
        if overrides["debug"]:
            overrides["log_level"] = "debug"
        del overrides["debug"]
    
    if "configure_logging" in overrides:
        logger.warning("'configure_logging' parameter is deprecated. Use log_level=None instead.")
        if not overrides["configure_logging"]:
            overrides["log_level"] = None
        del overrides["configure_logging"]

    # Apply overrides
    for key, value in overrides.items():
        if hasattr(config, key):
            setattr(config, key, value)

    # Validate log_level
    if config.log_level is not None:
        valid_levels = ["debug", "info", "warning", "error", "critical"]
        if config.log_level.lower() not in valid_levels:
            raise ValueError(f"Invalid log_level: {config.log_level}. Must be one of {valid_levels} or None")
        config.log_level = config.log_level.lower()

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
    template_file: str,
) -> None:
    """Define routes for TTYD terminals and index pages."""

    # Check if index template exists
    template_dir = Path(templates.env.loader.searchpath[0])
    index_template_file = "index.html"
    has_index_template = (template_dir / index_template_file).exists()

    if config.has_index_pages and not has_index_template:
        logger.warning(
            f"Index pages configured but {index_template_file} not found in templates directory"
        )

    @app.get(f"{config.mount_path}/health")
    async def health_check():
        return {
            "ttyd": ttyd_manager.check_health(),
            "proxy": proxy_manager.get_routes_info(),
        }

    # Process all route configs
    for route_config in config.route_configs:
        route_path = route_config.route_path

        if isinstance(route_config, IndexPageConfig):
            # Handle index page route
            @app.get(route_path, response_class=HTMLResponse)
            async def index_page_handler(
                request: Request,
                route_config=route_config,
            ):
                try:
                    # Get the index page instance
                    index_page = route_config.index_page

                    # Build template context
                    context = index_page.to_template_context()
                    context["request"] = request

                    # Handle preview image
                    preview_image_path = route_config.get_preview_image()
                    if preview_image_path and preview_image_path.exists():
                        preview_image = copy_preview_image_to_static(preview_image_path)
                    else:
                        preview_image = "preview.png"

                    context["preview_image"] = preview_image

                    logger.debug(f"Rendering index page for route {route_path}")

                    # Check if index template exists
                    if not has_index_template:
                        return HTMLResponse(
                            content=f"<h1>Index template not found</h1><p>Please create {index_template_file}</p>",
                            status_code=500,
                        )

                    return templates.TemplateResponse(index_template_file, context)
                except Exception as e:
                    logger.error(
                        f"Error rendering index page for route {route_path}: {e}"
                    )
                    raise TemplateError(index_template_file, str(e))

        elif isinstance(route_config, ScriptConfig):
            # Handle terminal route
            terminal_path = config.get_terminal_path_for_route(route_path)
            title = route_config.title or config.title

            # Debug logging for preview image config
            logger.debug(f"Script config preview_image: {route_config.preview_image}")
            logger.debug(f"Config preview_image: {config.preview_image}")

            # Get preview image path - prefer script_config's image, fall back to config's, then default
            preview_image = "preview.png"  # Default fallback

            # Try script config preview first
            if route_config.preview_image and route_config.preview_image.exists():
                logger.debug(
                    f"Using script config preview image: {route_config.preview_image}"
                )
                preview_image = copy_preview_image_to_static(route_config.preview_image)
            elif route_config.preview_image:
                logger.warning(
                    f"Script preview image doesn't exist: {route_config.preview_image}"
                )

            # If no script preview or it failed, try global config
            elif config.preview_image:
                logger.debug(
                    f"Using global config preview image: {config.preview_image}"
                )
                if config.preview_image.exists():
                    preview_image = copy_preview_image_to_static(config.preview_image)
                else:
                    logger.warning(
                        f"Global preview image doesn't exist: {config.preview_image}"
                    )
            else:
                logger.debug("No custom preview images configured, using default")

            logger.debug(f"Final preview image for route {route_path}: {preview_image}")

            @app.get(route_path, response_class=HTMLResponse)
            async def terminal_interface(
                request: Request,
                route_path=route_path,
                terminal_path=terminal_path,
                title=title,
                preview_image=preview_image,
                route_config=route_config,
            ):
                try:
                    logger.debug(
                        f"Rendering template with preview_image={preview_image}"
                    )
                    
                    # For dynamic routes, append query parameters to the terminal path
                    iframe_src = terminal_path
                    if route_config.dynamic and request.url.query:
                        iframe_src = f"{terminal_path}?{request.url.query}"
                        logger.debug(f"Dynamic route {route_path}: appending query params to iframe src: {iframe_src}")
                    
                    return templates.TemplateResponse(
                        template_file,
                        {
                            "request": request,
                            "mount_path": iframe_src,
                            "theme": config.theme.model_dump(),
                            "title": title,
                            "preview_image": preview_image,
                            "keyboard_mapping": route_config.keyboard_mapping.model_dump(),
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"Template rendering error for route {route_path}: {e}"
                    )
                    raise TemplateError(template_file, str(e))

            @app.websocket(f"{terminal_path}/ws")
            async def terminal_ws(websocket: WebSocket, route_path=route_path):
                await proxy_manager.proxy_websocket(websocket, route_path=route_path)

            @app.api_route(
                f"{terminal_path}/{{path:path}}",
                methods=[
                    "GET",
                    "POST",
                    "PUT",
                    "DELETE",
                    "OPTIONS",
                    "HEAD",
                    "PATCH",
                    "TRACE",
                ],
            )
            async def proxy_terminal_request(
                request: Request, path: str, route_path=route_path
            ):
                return await proxy_manager.proxy_http(request)


def configure_app(app: FastAPI, config: TTYDConfig):
    """Configure the FastAPI app with the TTYDManager, ProxyManager, and routes."""
    mode = "apps-server" if config.is_multi_script else "solo-server"
    entry_mode = getattr(config, "_mode", "script")

    # Debug-level configuration logging to avoid duplication
    if entry_mode == "meta":
        logger.debug(f"Configuring meta-server with {config.mount_path} mounting")
    else:
        logger.debug(
            f"Configuring {mode} with {config.mount_path} mounting ({entry_mode} API)"
        )

    ttyd_manager = TTYDManager(config)
    proxy_manager = ProxyManager(config)

    package_dir = Path(__file__).parent.parent
    static_dir = package_dir / "static"
    static_dir.mkdir(exist_ok=True)

    terminaide_static_path = "/terminaide-static"  # one-place constant
    app.mount(
        terminaide_static_path,
        StaticFiles(directory=str(static_dir)),
        name="terminaide_static",  # unique route-name
    )

    # config.static_path = terminaide_static_path

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

    mode = "apps-server" if config.is_multi_script else "solo-server"
    entry_mode = getattr(config, "_mode", "script")

    # Consolidated startup log message
    mode_desc = "meta-server" if entry_mode == "meta" else f"{mode} ({entry_mode} API)"
    logger.info(
        f"Starting ttyd service in {mode_desc} mode "
        f"(mounting: {'root' if config.is_root_mounted else 'non-root'})"
    )

    ttyd_manager.start()
    try:
        yield
    finally:
        logger.info("Cleaning up ttyd service...")
        
        # Clean up ephemeral files on graceful shutdown
        try:
            from .wrappers import cleanup_own_ephemeral_files
            cleanup_own_ephemeral_files()
        except ImportError:
            pass  # Graceful fallback if import fails
        
        ttyd_manager.stop()
        await proxy_manager.cleanup()


def extract_routes_from_autoindex(terminal_routes: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and merge routes defined in AutoIndex instances.
    
    Searches through terminal_routes for AutoIndex instances and extracts
    their menu items as route definitions. Explicit routes in terminal_routes
    take precedence over extracted routes.
    
    Args:
        terminal_routes: Dictionary mapping paths to route specifications
        
    Returns:
        Merged dictionary with both explicit and extracted routes
    """
    # Import here to avoid circular import
    from .index import AutoIndex
    
    merged_routes = {}
    
    # Find all AutoIndex instances and extract their routes
    for path, spec in terminal_routes.items():
        if isinstance(spec, AutoIndex):
            extracted = spec.extract_routes()
            
            # Add extracted routes that don't conflict with explicit routes
            for route_path, route_spec in extracted.items():
                if route_path not in terminal_routes:
                    merged_routes[route_path] = route_spec
                else:
                    logger.debug(
                        f"Skipping AutoIndex route {route_path} - explicitly defined in terminal_routes"
                    )
    
    # Merge with original routes (explicit routes preserved)
    result = terminal_routes.copy()
    result.update(merged_routes)
    
    return result


def convert_terminaide_config_to_ttyd_config(
    config: TerminaideConfig, script_path: Path = None
) -> TTYDConfig:
    """Convert a TerminaideConfig to a TTYDConfig."""
    if (
        script_path is None
        and config._target is not None
        and isinstance(config._target, Path)
    ):
        script_path = config._target

    terminal_routes = {}
    if config._mode == "apps" and isinstance(config._target, dict):
        terminal_routes = config._target
    elif script_path is not None:
        # For script mode, include args and dynamic if provided
        if config.args is not None or config.dynamic:
            terminal_routes = {"/": {
                "script": script_path,
                "args": config.args or [],
                "dynamic": config.dynamic,
                "args_param": config.args_param,
            }}
        else:
            terminal_routes = {"/": script_path}
    elif callable(config._target):
        # Handle function target for serve_function mode
        if config.args is not None or config.dynamic:
            terminal_routes = {"/": {
                "function": config._target,
                "args": config.args or [],
                "dynamic": config.dynamic,
                "args_param": config.args_param,
            }}
        else:
            terminal_routes = {"/": config._target}

    # Use create_route_configs instead of create_script_configs
    route_configs = create_route_configs(terminal_routes)
    
    # Check if we're in reload mode and validate/recover routes
    import os
    is_reload = bool(os.environ.get("TERMINAIDE_MODE") and os.environ.get("TERMINAIDE_PORT"))
    if is_reload and route_configs:
        # Filter only ScriptConfig instances for validation
        script_configs = [cfg for cfg in route_configs if isinstance(cfg, ScriptConfig)]
        if script_configs:
            validated_scripts, errors = validate_and_recover_routes(script_configs, is_reload=True)
            # Replace script configs in route_configs with validated ones
            other_configs = [cfg for cfg in route_configs if not isinstance(cfg, ScriptConfig)]
            route_configs = other_configs + validated_scripts
            if errors:
                logger.warning(f"Route validation errors during reload: {'; '.join(errors)}")

    # If we have route configs and a custom title is set, apply it to the first script config
    if route_configs and config.title != "Terminal":
        for cfg in route_configs:
            if isinstance(cfg, ScriptConfig):
                cfg.title = config.title
                break

    # Debug log for preview_image
    if hasattr(config, "preview_image") and config.preview_image:
        logger.debug(
            f"Converting preview_image from TerminaideConfig: {config.preview_image}"
        )

    # Convert theme dict to ThemeConfig
    theme_config = ThemeConfig(**(config.theme or {}))

    # Convert ttyd_options dict to TTYDOptions
    ttyd_options_config = TTYDOptions(**(config.ttyd_options or {}))

    # Find the first script config for backward compatibility
    first_script_config = None
    for cfg in route_configs:
        if isinstance(cfg, ScriptConfig):
            first_script_config = cfg
            break

    ttyd_config = TTYDConfig(
        script=(
            first_script_config.script
            if first_script_config and not first_script_config.is_function_based
            else None
        ),
        mount_path=config.mount_path,
        port=config.ttyd_port,
        theme=theme_config,
        ttyd_options=ttyd_options_config,
        template_override=config.template_override,
        preview_image=config.preview_image,  # Pass the preview_image to TTYDConfig
        title=config.title,  # Keep the original title
        log_level=config.log_level,
        route_configs=route_configs,  # Use route_configs instead of script_configs
        forward_env=config.forward_env,
    )

    # Propagate the entry mode to TTYDConfig - include meta mode
    ttyd_config._mode = config._mode

    # Debug log for meta mode
    if config._mode == "meta":
        logger.debug(f"Converting meta-server config to TTYDConfig")
        # Copy any special meta-specific attributes
        if hasattr(config, "_app_dir"):
            ttyd_config._app_dir = config._app_dir

    return ttyd_config
