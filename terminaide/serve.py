# serve.py

"""
Main implementation for configuring and serving ttyd through FastAPI.

This module provides the core functionality for setting up a ttyd-based terminal
service within a FastAPI application, with three distinct API paths:
1. serve_function: simplest entry point - run a function in a terminal
2. serve_script: simple path - run a Python script in a terminal
3. serve_apps: advanced path - integrate multiple terminals into a FastAPI application
"""

import inspect
import logging
import os
import sys
import signal
import tempfile
# import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any, Union, Tuple, List, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core.manager import TTYDManager
from .core.proxy import ProxyManager
from .core.settings import (
    TTYDConfig,
    ScriptConfig,
    # ThemeConfig,
    # TTYDOptions,
    smart_resolve_path
)
from .exceptions import TemplateError, ConfigurationError

logger = logging.getLogger("terminaide")


def _setup_templates(config: TTYDConfig) -> Tuple[Jinja2Templates, str]:
    """Configure and validate template directory and file."""
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


def _configure_routes(
    app: FastAPI,
    config: TTYDConfig,
    ttyd_manager: TTYDManager,
    proxy_manager: ProxyManager,
    templates: Jinja2Templates,
    template_file: str
) -> None:
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


def _create_script_configs(
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any]]]
) -> List[ScriptConfig]:
    """Convert terminal_routes mapping into a list of ScriptConfig objects."""
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
        # If no "/" route is defined, add the default client at root.
        default_client_path = Path(__file__).parent / "default_client.py"
        script_configs.append(
            ScriptConfig(route_path="/", client_script=default_client_path, title="Terminaide (Intro)")
        )

    if not script_configs:
        raise ConfigurationError("No valid script configuration provided")

    return script_configs


def _configure_app(app: FastAPI, config: TTYDConfig):
    """Set up TTYD managers, routes, static files, etc."""
    mode = "multi-script" if config.is_multi_script else "single-script"
    logger.info(f"Configuring ttyd service with {config.mount_path} mounting ({mode} mode)")

    ttyd_manager = TTYDManager(config)
    proxy_manager = ProxyManager(config)

    package_dir = Path(__file__).parent
    static_dir = package_dir / "static"
    static_dir.mkdir(exist_ok=True)

    app.mount(config.static_path, StaticFiles(directory=str(static_dir)), name="static")

    templates, template_file = _setup_templates(config)
    app.state.terminaide_templates = templates
    app.state.terminaide_template_file = template_file
    app.state.terminaide_config = config

    _configure_routes(app, config, ttyd_manager, proxy_manager, templates, template_file)
    return ttyd_manager, proxy_manager


@asynccontextmanager
async def _terminaide_lifespan(app: FastAPI, config: TTYDConfig):
    """Start TTYD on startup, stop it on shutdown."""
    ttyd_manager, proxy_manager = _configure_app(app, config)
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


async def _default_client_middleware(request: Request, call_next):
    """
    Middleware that serves the default client at the root path
    if no route was found (404 on "/").
    """
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


def _generate_function_wrapper(func: Callable) -> Tuple[Path, List[Callable]]:
    """
    Generate a temporary Python script that calls the given function.
    Return (script_path, [cleanup_funcs]).
    """
    if not callable(func):
        raise TypeError(f"Expected a callable function, got {type(func).__name__}")

    func_name = func.__name__
    module = inspect.getmodule(func)
    module_name = getattr(module, "__name__", None)

    temp_dir = tempfile.mkdtemp(prefix="terminaide_")
    script_path = Path(temp_dir) / f"{func_name}_wrapper.py"

    if module_name == "__main__":
        main_module_file = getattr(module, "__file__", None)
        if main_module_file:
            main_script_path = Path(main_module_file).resolve()
            module_dir = main_script_path.parent
            module_file = main_script_path.name
            base_name = module_file.rsplit('.', 1)[0]
            with open(script_path, "w") as f:
                f.write(f"""# Generated wrapper for function {func_name}
import sys
import os

script_dir = {repr(str(module_dir))}
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    from {base_name} import {func_name}
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location("{base_name}", {repr(str(main_script_path))})
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    {func_name} = getattr(module, "{func_name}")

if __name__ == "__main__":
    {func_name}()
""")
        else:
            # Interactive environment fallback
            source_code = inspect.getsource(func)
            with open(script_path, "w") as f:
                f.write(f"""# Generated wrapper for function {func_name} (interactive env)

{source_code}

if __name__ == "__main__":
    {func_name}()
""")
    else:
        with open(script_path, "w") as f:
            f.write(f"""# Generated wrapper for function {func_name}
from {module_name} import {func_name}

if __name__ == "__main__":
    {func_name}()
""")

    def cleanup_temp_files():
        try:
            if script_path.exists():
                script_path.unlink()
            if Path(temp_dir).exists():
                os.rmdir(temp_dir)
            logger.debug(f"Cleaned up temporary function wrapper: {script_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp wrapper: {e}")

    return script_path, [cleanup_temp_files]


def serve_function(
    func: Callable,
    port: int = 8000,
    title: Optional[str] = None,
    theme: Optional[Dict[str, Any]] = None,
    debug: bool = False
) -> None:
    """
    Serve a Python function in a browser terminal.
    No banner is printed here – we pass a label to serve_script -> serve_apps.
    """
    if title is None:
        title = f"{func.__name__}() Terminal"

    # Generate a temporary wrapper script for the function
    script_path, cleanup_functions = _generate_function_wrapper(func)

    def handle_exit(sig, frame):
        print("\n\033[93mCleaning up...\033[0m")
        for cfunc in cleanup_functions:
            cfunc()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    try:
        # Pass banner_label to serve_script, so we see "Serving function xyz()..."
        func_name = func.__name__
        module_name = func.__module__
        module_desc = f" from {module_name}" if module_name and module_name != "__main__" else ""
        banner_label = f"'{func_name}()'{module_desc}"

        serve_script(
            script_path=script_path,
            port=port,
            title=title,
            theme=theme,
            debug=debug,
            banner_label=banner_label
        )
    finally:
        for cfunc in cleanup_functions:
            cfunc()


def serve_script(
    script_path: Union[str, Path],
    port: int = 8000,
    title: str = "Terminal",
    theme: Optional[Dict[str, Any]] = None,
    debug: bool = False,
    banner_label: Optional[str] = None  # <--- pass "script X" or get from function
) -> None:
    """
    Serve a Python script in a browser terminal.
    No banner is printed here – we pass a label to serve_apps to handle it.
    """
    try:
        script_absolute_path = smart_resolve_path(script_path)
        if not script_absolute_path.exists():
            print(f"\033[91mError: Script not found: {script_path}\033[0m")
            return

        # If banner_label wasn't supplied (meaning direct script mode),
        # then we set it to "<filename>" by default.
        if banner_label is None:
            banner_label = f"{script_absolute_path.name}"

        app = FastAPI(title=f"Terminaide - {title}")
        from .serve import serve_apps

        serve_apps(
            app,
            terminal_routes={"/": script_absolute_path},
            port=7681,
            title=title,
            theme=theme,
            debug=debug,
            banner_label=banner_label  # <--- unify banner logic in serve_apps
        )

        # After serve_apps prints the banner, we print our normal usage lines:
        print(f"\033[96m> URL: \033[1mhttp://localhost:{port}\033[0m")
        print("\033[96m> Press Ctrl+C to exit\033[0m")

        import uvicorn

        def handle_exit(sig, frame):
            print("\n\033[93mShutting down...\033[0m")
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_exit)

        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info" if debug else "warning"
        )

    except Exception as e:
        print(f"\033[91mError starting terminal: {e}\033[0m")
        if debug:
            import traceback
            traceback.print_exc()


def serve_apps(
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
    trust_proxy_headers: bool = True,
    banner_label: Optional[str] = None
) -> None:
    """
    Integrate multiple terminal apps into a FastAPI app. Prints exactly one banner.
      - If banner_label is provided, we use "Serving {banner_label} in a browser terminal."
      - Otherwise, we fallback to "Serving advanced multi-route setup in a browser terminal."
    """
    if trust_proxy_headers:
        try:
            from .middleware import ProxyHeaderMiddleware
            if not any(m.cls.__name__ == "ProxyHeaderMiddleware" for m in getattr(app, "user_middleware", [])):
                app.add_middleware(ProxyHeaderMiddleware)
                logger.info("Added proxy header middleware for HTTPS detection")
        except Exception as e:
            logger.warning(f"Failed to add proxy header middleware: {e}")

    script_configs = _create_script_configs(terminal_routes)
    from .core.settings import TTYDConfig, ThemeConfig, TTYDOptions

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

    sentinel_attr = "_terminaide_lifespan_attached"
    if getattr(app.state, sentinel_attr, False):
        return
    setattr(app.state, sentinel_attr, True)

    app.middleware("http")(_default_client_middleware)

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def terminaide_merged_lifespan(_app: FastAPI):
        if original_lifespan is not None:
            async with original_lifespan(_app):
                async with _terminaide_lifespan(_app, config):
                    yield
        else:
            async with _terminaide_lifespan(_app, config):
                yield

    app.router.lifespan_context = terminaide_merged_lifespan

    # Print a single banner based on banner_label
    if banner_label:
        print("\033[92m" + "="*60 + "\033[0m")
        print(f"\033[92mTerminaide serving {banner_label} on port {config.port}\033[0m")
        print("\033[92m" + "="*60 + "\033[0m")
    else:
        print("\033[92m" + "="*60 + "\033[0m")
        print(f"\033[92mTerminaide serving multi-route setup on port {config.port}\033[0m")
        print("\033[92m" + "="*60 + "\033[0m")