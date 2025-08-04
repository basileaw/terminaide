# factory.py

"""
Factory functions and app builders for Terminaide serving modes.

This module contains app creation utilities, environment variable handling,
and factory functions used with Uvicorn's reload feature.
"""

import os
import sys
import json
import logging
import tempfile
import ast
from pathlib import Path
from fastapi import FastAPI
from typing import Callable, Optional, Dict, Any
from contextlib import asynccontextmanager

from .config import (
    TerminaideConfig,
    convert_terminaide_config_to_ttyd_config,
    terminaide_lifespan,
)
from .wrappers import generate_function_wrapper, get_or_ensure_function_wrapper
from .server import ServeWithConfig

logger = logging.getLogger("terminaide")


def set_reload_env_vars(config: TerminaideConfig, mode: str, extra_vars: Optional[Dict[str, Any]] = None) -> None:
    """Set environment variables for reload mode.
    
    Args:
        config: The Terminaide configuration
        mode: The serving mode (function, script, meta)
        extra_vars: Additional environment variables to set
    """
    os.environ["TERMINAIDE_PORT"] = str(config.port)
    os.environ["TERMINAIDE_TITLE"] = config.title
    os.environ["TERMINAIDE_LOG_LEVEL"] = config.log_level or "info"
    os.environ["TERMINAIDE_BANNER"] = json.dumps(config.banner)
    os.environ["TERMINAIDE_THEME"] = str(config.theme or {})
    os.environ["TERMINAIDE_FORWARD_ENV"] = str(config.forward_env)
    os.environ["TERMINAIDE_MODE"] = mode
    
    if hasattr(config, "preview_image") and config.preview_image:
        os.environ["TERMINAIDE_PREVIEW_IMAGE"] = str(config.preview_image)
    
    if hasattr(config, "args") and config.args is not None:
        os.environ["TERMINAIDE_ARGS"] = json.dumps(config.args)
    
    if extra_vars:
        for key, value in extra_vars.items():
            os.environ[key] = str(value)


def parse_reload_env_vars() -> Dict[str, Any]:
    """Parse environment variables set for reload mode.
    
    Returns:
        Dictionary with parsed configuration values
    """
    config_vars = {
        "port": int(os.environ["TERMINAIDE_PORT"]),
        "title": os.environ["TERMINAIDE_TITLE"],
        "log_level": os.environ.get("TERMINAIDE_LOG_LEVEL", "info"),
        "mode": os.environ.get("TERMINAIDE_MODE", "script"),
    }
    
    # Parse banner (JSON to handle both bool and string)
    banner_str = os.environ.get("TERMINAIDE_BANNER", "true")
    try:
        config_vars["banner"] = json.loads(banner_str)
    except:
        config_vars["banner"] = True
    
    # Parse theme
    theme_str = os.environ.get("TERMINAIDE_THEME") or "{}"
    try:
        config_vars["theme"] = ast.literal_eval(theme_str)
    except:
        config_vars["theme"] = {}
    
    # Parse forward_env
    forward_env_str = os.environ.get("TERMINAIDE_FORWARD_ENV", "True")
    try:
        config_vars["forward_env"] = ast.literal_eval(forward_env_str)
    except:
        config_vars["forward_env"] = True
    
    # Parse preview image
    preview_image_str = os.environ.get("TERMINAIDE_PREVIEW_IMAGE")
    if preview_image_str:
        config_vars["preview_image"] = Path(preview_image_str)
    
    # Parse args
    args_str = os.environ.get("TERMINAIDE_ARGS")
    if args_str:
        try:
            config_vars["args"] = json.loads(args_str)
        except:
            config_vars["args"] = None
    
    return config_vars


def create_app_with_lifespan(title: str, config: TerminaideConfig, ttyd_config: Any) -> FastAPI:
    """Create a FastAPI app with common setup and lifespan management.
    
    Args:
        title: The application title
        config: The Terminaide configuration
        ttyd_config: The TTYd configuration
    
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(title=f"Terminaide - {title}")
    
    # Add proxy middleware if needed
    ServeWithConfig.add_proxy_middleware_if_needed(app, config)
    
    # Setup lifespan
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


def copy_config_attributes(source_config: TerminaideConfig, **overrides) -> TerminaideConfig:
    """Create a new config copying attributes from source with optional overrides.
    
    Args:
        source_config: The source configuration to copy from
        **overrides: Attributes to override in the new config
    
    Returns:
        New TerminaideConfig instance
    """
    config_attrs = {
        "port": source_config.port,
        "title": source_config.title,
        "theme": source_config.theme,
        "log_level": source_config.log_level,
        "banner": source_config.banner,
        "forward_env": source_config.forward_env,
        "ttyd_options": source_config.ttyd_options,
        "template_override": source_config.template_override,
        "trust_proxy_headers": source_config.trust_proxy_headers,
        "mount_path": source_config.mount_path,
        "ttyd_port": source_config.ttyd_port,
    }
    
    # Apply overrides
    config_attrs.update(overrides)
    
    # Create new config
    new_config = type(source_config)(**config_attrs)
    
    # Copy optional attributes if they exist
    if hasattr(source_config, "preview_image"):
        new_config.preview_image = source_config.preview_image
    
    
    return new_config




class AppFactory:
    """Factory class for creating FastAPI applications based on environment variables."""

    @classmethod
    def _create_app_from_env(cls, mode: str, ephemeral_path_func: Callable) -> FastAPI:
        """Common app factory logic for both function and script modes.
        
        Args:
            mode: The serving mode ("function" or "script")
            ephemeral_path_func: Function to generate the ephemeral path
        
        Returns:
            Configured FastAPI application
        """
        # Parse environment variables
        config_vars = parse_reload_env_vars()
        
        # Generate ephemeral path using the provided function
        ephemeral_path = ephemeral_path_func()
        
        # Create config
        config = TerminaideConfig(
            port=config_vars["port"],
            title=config_vars["title"],
            theme=config_vars["theme"],
            log_level=config_vars.get("log_level", "info"),
            banner=config_vars["banner"],
            forward_env=config_vars["forward_env"],
            args=config_vars.get("args"),
        )
        
        # Set preview image if available
        if "preview_image" in config_vars:
            preview_path = config_vars["preview_image"]
            if preview_path.exists():
                config.preview_image = preview_path
            else:
                logger.warning(f"Preview image not found: {preview_path}")
        
        config._target = ephemeral_path
        config._mode = mode
        
        # Display banner based on config.banner value
        if config.banner:
            ServeWithConfig.display_banner(config._mode, config.banner)
        
        # Create app with common setup
        ttyd_config = convert_terminaide_config_to_ttyd_config(config, ephemeral_path)
        return create_app_with_lifespan(config.title, config, ttyd_config)

    @classmethod
    def function_app_factory(cls) -> FastAPI:
        """
        Called by uvicorn with factory=True in function mode when reload=True.
        We'll try to re-import the function from its module if it's not __main__/__mp_main__.
        If it *is* in main or mp_main, we search sys.modules for the function, then inline.
        """
        func_name = os.environ.get("TERMINAIDE_FUNC_NAME", "")
        func_mod = os.environ.get("TERMINAIDE_FUNC_MOD", "")
        
        def ephemeral_path_generator():
            func = None
            if func_mod and func_mod not in ("__main__", "__mp_main__"):
                try:
                    mod = __import__(func_mod, fromlist=[func_name])
                    func = getattr(mod, func_name, None)
                except:
                    logger.warning(f"Failed to import {func_name} from {func_mod}")

            if func is None and func_mod in ("__main__", "__mp_main__"):
                candidate_mod = sys.modules.get(func_mod)
                if candidate_mod and hasattr(candidate_mod, func_name):
                    func = getattr(candidate_mod, func_name)

            if func is not None and callable(func):
                # Get args from environment if available
                args = None
                args_str = os.environ.get("TERMINAIDE_ARGS")
                if args_str:
                    try:
                        args = json.loads(args_str)
                    except:
                        args = None
                return generate_function_wrapper(func, args=args)
            else:
                temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
                temp_dir.mkdir(exist_ok=True)
                ephemeral_path = temp_dir / f"{func_name}_cannot_reload.py"
                ephemeral_path.write_text(
                    f'print("ERROR: cannot reload function {func_name} from module={func_mod}")\n',
                    encoding="utf-8",
                )
                return ephemeral_path
        
        return cls._create_app_from_env("function", ephemeral_path_generator)

    @classmethod
    def script_app_factory(cls) -> FastAPI:
        """
        Called by uvicorn with factory=True in script mode when reload=True.
        Rebuilds the FastAPI app from environment variables.
        """
        script_path_str = os.environ["TERMINAIDE_SCRIPT_PATH"]
        mode = os.environ.get("TERMINAIDE_MODE", "script")
        
        def ephemeral_path_generator():
            script_path = Path(script_path_str)
            
            # Check if script exists during reload
            if not script_path.exists():
                logger.error(f"Script not found during reload: {script_path}")
                # Create a temporary error script
                temp_dir = Path(tempfile.gettempdir()) / "terminaide_reload_errors"
                temp_dir.mkdir(exist_ok=True)
                error_script = temp_dir / f"{script_path.stem}_missing.py"
                
                error_content = f'''#!/usr/bin/env python3
# Hot reload error script

print("\\033[91m✗ Script Not Found During Hot Reload\\033[0m")
print()
print(f"The script at the following path could not be found:")
print(f"  {script_path}")
print()
print("This can happen if:")
print("- The file was moved or renamed")
print("- The file was deleted")
print("- There's a configuration mismatch")
print()
print("Please check your server configuration and restart if needed.")
'''
                error_script.write_text(error_content, encoding="utf-8")
                return error_script
                
            return script_path
        
        try:
            return cls._create_app_from_env(mode, ephemeral_path_generator)
        except Exception as e:
            logger.error(f"Failed to create app during reload: {e}")
            # Return a minimal error app
            app = FastAPI(title="Terminaide - Reload Error")
            
            @app.get("/")
            async def error_page():
                return {
                    "error": "Failed to reload application",
                    "details": str(e),
                    "recommendation": "Check server logs and restart if needed"
                }
                
            return app