# terminaide/core/settings.py

"""
Defines Pydantic-based settings for terminaide, including path handling for
root/non-root mounting and multiple script routing.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator
)

from ..exceptions import ConfigurationError

logger = logging.getLogger("terminaide")


def smart_resolve_path(path: Union[str, Path]) -> Path:
    """
    Resolves a path using a predictable strategy:
    1. First try the path as-is (absolute or relative to CWD)
    2. Then try relative to the main script being run (sys.argv[0])
    
    This approach is both flexible and predictable.
    """
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
            logger.debug(f"Found script at {script_relative_path} (relative to main script)")
            return script_relative_path.absolute()
    except Exception as e:
        logger.debug(f"Error resolving path relative to main script: {e}")
    
    # Return the original if nothing was found
    return original_path


class TTYDOptions(BaseModel):
    """TTYd-specific options like auth, interface, and client capacity."""
    writable: bool = True
    port: int = Field(default=7681, gt=1024, lt=65535)
    interface: str = "127.0.0.1"
    check_origin: bool = True
    max_clients: int = Field(default=1, gt=0)
    credential_required: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    force_https: bool = False  # Add this option to force HTTPS mode
    
    @model_validator(mode='after')
    def validate_credentials(self) -> 'TTYDOptions':
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

class ScriptConfig(BaseModel):
    """
    Configuration for a single terminal route, including the script path,
    port assignment, and optional custom title.
    """
    route_path: str
    client_script: Path
    args: List[str] = Field(default_factory=list)
    port: Optional[int] = None
    title: Optional[str] = None
    
    @field_validator('client_script')
    @classmethod
    def validate_script_path(cls, v: Union[str, Path]) -> Path:
        """
        Ensure the script file exists, trying:
        1. The path as provided (relative to CWD or absolute)
        2. The path relative to the main script being executed
        """
        resolved_path = smart_resolve_path(v)
        
        if not resolved_path.exists():
            # Create a helpful error message
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
        
        return resolved_path.absolute()
    
    @field_validator('route_path')
    @classmethod
    def validate_route_path(cls, v: str) -> str:
        """Normalize route path to start with '/' and remove trailing '/'."""
        if not v.startswith('/'):
            v = f"/{v}"
        if v != "/" and v.endswith('/'):
            v = v.rstrip('/')
        return v
    
    @field_validator('args')
    @classmethod
    def validate_args(cls, v: List[str]) -> List[str]:
        """Convert all args to strings."""
        return [str(arg) for arg in v]

class TTYDConfig(BaseModel):
    """
    Main configuraion for terminaide, handling root vs. non-root mounting,
    multiple scripts, and other settings like theme and debug mode.
    """
    client_script: Path
    mount_path: str = "/"
    port: int = Field(default=7681, gt=1024, lt=65535)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    ttyd_options: TTYDOptions = Field(default_factory=TTYDOptions)
    template_override: Optional[Path] = None
    debug: bool = False
    title: str = "Terminal"
    script_configs: List[ScriptConfig] = Field(default_factory=list)
    
    @field_validator('client_script', 'template_override')
    @classmethod
    def validate_paths(cls, v: Optional[Union[str, Path]]) -> Optional[Path]:
        """Ensure given path exists, if provided."""
        if v is None:
            return None
        path = Path(v)
        if not path.exists():
            raise ConfigurationError(f"Path does not exist: {path}")
        return path.absolute()
    
    @field_validator('mount_path')
    @classmethod
    def validate_mount_path(cls, v: str) -> str:
        """Normalize and disallow '/terminal' as a mount path."""
        if v in ("", "/"):
            return "/"
        if not v.startswith('/'):
            v = f"/{v}"
        v = v.rstrip('/')
        if v == "/terminal":
            raise ConfigurationError(
                '"/terminal" is reserved. Please use another mount path.'
            )
        return v
    
    @model_validator(mode='after')
    def validate_script_configs(self) -> 'TTYDConfig':
        """Check for unique route paths and handle a default script if no scripts given."""
        seen_routes = set()
        for config in self.script_configs:
            if config.route_path in seen_routes:
                raise ConfigurationError(f"Duplicate route path: {config.route_path}")
            seen_routes.add(config.route_path)
        if not self.script_configs and self.client_script:
            self.script_configs.append(
                ScriptConfig(route_path="/", client_script=self.client_script,
                             port=self.port, title=self.title)
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
    
    def get_script_config_for_path(self, path: str) -> Optional[ScriptConfig]:
        """
        Find which script config matches an incoming request path,
        returning the default if none match.
        """
        if len(self.script_configs) == 1:
            return self.script_configs[0]
        sorted_configs = sorted(
            self.script_configs,
            key=lambda c: len(c.route_path),
            reverse=True
        )
        for config in sorted_configs:
            if (config.route_path == "/" and (path == "/" or path.startswith("/terminal"))) \
               or path.startswith(config.route_path) \
               or path.startswith(f"{config.route_path}/terminal"):
                return config
        return self.script_configs[0] if self.script_configs else None
    
    def get_terminal_path_for_route(self, route_path: str) -> str:
        """Return the terminal path for a specific route, or global path if root."""
        if route_path == "/":
            return self.terminal_path
        return f"{route_path}/terminal"

    def get_health_check_info(self) -> Dict[str, Any]:
        """Return structured data about the config for health checks."""
        script_info = []
        for config in self.script_configs:
            script_info.append({
                "route_path": config.route_path,
                "script": str(config.client_script),
                "args": config.args,
                "port": config.port,
                "title": config.title or self.title
            })
        return {
            "mount_path": self.mount_path,
            "terminal_path": self.terminal_path,
            "static_path": self.static_path,
            "is_root_mounted": self.is_root_mounted,
            "is_multi_script": self.is_multi_script,
            "port": self.port,
            "debug": self.debug,
            "max_clients": self.ttyd_options.max_clients,
            "auth_required": self.ttyd_options.credential_required,
            "script_configs": script_info
        }