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
    smart_resolve_path
)
from .exceptions import TemplateError, ConfigurationError

import uvicorn

logger = logging.getLogger("terminaide")

###############################################################################
# Template & route setup
###############################################################################

def _setup_templates(config: TTYDConfig) -> Tuple[Jinja2Templates, str]:
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


def _configure_app(app: FastAPI, config: TTYDConfig):
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

###############################################################################
# Ephemeral script generation (with __mp_main__ fix)
###############################################################################

def _inline_source_code_wrapper(func: Callable) -> Optional[str]:
    """
    Attempt to inline the source code of 'func' if it's in __main__ or __mp_main__.
    Return the wrapper code as a string, or None if we can't get source code.
    """
    try:
        source_code = inspect.getsource(func)
    except OSError:
        return None

    func_name = func.__name__
    return f"""# Ephemeral inline function from main or mp_main
{source_code}

if __name__ == "__main__":
    {func_name}()
"""

def _generate_function_wrapper(func: Callable) -> Path:
    """
    Generate an ephemeral script for the given function. If it's in a real module,
    we do the normal import approach. If it's in __main__ or __mp_main__, inline fallback.
    """
    func_name = func.__name__
    module_name = getattr(func, "__module__", None)

    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    script_path = temp_dir / f"{func_name}_wrapper.py"

    # if it's a normal module (not main or mp_main)
    if module_name and module_name not in ("__main__", "__mp_main__"):
        wrapper_code = f"""# Ephemeral script for function {func_name} from module {module_name}
from {module_name} import {func_name}

if __name__ == "__main__":
    {func_name}()
"""
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path

    # otherwise, inline fallback
    inline_code = _inline_source_code_wrapper(func)
    if inline_code:
        script_path.write_text(inline_code, encoding="utf-8")
        return script_path

    # last resort: error script
    script_path.write_text(
        f'print("ERROR: cannot reload function {func_name} from module={module_name}, no source found.")\n',
        encoding="utf-8"
    )
    return script_path

###############################################################################
# Public APIs: serve_function, serve_script, serve_apps
###############################################################################

def serve_function(
    func: Callable,
    port: int = 8000,
    title: Optional[str] = None,
    theme: Optional[Dict[str, Any]] = None,
    debug: bool = False,
    reload: bool = False
) -> None:
    if title is None:
        title = f"{func.__name__}() Terminal"

    if not reload:
        ephemeral_path = _generate_function_wrapper(func)
        banner_label = f"'{func.__name__}()' from {func.__module__}"
        _serve_script_direct(
            ephemeral_path,
            port=port,
            title=title,
            theme=theme,
            debug=debug,
            banner_label=banner_label
        )
    else:
        os.environ["TERMINAIDE_FUNC_NAME"] = func.__name__
        os.environ["TERMINAIDE_FUNC_MOD"] = func.__module__ if func.__module__ else ""
        os.environ["TERMINAIDE_PORT"] = str(port)
        os.environ["TERMINAIDE_TITLE"] = title
        os.environ["TERMINAIDE_DEBUG"] = "1" if debug else "0"
        os.environ["TERMINAIDE_THEME"] = str(theme) if theme else ""

        uvicorn.run(
            "terminaide.serve:_function_app_factory",
            factory=True,
            host="127.0.0.1",
            port=port,
            reload=True,
            log_level="info" if debug else "warning"
        )


def serve_script(
    script_path: Union[str, Path],
    port: int = 8000,
    title: str = "Terminal",
    theme: Optional[Dict[str, Any]] = None,
    debug: bool = False,
    banner_label: Optional[str] = None,
    reload: bool = False
) -> None:
    script_absolute_path = smart_resolve_path(script_path)
    if not script_absolute_path.exists():
        print(f"\033[91mError: Script not found: {script_path}\033[0m")
        return

    if not banner_label:
        banner_label = f"{script_absolute_path.name}"

    if not reload:
        _serve_script_direct(
            script_absolute_path,
            port=port,
            title=title,
            theme=theme,
            debug=debug,
            banner_label=banner_label
        )
    else:
        os.environ["TERMINAIDE_SCRIPT_PATH"] = str(script_absolute_path)
        os.environ["TERMINAIDE_PORT"] = str(port)
        os.environ["TERMINAIDE_TITLE"] = title
        os.environ["TERMINAIDE_DEBUG"] = "1" if debug else "0"
        os.environ["TERMINAIDE_BANNER"] = banner_label
        os.environ["TERMINAIDE_THEME"] = str(theme) if theme else ""

        uvicorn.run(
            "terminaide.serve:_script_app_factory",
            factory=True,
            host="127.0.0.1",
            port=port,
            reload=True,
            log_level="info" if debug else "warning"
        )


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
    if trust_proxy_headers:
        try:
            from .middleware import ProxyHeaderMiddleware
            if not any(m.cls.__name__ == "ProxyHeaderMiddleware" for m in getattr(app, "user_middleware", [])):
                app.add_middleware(ProxyHeaderMiddleware)
                logger.info("Added proxy header middleware for HTTPS detection")
        except Exception as e:
            logger.warning(f"Failed to add proxy header middleware: {e}")

    from .core.settings import TTYDConfig, ThemeConfig, TTYDOptions

    script_configs = _create_script_configs(terminal_routes)
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

    if banner_label:
        print("\033[92m" + "=" * 60 + "\033[0m")
        print(f"\033[92mTerminaide serving {banner_label} on port {config.port}\033[0m")
        print("\033[92m" + "=" * 60 + "\033[0m")
    else:
        print("\033[92m" + "=" * 60 + "\033[0m")
        print(f"\033[92mTerminaide serving multi-route setup on port {config.port}\033[0m")
        print("\033[92m" + "=" * 60 + "\033[0m")


###############################################################################
# Internal: direct (non-reload) approach vs. factory approach
###############################################################################

def _serve_script_direct(
    script_path: Path,
    port: int,
    title: str,
    theme: Optional[Dict[str, Any]],
    debug: bool,
    banner_label: str
):
    """
    Old approach: pass a FastAPI object directly to uvicorn.run().
    This triggers a reload warning if reload=True, so we only do it if reload=False.
    """
    app = FastAPI(title=f"Terminaide - {title}")
    from .serve import serve_apps

    serve_apps(
        app,
        terminal_routes={"/": script_path},
        port=7681,
        title=title,
        theme=theme,
        debug=debug,
        banner_label=banner_label
    )

    print(f"\033[96m> URL: \033[1mhttp://localhost:{port}\033[0m")
    print("\033[96m> Press Ctrl+C to exit\033[0m")

    def handle_exit(sig, frame):
        print("\n\033[93mShutting down...\033[0m")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info" if debug else "warning"
    )


def _script_app_factory() -> FastAPI:
    """
    Called by uvicorn with factory=True in script mode when reload=True.
    Rebuilds the FastAPI app from environment variables.
    """
    script_path_str = os.environ["TERMINAIDE_SCRIPT_PATH"]
    port_str = os.environ["TERMINAIDE_PORT"]
    title = os.environ["TERMINAIDE_TITLE"]
    debug = (os.environ.get("TERMINAIDE_DEBUG") == "1")
    banner_label = os.environ["TERMINAIDE_BANNER"]
    theme_str = os.environ.get("TERMINAIDE_THEME") or ""

    import ast
    theme = None
    if theme_str and theme_str not in ("{}", "None"):
        try:
            theme = ast.literal_eval(theme_str)
        except:
            pass

    script_path = Path(script_path_str)

    app = FastAPI(title=f"Terminaide - {title}")
    from .serve import serve_apps
    serve_apps(
        app,
        terminal_routes={"/": script_path},
        port=7681,
        title=title,
        theme=theme,
        debug=debug,
        banner_label=banner_label
    )
    return app


def _function_app_factory() -> FastAPI:
    """
    Called by uvicorn with factory=True in function mode when reload=True.
    We'll try to re-import the function from its module if it's not __main__/__mp_main__.
    If it *is* in main or mp_main, we search sys.modules for the function, then inline.
    """
    func_name = os.environ.get("TERMINAIDE_FUNC_NAME", "")
    func_mod = os.environ.get("TERMINAIDE_FUNC_MOD", "")
    port_str = os.environ["TERMINAIDE_PORT"]
    title = os.environ["TERMINAIDE_TITLE"]
    debug = (os.environ.get("TERMINAIDE_DEBUG") == "1")
    theme_str = os.environ.get("TERMINAIDE_THEME") or ""

    # Attempt to re-import if not __main__ or __mp_main__
    func = None
    if func_mod and func_mod not in ("__main__", "__mp_main__"):
        try:
            mod = __import__(func_mod, fromlist=[func_name])
            func = getattr(mod, func_name, None)
        except:
            logger.warning(f"Failed to import {func_name} from {func_mod}")

    # If it's __main__ or __mp_main__, see if we can find the function object in sys.modules
    if func is None and func_mod in ("__main__", "__mp_main__"):
        candidate_mod = sys.modules.get(func_mod)
        if candidate_mod and hasattr(candidate_mod, func_name):
            func = getattr(candidate_mod, func_name)

    ephemeral_path = None
    banner_label = f"'{func_name}()' from {func_mod}"

    if func is not None and callable(func):
        ephemeral_path = _generate_function_wrapper(func)
    else:
        # If we still can't get the function, create an error script
        temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
        temp_dir.mkdir(exist_ok=True)
        ephemeral_path = temp_dir / f"{func_name}_cannot_reload.py"
        ephemeral_path.write_text(
            f'print("ERROR: cannot reload function {func_name} from module={func_mod}")\n',
            encoding="utf-8"
        )
        banner_label += " (reload failed)"

    import ast
    theme = None
    if theme_str and theme_str not in ("{}", "None"):
        try:
            theme = ast.literal_eval(theme_str)
        except:
            pass

    app = FastAPI(title=f"Terminaide - {title}")
    from .serve import serve_apps
    serve_apps(
        app,
        terminal_routes={"/": ephemeral_path},
        port=7681,
        title=title,
        theme=theme,
        debug=debug,
        banner_label=banner_label
    )
    return app
