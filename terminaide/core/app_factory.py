"""
Factory functions and app builders for Terminaide serving modes.

This module contains implementation classes that handle different serving modes
(function, script, apps) and the factory functions used with Uvicorn's reload feature.
"""

import os
import sys
import signal
import inspect
import logging
import uvicorn
import tempfile
from pathlib import Path
from fastapi import FastAPI
from typing import Callable, Optional
from contextlib import asynccontextmanager

from .settings import smart_resolve_path
from .config import (
    TerminaideConfig,
    convert_terminaide_config_to_ttyd_config,
    terminaide_lifespan,
)

logger = logging.getLogger("terminaide")

def inline_source_code_wrapper(func: Callable) -> Optional[str]:
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
    {func_name}()"""

def generate_function_wrapper(func: Callable) -> Path:
    """
    Generate an ephemeral script for the given function. If it's in a real module,
    we do the normal import approach. If it's in __main__ or __mp_main__, inline fallback.
    """
    func_name = func.__name__
    module_name = getattr(func, "__module__", None)
    
    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    script_path = temp_dir / f"{func_name}_wrapper.py"
    
    # If it's a normal module (not main or mp_main)
    if module_name and module_name not in ("__main__", "__mp_main__"):
        wrapper_code = f"""# Ephemeral script for function {func_name} from module {module_name}
from {module_name} import {func_name}
if __name__ == "__main__":
    {func_name}()"""
    
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path
    
    # Otherwise, inline fallback
    inline_code = inline_source_code_wrapper(func)
    if inline_code:
        script_path.write_text(inline_code, encoding="utf-8")
        return script_path
    
    # Last resort: error script
    script_path.write_text(
        f'print("ERROR: cannot reload function {func_name} from module={module_name}, no source found.")\n',
        encoding="utf-8"
    )
    return script_path

class ServeWithConfig:
    """Class responsible for handling the serving implementation for different modes."""
    
    @classmethod
    def serve(cls, config) -> None:
        """Serves the application based on the configuration mode."""
        if config._mode == "function":
            cls.serve_function(config)
        elif config._mode == "script":
            cls.serve_script(config)
        elif config._mode == "apps":
            cls.serve_apps(config)
        else:
            raise ValueError(f"Unknown serving mode: {config._mode}")

    @classmethod
    def serve_function(cls, config) -> None:
        """Implementation for serving a function."""
        if config.reload:
            # Reload mode - set environment variables and delegate to uvicorn
            func = config._target
            os.environ["TERMINAIDE_FUNC_NAME"] = func.__name__
            os.environ["TERMINAIDE_FUNC_MOD"] = func.__module__ if func.__module__ else ""
            os.environ["TERMINAIDE_PORT"] = str(config.port)
            os.environ["TERMINAIDE_TITLE"] = config.title
            os.environ["TERMINAIDE_DEBUG"] = "1" if config.debug else "0"
            os.environ["TERMINAIDE_THEME"] = str(config.theme or {})
            os.environ["TERMINAIDE_FORWARD_ENV"] = str(config.forward_env)
            
            uvicorn.run(
                "terminaide.termin_api:function_app_factory",  # Updated
                factory=True,
                host="0.0.0.0",
                port=config.port,
                reload=True,
                log_level="info" if config.debug else "warning"
            )
        else:
            # Direct mode - use local generate_function_wrapper
            func = config._target
            ephemeral_path = generate_function_wrapper(func)
            banner_label = config.banner_label or f"'{func.__name__}()' from {func.__module__}"
            
            # Create a clean config for script mode
            script_config = type(config)(
                port=config.port,
                title=config.title,
                theme=config.theme,
                debug=config.debug,
                forward_env=config.forward_env,
                banner_label=banner_label,
                ttyd_options=config.ttyd_options,
                template_override=config.template_override,
                trust_proxy_headers=config.trust_proxy_headers,
                mount_path=config.mount_path,
                ttyd_port=config.ttyd_port
            )
            script_config._target = ephemeral_path
            script_config._mode = "script"
            
            cls.serve_script(script_config)

    @classmethod
    def serve_script(cls, config) -> None:
        """Implementation for serving a script."""
        script_path = config._target
        if not isinstance(script_path, Path):
            script_path = Path(script_path)
        
        script_path = smart_resolve_path(script_path)
        if not script_path.exists():
            print(f"\033[91mError: Script not found: {script_path}\033[0m")
            return
        
        banner_label = config.banner_label or f"{script_path.name}"
        
        if config.reload:
            # Reload mode
            os.environ["TERMINAIDE_SCRIPT_PATH"] = str(script_path)
            os.environ["TERMINAIDE_PORT"] = str(config.port)
            os.environ["TERMINAIDE_TITLE"] = config.title
            os.environ["TERMINAIDE_DEBUG"] = "1" if config.debug else "0"
            os.environ["TERMINAIDE_BANNER"] = banner_label
            os.environ["TERMINAIDE_THEME"] = str(config.theme or {})
            os.environ["TERMINAIDE_FORWARD_ENV"] = str(config.forward_env)
            
            uvicorn.run(
                "terminaide.termin_api:script_app_factory",  # Updated
                factory=True,
                host="0.0.0.0",
                port=config.port,
                reload=True,
                log_level="info" if config.debug else "warning"
            )
        else:
            # Direct mode
            app = FastAPI(title=f"Terminaide - {config.title}")
            
            # Convert to TTYDConfig
            ttyd_config = convert_terminaide_config_to_ttyd_config(config, script_path)
            
            # Setup routes and lifecycle
            original_lifespan = app.router.lifespan_context
            
            @asynccontextmanager
            async def terminaide_merged_lifespan(_app: FastAPI):
                if original_lifespan is not None:
                    async with original_lifespan(_app):
                        async with terminaide_lifespan(_app, ttyd_config):
                            yield
                else:
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield
            
            app.router.lifespan_context = terminaide_merged_lifespan
            
            print(f"\033[96m> URL: \033[1mhttp://localhost:{config.port}\033[0m")
            print("\033[96m> Press Ctrl+C to exit\033[0m")
            
            def handle_exit(sig, frame):
                print("\033[93mShutting down...\033[0m")
                sys.exit(0)
            
            signal.signal(signal.SIGINT, handle_exit)
            signal.signal(signal.SIGTERM, handle_exit)
            
            uvicorn.run(
                app,
                host="0.0.0.0",
                port=config.port,
                log_level="info" if config.debug else "warning"
            )

    @classmethod
    def serve_apps(cls, config) -> None:
        """Implementation for serving multiple apps."""
        app = config._app
        terminal_routes = config._target
        
        # Import middleware here to avoid circular imports
        if config.trust_proxy_headers:
            try:
                from .middleware import ProxyHeaderMiddleware
                if not any(m.cls.__name__ == "ProxyHeaderMiddleware" for m in getattr(app, "user_middleware", [])):
                    app.add_middleware(ProxyHeaderMiddleware)
                    logger.info("Added proxy header middleware for HTTPS detection")
            except Exception as e:
                logger.warning(f"Failed to add proxy header middleware: {e}")
        
        # Convert to TTYDConfig
        ttyd_config = convert_terminaide_config_to_ttyd_config(config)
        
        sentinel_attr = "_terminaide_lifespan_attached"
        if getattr(app.state, sentinel_attr, False):
            return
        
        setattr(app.state, sentinel_attr, True)
        
        original_lifespan = app.router.lifespan_context
        
        @asynccontextmanager
        async def terminaide_merged_lifespan(_app: FastAPI):
            if original_lifespan is not None:
                async with original_lifespan(_app):
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield
            else:
                async with terminaide_lifespan(_app, ttyd_config):
                    yield
        
        app.router.lifespan_context = terminaide_merged_lifespan
        
        if config.banner_label:
            print(f"\033[92mTerminaide proxying {config.banner_label} on port {config.ttyd_port}\033[0m")
        else:
            print(f"\033[92mTerminaide proxying multi-routes on port {config.ttyd_port}\033[0m")


class AppFactory:
    """Factory class for creating FastAPI applications based on environment variables."""
    
    @classmethod
    def function_app_factory(cls) -> FastAPI:
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
        theme_str = os.environ.get("TERMINAIDE_THEME") or "{}"
        forward_env_str = os.environ.get("TERMINAIDE_FORWARD_ENV", "True")
        
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
            ephemeral_path = generate_function_wrapper(func)
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
        
        theme = {}
        try:
            theme = ast.literal_eval(theme_str)
        except:
            pass
        
        forward_env = True
        try:
            forward_env = ast.literal_eval(forward_env_str)
        except:
            pass
        
        app = FastAPI(title=f"Terminaide - {title}")
        
        config = TerminaideConfig(
            port=int(port_str),
            title=title,
            theme=theme,
            debug=debug,
            forward_env=forward_env,
            banner_label=banner_label
        )
        config._target = ephemeral_path
        
        # Direct setup instead of recursive uvicorn call
        script_path = config._target
        ttyd_config = convert_terminaide_config_to_ttyd_config(config, script_path)
        
        # Setup routes and lifecycle
        original_lifespan = app.router.lifespan_context
        
        @asynccontextmanager
        async def merged_lifespan(_app: FastAPI):
            if original_lifespan is not None:
                async with original_lifespan(_app):
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield
            else:
                async with terminaide_lifespan(_app, ttyd_config):
                    yield
        
        app.router.lifespan_context = merged_lifespan
        
        return app

    @classmethod
    def script_app_factory(cls) -> FastAPI:
        """
        Called by uvicorn with factory=True in script mode when reload=True.
        Rebuilds the FastAPI app from environment variables.
        """
        script_path_str = os.environ["TERMINAIDE_SCRIPT_PATH"]
        port_str = os.environ["TERMINAIDE_PORT"]
        title = os.environ["TERMINAIDE_TITLE"]
        debug = (os.environ.get("TERMINAIDE_DEBUG") == "1")
        banner_label = os.environ["TERMINAIDE_BANNER"]
        theme_str = os.environ.get("TERMINAIDE_THEME") or "{}"
        forward_env_str = os.environ.get("TERMINAIDE_FORWARD_ENV", "True")
        
        import ast
        
        theme = {}
        try:
            theme = ast.literal_eval(theme_str)
        except:
            pass
        
        forward_env = True
        try:
            forward_env = ast.literal_eval(forward_env_str)
        except:
            pass
        
        script_path = Path(script_path_str)
        app = FastAPI(title=f"Terminaide - {title}")
        
        config = TerminaideConfig(
            port=int(port_str),
            title=title,
            theme=theme,
            debug=debug,
            forward_env=forward_env,
            banner_label=banner_label
        )
        config._target = script_path
        
        # Direct setup instead of recursive uvicorn call
        ttyd_config = convert_terminaide_config_to_ttyd_config(config, script_path)
        
        # Setup routes and lifecycle
        original_lifespan = app.router.lifespan_context
        
        @asynccontextmanager
        async def merged_lifespan(_app: FastAPI):
            if original_lifespan is not None:
                async with original_lifespan(_app):
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield
            else:
                async with terminaide_lifespan(_app, ttyd_config):
                    yield
        
        app.router.lifespan_context = merged_lifespan
        
        return app
