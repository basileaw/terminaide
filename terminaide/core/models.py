# data_models.py

"""Defines Pydantic-based settings for terminaide, including path handling for root/non-root mounting and multiple script routing."""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Callable, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

from .exceptions import ConfigurationError

logger = logging.getLogger("terminaide")


class TTYDOptions(BaseModel):
    """TTYd-specific options like auth, interface, and client capacity."""

    writable: bool = True
    port: int = Field(default=7681, gt=1024, lt=65535)
    interface: str = "0.0.0.0"  # Changed from "127.0.0.1" to bind to all interfaces
    check_origin: bool = True
    max_clients: int = Field(default=1, gt=0)
    credential_required: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    force_https: bool = False

    @model_validator(mode="after")
    def validate_credentials(self) -> "TTYDOptions":
        """Require username/password if credentials are enabled."""
        if self.credential_required and not (self.username and self.password):
            raise ConfigurationError(
                "Both username and password must be provided when credential_required=True"
            )
        return self


class ThemeConfig(BaseModel):
    """Defines basic color and font options for the terminal."""

    background: str = "black"
    foreground: str = "white"
    cursor: str = "white"
    cursor_accent: Optional[str] = None
    selection: Optional[str] = None
    font_family: Optional[str] = None
    font_size: Optional[int] = Field(default=None, gt=0)


class KeyboardMappingConfig(BaseModel):
    """Configuration for CMD to CTRL keyboard mapping in terminal interface."""
    
    mode: Literal["none", "smart", "all", "custom"] = "none"
    custom_mappings: Dict[str, bool] = Field(default_factory=dict)
    
    @property
    def smart_defaults(self) -> Dict[str, bool]:
        """Smart default mappings for common editing and navigation shortcuts."""
        return {
            # Editing shortcuts (CMD+key → CTRL+key)
            "z": True,   # Undo
            "y": True,   # Redo
            "x": True,   # Cut
            "c": True,   # Copy
            "v": True,   # Paste
            "a": True,   # Select All
            "s": True,   # Save
            "f": True,   # Find
            
            # Navigation shortcuts (CMD+Arrow → Home/End/CTRL+Home/CTRL+End)
            "arrowleft": True,   # CMD+Left → Home (beginning of line)
            "arrowright": True,  # CMD+Right → End (end of line)
            "arrowup": True,     # CMD+Up → CTRL+Home (beginning of document)
            "arrowdown": True,   # CMD+Down → CTRL+End (end of document)
            
            # System shortcuts that should NOT be mapped
            "tab": False,  # App switching
            "w": False,    # Close tab
            "q": False,    # Quit
            "r": False,    # Refresh
            "t": False,    # New tab
            "n": False,    # New window
            "l": False,    # Address bar
            ",": False,    # Preferences
        }
    
    def should_map_key(self, key: str) -> bool:
        """Determine if a given key should be mapped based on current mode and settings."""
        # Normalize key for lookup (handle arrow keys specially)
        if key.lower().startswith("arrow"):
            key_normalized = key.lower()  # "ArrowLeft" → "arrowleft"
        else:
            key_normalized = key.lower()
        
        if self.mode == "none":
            return False
        elif self.mode == "all":
            return True
        elif self.mode == "smart":
            return self.smart_defaults.get(key_normalized, False)
        elif self.mode == "custom":
            # Use custom mappings, falling back to smart defaults
            if key_normalized in self.custom_mappings:
                return self.custom_mappings[key_normalized]
            return self.smart_defaults.get(key_normalized, False)
        
        return False


class RouteConfigBase(BaseModel):
    """Base class for all route configurations."""

    route_path: str
    preview_image: Optional[Path] = None
    title: Optional[str] = None

    @field_validator("route_path")
    @classmethod
    def validate_route_path(cls, v: str) -> str:
        """Normalize route path to start with '/' and remove trailing '/'."""
        if not v.startswith("/"):
            v = f"/{v}"
        if v != "/" and v.endswith("/"):
            v = v.rstrip("/")
        return v

    @field_validator("preview_image")
    @classmethod
    def validate_preview_image_path(
        cls, v: Optional[Union[str, Path]]
    ) -> Optional[Path]:
        """
        Ensure the preview image file exists if provided, trying:
        1. The path as provided (relative to CWD or absolute)
        2. The path relative to the main script being executed
        3. Look in common static dirs relative to main script (static, assets, images)
        4. Look relative to project root directories
        """
        if v is None:
            return None

        original_path = Path(v)

        # Strategy 1: Use the path as-is (absolute or relative to CWD)
        if original_path.is_absolute() or original_path.exists():
            return original_path.absolute()

        # Strategy 2: Try relative to the main script being run
        try:
            main_script = Path(sys.argv[0]).absolute()
            main_script_dir = main_script.parent
            image_relative_path = main_script_dir / original_path
            if image_relative_path.exists():
                logger.debug(
                    f"Found preview image at {image_relative_path} (relative to main script)"
                )
                return image_relative_path.absolute()

            # Strategy 3: Try common static directories relative to the main script
            for common_dir in ["static", "assets", "images", "img"]:
                common_path = main_script_dir / common_dir / original_path.name
                if common_path.exists():
                    logger.debug(
                        f"Found preview image at {common_path} (in common directory)"
                    )
                    return common_path.absolute()

            # Strategy 4: Try going up directories to find project root with static dirs
            current_dir = main_script_dir
            for _ in range(3):  # Limit depth to prevent excessive searching
                parent_dir = current_dir.parent
                if parent_dir == current_dir:  # Reached filesystem root
                    break

                current_dir = parent_dir
                for common_dir in ["static", "assets", "images", "img"]:
                    common_path = current_dir / common_dir / original_path.name
                    if common_path.exists():
                        logger.debug(
                            f"Found preview image at {common_path} (in project structure)"
                        )
                        return common_path.absolute()
        except Exception as e:
            logger.debug(
                f"Error resolving preview image path relative to main script: {e}"
            )

        # If we got here, log a warning but don't fail - we'll fall back to the default
        logger.warning(
            f"Preview image does not exist: {v}. Will use default preview image."
        )
        return None

    def is_terminal_route(self) -> bool:
        """Check if this route requires a terminal (ttyd process)."""
        return False


class ScriptConfig(RouteConfigBase):
    """Configuration for a single terminal route, including the script path, port assignment, and optional custom title."""

    script: Optional[Path] = None
    args: List[str] = Field(default_factory=list)
    port: Optional[int] = None
    function_object: Optional[Callable] = None
    _function_wrapper_path: Optional[Path] = None
    dynamic: bool = False  # Enable dynamic argument passing via query parameters
    args_param: str = "args"  # Query parameter name for dynamic arguments
    _dynamic_wrapper_path: Optional[Path] = None
    keyboard_mapping: KeyboardMappingConfig = Field(default_factory=KeyboardMappingConfig)

    @field_validator("script")
    @classmethod
    def validate_script_path(cls, v: Optional[Union[str, Path]]) -> Optional[Path]:
        """
        Ensure the script file exists, trying:
        1. The path as provided (relative to CWD or absolute)
        2. The path relative to the main script being executed

        Returns None if no script path is provided (function-based route).
        """
        if v is None:
            return None

        original_path = Path(v)

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

        # If we got here, the path doesn't exist
        error_msg = f"Script file does not exist: {v}\n"

        # Add context about where we looked
        cwd_path = Path.cwd() / v
        error_msg += f"Current working directory: {os.getcwd()}\n"
        error_msg += f"Tried:\n"
        error_msg += f"  - As provided: {v}\n"
        error_msg += f"  - Relative to CWD: {cwd_path}\n"

        # Add info about script-relative path if available
        if sys.argv and len(sys.argv) > 0:
            script_path = Path(sys.argv[0]).absolute().parent / v
            error_msg += f"  - Relative to main script: {script_path}\n"

        raise ConfigurationError(error_msg)

    @field_validator("args")
    @classmethod
    def validate_args(cls, v: List[str]) -> List[str]:
        """Convert all args to strings."""
        return [str(arg) for arg in v]

    @model_validator(mode="after")
    def validate_script_or_function(self) -> "ScriptConfig":
        """Ensure either script or function_object is provided."""
        if self.script is None and self.function_object is None:
            raise ConfigurationError(
                "Either script or function_object must be provided for route "
                + f"'{self.route_path}'"
            )
        return self

    @property
    def is_function_based(self) -> bool:
        """Returns True if this route uses a function instead of a script."""
        return self.function_object is not None

    def set_function_wrapper_path(self, path: Path) -> None:
        """Set the path to the generated wrapper script for a function."""
        self._function_wrapper_path = path
    
    def set_dynamic_wrapper_path(self, path: Path) -> None:
        """Set the path to the generated dynamic wrapper script."""
        self._dynamic_wrapper_path = path

    @property
    def effective_script_path(self) -> Path:
        """Returns the script path to use (priority: dynamic_wrapper > function_wrapper > script)."""
        if self.dynamic and self._dynamic_wrapper_path is not None:
            return self._dynamic_wrapper_path
        if self.is_function_based and self._function_wrapper_path is not None:
            return self._function_wrapper_path
        return self.script

    def is_terminal_route(self) -> bool:
        """ScriptConfig routes always require a terminal."""
        return True


class IndexPageConfig(RouteConfigBase):
    """Configuration for an index page route."""

    index_page: Any  # Will be IndexPage instance, using Any to avoid circular import

    def is_terminal_route(self) -> bool:
        """Index pages don't require terminals."""
        return False

    def get_preview_image(self) -> Optional[Path]:
        """Get preview image from either the config or the IndexPage."""
        if self.preview_image:
            return self.preview_image
        elif hasattr(self.index_page, "preview_image"):
            return self.index_page.preview_image
        return None


class TTYDConfig(BaseModel):
    """Main configuration for terminaide, handling root vs. non-root mounting, multiple scripts, and other settings like theme and debug mode."""

    script: Optional[Path] = None
    mount_path: str = "/"
    port: int = Field(default=7681, gt=1024, lt=65535)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    ttyd_options: TTYDOptions = Field(default_factory=TTYDOptions)
    template_override: Optional[Path] = None
    preview_image: Optional[Path] = None  # Added preview_image field
    log_level: Optional[str] = "info"  # "debug", "info", "warning", "error", None
    title: str = "Terminal"
    route_configs: List[Union[ScriptConfig, IndexPageConfig]] = Field(
        default_factory=list
    )
    _mode: str = "script"  # Default mode: "function", "script", "apps", or "meta"
    forward_env: Union[bool, List[str], Dict[str, Optional[str]]] = True
    venv_detection: bool = True  # Enable automatic virtual environment detection

    # Legacy field names for backward compatibility
    @property
    def script_configs(self) -> List[ScriptConfig]:
        """Backward compatibility: return only ScriptConfig instances."""
        return [cfg for cfg in self.route_configs if isinstance(cfg, ScriptConfig)]

    @field_validator("script", "template_override")
    @classmethod
    def validate_paths(cls, v: Optional[Union[str, Path]]) -> Optional[Path]:
        """Ensure given path exists, if provided."""
        if v is None:
            return None
        path = Path(v)
        if not path.exists():
            # Check if we're in a reload context
            import os
            if os.environ.get("TERMINAIDE_MODE") and os.environ.get("TERMINAIDE_PORT"):
                # We're in a reload context - log warning but don't crash
                logger.warning(
                    f"Path does not exist during hot reload: {path}. "
                    "This may cause route failures."
                )
                # Return None to allow graceful degradation
                return None
            else:
                # Initial startup - strict validation
                raise ConfigurationError(f"Path does not exist: {path}")
        return path.absolute()

    @field_validator("preview_image")
    @classmethod
    def validate_preview_image(cls, v: Optional[Union[str, Path]]) -> Optional[Path]:
        """Ensure preview image exists, if provided."""
        if v is None:
            return None
        path = Path(v)
        if not path.exists():
            logger.warning(
                f"Preview image path does not exist: {path}. Will use default preview image."
            )
            return None
        return path.absolute()

    @field_validator("mount_path")
    @classmethod
    def validate_mount_path(cls, v: str) -> str:
        """Normalize and disallow '/terminal' as a mount path."""
        if v in ("", "/"):
            return "/"
        if not v.startswith("/"):
            v = f"/{v}"
        v = v.rstrip("/")
        if v == "/terminal":
            raise ConfigurationError(
                '"/terminal" is reserved. Please use another mount path.'
            )
        return v

    @model_validator(mode="after")
    def validate_route_configs(self) -> "TTYDConfig":
        """Check for unique route paths and handle a default script if no routes given."""
        seen_routes = set()
        for config in self.route_configs:
            if config.route_path in seen_routes:
                raise ConfigurationError(f"Duplicate route path: {config.route_path}")
            seen_routes.add(config.route_path)

        # Add a default script config if needed (backward compatibility)
        if not self.route_configs and self.script:
            self.route_configs.append(
                ScriptConfig(
                    route_path="/",
                    script=self.script,
                    args=[],
                    port=self.port,
                    title=self.title,
                    preview_image=self.preview_image,
                )
            )
        return self

    @property
    def is_root_mounted(self) -> bool:
        """True if mounted at root ('/')."""
        return self.mount_path == "/"

    @property
    def is_multi_script(self) -> bool:
        """True if multiple scripts are configured."""
        return len(self.script_configs) > 1

    @property
    def has_index_pages(self) -> bool:
        """True if any index pages are configured."""
        return any(isinstance(cfg, IndexPageConfig) for cfg in self.route_configs)

    @property
    def is_meta_mode(self) -> bool:
        """True if this is a meta-server configuration."""
        return self._mode == "meta"

    @property
    def terminal_path(self) -> str:
        """Return the terminal's path, accounting for root or non-root mounting."""
        if self.is_root_mounted:
            return "/terminal"
        return f"{self.mount_path}/terminal"

    @property
    def static_path(self) -> str:
        """Return the path for static files."""
        if self.is_root_mounted:
            return "/static"
        return f"{self.mount_path}/static"

    def get_route_config_for_path(
        self, path: str
    ) -> Optional[Union[ScriptConfig, IndexPageConfig]]:
        """
        Find which route config matches an incoming request path.
        """
        # For single route configs, return it if the path matches
        if len(self.route_configs) == 1:
            return self.route_configs[0]

        # Sort by path length to match most specific first
        sorted_configs = sorted(
            self.route_configs, key=lambda c: len(c.route_path), reverse=True
        )

        for config in sorted_configs:
            if path == config.route_path or path.startswith(config.route_path + "/"):
                return config

        return None

    def get_script_config_for_path(self, path: str) -> Optional[ScriptConfig]:
        """
        Find which script config matches an incoming request path,
        returning the default if none match.
        """
        config = self.get_route_config_for_path(path)
        if config and isinstance(config, ScriptConfig):
            return config

        # Fallback to first script config if available
        for cfg in self.route_configs:
            if isinstance(cfg, ScriptConfig):
                return cfg

        return None

    def get_terminal_path_for_route(self, route_path: str) -> str:
        """Return the terminal path for a specific route, or global path if root."""
        if route_path == "/":
            return self.terminal_path
        return f"{route_path}/terminal"

    def get_health_check_info(self) -> Dict[str, Any]:
        """Return structured data about the config for health checks."""
        route_info = []

        for config in self.route_configs:
            if isinstance(config, ScriptConfig):
                route_info.append(
                    {
                        "type": "terminal",
                        "route_path": config.route_path,
                        "script": str(config.effective_script_path),
                        "is_function": config.is_function_based,
                        "args": config.args,
                        "port": config.port,
                        "title": config.title or self.title,
                        "preview_image": (
                            str(config.preview_image) if config.preview_image else None
                        ),
                    }
                )
            elif isinstance(config, IndexPageConfig):
                route_info.append(
                    {
                        "type": "index",
                        "route_path": config.route_path,
                        "title": config.title
                        or getattr(config.index_page, "page_title", "Index"),
                        "preview_image": (
                            str(config.get_preview_image())
                            if config.get_preview_image()
                            else None
                        ),
                        "menu_items": len(config.index_page.get_all_menu_items()),
                    }
                )

        # Include meta-server specific info if in meta mode
        meta_info = {}
        if self.is_meta_mode:
            meta_info = {
                "is_meta_server": True,
                "app_dir": str(getattr(self, "_app_dir", "auto-detected")),
            }

        return {
            "mount_path": self.mount_path,
            "terminal_path": self.terminal_path,
            "static_path": self.static_path,
            "is_root_mounted": self.is_root_mounted,
            "is_multi_script": self.is_multi_script,
            "has_index_pages": self.has_index_pages,
            "entry_mode": self._mode,  # Add entry mode to health check info
            "port": self.port,
            "log_level": self.log_level,
            "max_clients": self.ttyd_options.max_clients,
            "auth_required": self.ttyd_options.credential_required,
            "preview_image": str(self.preview_image) if self.preview_image else None,
            "route_configs": route_info,
            **meta_info,  # Include meta-server info if applicable
        }


def create_route_configs(
    terminal_routes: Dict[str, Union[str, Path, List, Dict[str, Any], Callable]],
) -> List[Union[ScriptConfig, IndexPageConfig]]:
    """
    Convert the terminal_routes dictionary into a list of route configurations.

    Now supports:
    - Script paths (str/Path)
    - Functions (Callable)
    - Lists with script path and args
    - Dictionaries with advanced config for scripts or functions
    - IndexPage instances
    - AutoIndex instances with embedded route definitions
    """
    # Import here to avoid circular import
    from .index import AutoIndex
    from ..core.config import extract_routes_from_autoindex
    
    # Extract routes from AutoIndex instances first
    expanded_routes = extract_routes_from_autoindex(terminal_routes)

    route_configs = []

    for route_path, route_spec in expanded_routes.items():
        # Handle AutoIndex instances
        if isinstance(route_spec, AutoIndex):
            route_configs.append(
                IndexPageConfig(
                    route_path=route_path,
                    index_page=route_spec,
                    preview_image=route_spec.preview_image,
                    title=route_spec.title,
                )
            )
            continue

        # Handle direct callable function
        if callable(route_spec):
            func = route_spec
            func_name = getattr(func, "__name__", "function")

            route_configs.append(
                ScriptConfig(
                    route_path=route_path,
                    function_object=func,
                    script=None,
                    args=[],
                    title=f"{func_name}()",
                )
            )
            continue

        # Handle dictionary configuration that might contain a function
        if isinstance(route_spec, dict) and "function" in route_spec:
            func = route_spec["function"]
            if not callable(func):
                raise ConfigurationError(
                    f"'function' value for route {route_path} is not callable"
                )

            func_name = getattr(func, "__name__", "function")

            cfg_data = {
                "route_path": route_path,
                "function_object": func,
                "client_script": None,
                "args": [],
            }

            # Use provided title or auto-generate
            if "title" in route_spec:
                cfg_data["title"] = route_spec["title"]
            else:
                cfg_data["title"] = f"{func_name}()"

            if "port" in route_spec:
                cfg_data["port"] = route_spec["port"]

            if "preview_image" in route_spec:
                cfg_data["preview_image"] = route_spec["preview_image"]
            
            if "dynamic" in route_spec:
                cfg_data["dynamic"] = route_spec["dynamic"]
            
            if "args_param" in route_spec:
                cfg_data["args_param"] = route_spec["args_param"]
            
            if "keyboard_mapping" in route_spec:
                if isinstance(route_spec["keyboard_mapping"], dict):
                    cfg_data["keyboard_mapping"] = KeyboardMappingConfig(**route_spec["keyboard_mapping"])
                else:
                    cfg_data["keyboard_mapping"] = route_spec["keyboard_mapping"]

            route_configs.append(ScriptConfig(**cfg_data))
            continue

        # Handle script path or function in dictionary
        # Support both "script" (new) and "client_script" (backward compatibility)
        if isinstance(route_spec, dict) and ("script" in route_spec or "client_script" in route_spec):
            # Use "script" if present, otherwise fall back to "client_script"
            script_value = route_spec.get("script") or route_spec.get("client_script")
            
            # Check if script is actually a function
            if callable(script_value):
                func = script_value
                func_name = getattr(func, "__name__", "function")
                
                cfg_data = {
                    "route_path": route_path,
                    "function_object": func,
                    "script": None,
                    "args": [],
                }
                
                # Use provided title or auto-generate
                if "title" in route_spec:
                    cfg_data["title"] = route_spec["title"]
                else:
                    cfg_data["title"] = f"{func_name}()"
                
                if "port" in route_spec:
                    cfg_data["port"] = route_spec["port"]
                
                if "preview_image" in route_spec:
                    cfg_data["preview_image"] = route_spec["preview_image"]
                
                if "dynamic" in route_spec:
                    cfg_data["dynamic"] = route_spec["dynamic"]
                
                if "args_param" in route_spec:
                    cfg_data["args_param"] = route_spec["args_param"]
                
                if "keyboard_mapping" in route_spec:
                    if isinstance(route_spec["keyboard_mapping"], dict):
                        cfg_data["keyboard_mapping"] = KeyboardMappingConfig(**route_spec["keyboard_mapping"])
                    else:
                        cfg_data["keyboard_mapping"] = route_spec["keyboard_mapping"]
                
                route_configs.append(ScriptConfig(**cfg_data))
                continue
            
            # Handle script path (existing logic)
            if isinstance(script_value, list) and len(script_value) > 0:
                script_path = script_value[0]
                args = script_value[1:]
            else:
                script_path = script_value
                args = []

            if "args" in route_spec:
                args = route_spec["args"]

            cfg_data = {
                "route_path": route_path,
                "script": script_path,
                "args": args,
            }

            # Use provided title or auto-generate if not present
            if "title" in route_spec:
                cfg_data["title"] = route_spec["title"]
            else:
                # Auto-generate title based on script name
                script_name = Path(script_path).name
                cfg_data["title"] = f"{script_name}"

            if "port" in route_spec:
                cfg_data["port"] = route_spec["port"]

            # Handle preview_image if provided in the script_spec
            if "preview_image" in route_spec:
                cfg_data["preview_image"] = route_spec["preview_image"]
            
            if "dynamic" in route_spec:
                cfg_data["dynamic"] = route_spec["dynamic"]
            
            if "args_param" in route_spec:
                cfg_data["args_param"] = route_spec["args_param"]
            
            if "keyboard_mapping" in route_spec:
                if isinstance(route_spec["keyboard_mapping"], dict):
                    cfg_data["keyboard_mapping"] = KeyboardMappingConfig(**route_spec["keyboard_mapping"])
                else:
                    cfg_data["keyboard_mapping"] = route_spec["keyboard_mapping"]

            route_configs.append(ScriptConfig(**cfg_data))
            continue

        # Handle script path with args as list
        if isinstance(route_spec, list) and len(route_spec) > 0:
            script_path = route_spec[0]
            args = route_spec[1:]

            # Auto-generate title based on script name
            script_name = Path(script_path).name

            route_configs.append(
                ScriptConfig(
                    route_path=route_path,
                    script=script_path,
                    args=args,
                    title=f"{script_name}",
                )
            )
            continue

        # Handle simple script path (str/Path)
        script_path = route_spec

        # Auto-generate title based on script name
        script_name = Path(script_path).name

        route_configs.append(
            ScriptConfig(
                route_path=route_path,
                script=script_path,
                args=[],
                title=f"{script_name}",
            )
        )

    if not route_configs:
        raise ConfigurationError("No valid route configuration provided")

    return route_configs


# Legacy function name for backward compatibility
def create_script_configs(terminal_routes: Dict[str, Any]) -> List[ScriptConfig]:
    """
    Backward compatibility wrapper for create_route_configs.

    Note: This will filter out IndexPage configs and only return ScriptConfig instances.
    """
    all_configs = create_route_configs(terminal_routes)
    return [cfg for cfg in all_configs if isinstance(cfg, ScriptConfig)]
